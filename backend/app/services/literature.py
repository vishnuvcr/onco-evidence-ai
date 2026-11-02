import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3

# Focused terminology expansion for common oncology concepts. This is a
# discovery aid, not a substitute for a peer-reviewed systematic search strategy.
CONCEPTS = [
    {
        "triggers": ("adaptive radiotherapy", "adaptive radiation therapy", "adaptive replanning"),
        "pubmed": (
            '"adaptive radiotherapy"[Title/Abstract] OR '
            '"adaptive radiation therapy"[Title/Abstract] OR '
            '"adaptive replanning"[Title/Abstract]'
        ),
        "europe_pmc": (
            '"adaptive radiotherapy" OR "adaptive radiation therapy" OR '
            '"adaptive replanning"'
        ),
    },
    {
        "triggers": ("salivary gland", "salivary function", "salivary flow", "xerostomia", "parotid"),
        "pubmed": (
            '"salivary gland"[Title/Abstract] OR "salivary glands"[MeSH Terms] OR '
            '"salivary function"[Title/Abstract] OR "salivary flow"[Title/Abstract] OR '
            'xerostomia[Title/Abstract] OR "xerostomia"[MeSH Terms] OR '
            'parotid[Title/Abstract]'
        ),
        "europe_pmc": (
            '"salivary gland" OR "salivary glands" OR "salivary function" OR '
            '"salivary flow" OR xerostomia OR parotid'
        ),
    },
    {
        "triggers": ("head and neck", "head-neck", "hnscc"),
        "pubmed": (
            '"head and neck cancer"[Title/Abstract] OR '
            '"head and neck neoplasms"[MeSH Terms] OR '
            '"head and neck squamous cell carcinoma"[Title/Abstract] OR '
            'HNSCC[Title/Abstract]'
        ),
        "europe_pmc": (
            '"head and neck cancer" OR "head and neck neoplasms" OR '
            '"head and neck squamous cell carcinoma" OR HNSCC'
        ),
    },
]

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "between",
    "but", "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "how", "if", "in", "into", "is", "it", "may", "might",
    "of", "on", "or", "should", "the", "their", "this", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "will", "with", "would",
    "improve", "improves", "improved", "improving", "effect", "effects",
    "impact", "role", "use", "using", "does",
}


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def build_search_queries(question: str) -> dict[str, str]:
    """Build broad concept-based database queries from a natural-language question."""
    normalised = _normalise(question)
    matched = [
        concept for concept in CONCEPTS
        if any(_normalise(trigger) in normalised for trigger in concept["triggers"])
    ]

    if matched:
        pubmed_groups = [f"({item['pubmed']})" for item in matched]
        epmc_groups = [f"({item['europe_pmc']})" for item in matched]
        pubmed_query = " AND ".join(pubmed_groups)
        epmc_query = " AND ".join(epmc_groups)
        strategy = (
            "Concept-based search with relevant terminology expansion. "
            "The query is intended for discovery and has not been validated "
            "as a systematic-review search."
        )
        return {
            "pubmed": pubmed_query,
            "europe_pmc": epmc_query,
            "strategy": strategy,
        }

    # General fallback for questions outside the terminology map. Strip
    # question words and common verbs rather than AND-ing every word verbatim.
    terms = [
        token for token in re.findall(r"[A-Za-z0-9-]+", question.lower())
        if token not in STOPWORDS and len(token) > 2
    ]
    terms = list(dict.fromkeys(terms))[:8]
    if not terms:
        raise ValueError("The question did not contain searchable topic terms.")

    pubmed_query = " AND ".join(f'"{term}"[Title/Abstract]' for term in terms)
    epmc_query = " AND ".join(f'"{term}"' for term in terms)
    return {
        "pubmed": pubmed_query,
        "europe_pmc": epmc_query,
        "strategy": (
            "Keyword fallback after removing common question words. "
            "Consider adding a curated synonym strategy for this topic."
        ),
    }


async def _get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: dict[str, Any],
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            response = await client.get(url, params=params)
            if response.status_code in RETRYABLE_STATUS_CODES:
                if attempt < MAX_ATTEMPTS - 1:
                    retry_after = response.headers.get("Retry-After", "")
                    try:
                        delay = min(float(retry_after), 5.0)
                    except (TypeError, ValueError):
                        delay = 0.75 * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
            response.raise_for_status()
            return response
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(0.75 * (2 ** attempt))
                continue
            raise
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(0.75 * (2 ** attempt))
                continue
            raise
    if last_error:
        raise last_error
    raise RuntimeError("Request failed without a response.")


def _error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        detail = (exc.response.text or "").strip().replace("\n", " ")[:300]
        return f"HTTP {exc.response.status_code}: {detail or exc.response.reason_phrase}"
    return f"{type(exc).__name__}: {str(exc)[:300]}"


async def search_pubmed(client: httpx.AsyncClient, query: str, limit: int) -> list[dict[str, str]]:
    response = await _get_with_retry(client, PUBMED_ESEARCH, {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": limit,
        "sort": "relevance",
    })
    search_data = response.json().get("esearchresult", {})
    ids = search_data.get("idlist", [])
    if not ids:
        return []

    response = await _get_with_retry(client, PUBMED_EFETCH, {
        "db": "pubmed",
        "id": ",".join(ids),
        "retmode": "xml",
    })
    root = ET.fromstring(response.text)
    records = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title_node = article.find(".//ArticleTitle")
        title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
        abstract_parts = []
        for node in article.findall(".//Abstract/AbstractText"):
            abstract_text = " ".join("".join(node.itertext()).split())
            label = node.attrib.get("Label")
            abstract_parts.append(f"{label}: {abstract_text}" if label else abstract_text)

        doi = ""
        for node in article.findall(".//ArticleId"):
            if node.attrib.get("IdType") == "doi":
                doi = node.text or ""

        year = article.findtext(".//PubDate/Year", default="")
        if not year:
            medline_date = article.findtext(".//PubDate/MedlineDate", default="")
            year_match = re.search(r"\b(19|20)\d{2}\b", medline_date)
            year = year_match.group(0) if year_match else ""

        records.append({
            "title": title,
            "abstract": " ".join(abstract_parts),
            "pmid": pmid,
            "doi": doi,
            "journal": article.findtext(".//Journal/Title", default=""),
            "year": year,
            "source": "PubMed",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return records


async def search_europe_pmc(
    client: httpx.AsyncClient,
    query: str,
    limit: int,
) -> list[dict[str, str]]:
    response = await _get_with_retry(client, EUROPE_PMC, {
        "query": query,
        "format": "json",
        "pageSize": limit,
        "resultType": "core",
        "sort": "RELEVANCE",
    })
    items = response.json().get("resultList", {}).get("result", [])
    records = []
    for item in items:
        pmid, doi = item.get("pmid", ""), item.get("doi", "")
        records.append({
            "title": item.get("title", ""),
            "abstract": item.get("abstractText", ""),
            "pmid": pmid,
            "doi": doi,
            "journal": item.get("journalTitle", ""),
            "year": str(item.get("firstPublicationDate", ""))[:4],
            "source": "Europe PMC",
            "url": (
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid
                else (f"https://doi.org/{doi}" if doi else "")
            ),
        })
    return records


def deduplicate(records: list[dict[str, str]]) -> list[dict[str, str]]:
    result, seen = [], set()
    for record in records:
        key = (record.get("pmid") or "").lower() or (record.get("doi") or "").lower()
        if not key:
            key = re.sub(r"[^a-z0-9]", "", record.get("title", "").lower())
        if key and key not in seen:
            seen.add(key)
            result.append(record)
    return result


async def search_all(question: str, limit: int) -> dict[str, Any]:
    queries = build_search_queries(question)
    timeout = httpx.Timeout(25.0, connect=10.0)
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "OncoEvidenceAI/0.2 (literature discovery prototype)"},
    ) as client:
        pubmed, epmc = await asyncio.gather(
            search_pubmed(client, queries["pubmed"], limit),
            search_europe_pmc(client, queries["europe_pmc"], limit),
            return_exceptions=True,
        )

    errors = []
    if isinstance(pubmed, Exception):
        errors.append({"source": "PubMed", "error": _error_message(pubmed)})
        pubmed_records = []
    else:
        pubmed_records = pubmed

    if isinstance(epmc, Exception):
        errors.append({"source": "Europe PMC", "error": _error_message(epmc)})
        epmc_records = []
    else:
        epmc_records = epmc

    records = deduplicate(pubmed_records + epmc_records)
    return {
        "question": question,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["PubMed", "Europe PMC"],
        "search_strategy": queries["strategy"],
        "queries": {
            "pubmed": queries["pubmed"],
            "europe_pmc": queries["europe_pmc"],
        },
        "counts": {
            "pubmed_retrieved": len(pubmed_records),
            "europe_pmc_retrieved": len(epmc_records),
            "unique_records": len(records),
        },
        "source_errors": errors,
        "records": records,
        "interpretation": (
            "Discovery results only. Records have not been screened or critically "
            "appraised; no supporting/contradicting labels or clinical conclusions "
            "are assigned automatically. Search coverage is limited by database "
            "indexing and this prototype's terminology map."
        ),
        "status": "partial" if errors and records else (
            "source_error" if errors and not records else (
                "no_results" if not records else "ok"
            )
        ),
    }
