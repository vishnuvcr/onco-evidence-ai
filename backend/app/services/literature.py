import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPE_PMC_POST = "https://www.ebi.ac.uk/europepmc/webservices/rest/searchPOST"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3

CONCEPTS = [
    {
        "triggers": ("adaptive radiotherapy", "adaptive radiation therapy", "adaptive replanning"),
        "pubmed": (
            '"adaptive radiotherapy"[Title/Abstract] OR '
            '"adaptive radiation therapy"[Title/Abstract] OR '
            '"adaptive replanning"[Title/Abstract] OR '
            '"online adaptive radiotherapy"[Title/Abstract] OR '
            '"offline adaptive radiotherapy"[Title/Abstract]'
        ),
        "europe_pmc": (
            '"adaptive radiotherapy" OR "adaptive radiation therapy" OR '
            '"adaptive replanning" OR "online adaptive radiotherapy" OR '
            '"offline adaptive radiotherapy"'
        ),
    },
    {
        "triggers": ("salivary gland", "salivary function", "salivary flow", "xerostomia", "parotid"),
        "pubmed": (
            '"salivary gland"[Title/Abstract] OR "salivary glands"[MeSH Terms] OR '
            '"salivary function"[Title/Abstract] OR "salivary flow"[Title/Abstract] OR '
            'xerostomia[Title/Abstract] OR "xerostomia"[MeSH Terms] OR '
            'parotid[Title/Abstract] OR hyposalivation[Title/Abstract]'
        ),
        "europe_pmc": (
            '"salivary gland" OR "salivary glands" OR "salivary function" OR '
            '"salivary flow" OR xerostomia OR parotid OR hyposalivation'
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
    {
        "triggers": ("radiomics", "radiomic", "radiogenomics"),
        "pubmed": (
            'radiomics[Title/Abstract] OR radiomic[Title/Abstract] OR '
            'radiogenomics[Title/Abstract] OR "quantitative imaging"[Title/Abstract]'
        ),
        "europe_pmc": (
            'radiomics OR radiomic OR radiogenomics OR "quantitative imaging"'
        ),
    },
    {
        "triggers": ("lung cancer", "lung neoplasm", "nsclc", "sclc"),
        "pubmed": (
            '"lung neoplasms"[MeSH Terms] OR "lung cancer"[Title/Abstract] OR '
            'NSCLC[Title/Abstract] OR SCLC[Title/Abstract]'
        ),
        "europe_pmc": (
            '"lung cancer" OR "lung neoplasms" OR NSCLC OR SCLC'
        ),
    },
    {
        "triggers": ("breast cancer", "breast neoplasm"),
        "pubmed": (
            '"breast neoplasms"[MeSH Terms] OR "breast cancer"[Title/Abstract]'
        ),
        "europe_pmc": '"breast cancer" OR "breast neoplasms"',
    },
]

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "between",
    "but", "by", "can", "could", "did", "do", "does", "for", "from", "had",
    "has", "have", "how", "if", "in", "into", "is", "it", "may", "might",
    "of", "on", "or", "should", "the", "their", "this", "to", "was", "were",
    "what", "when", "where", "which", "who", "why", "will", "with", "would",
    "improve", "improves", "improved", "improving", "effect", "effects",
    "impact", "role", "use", "using",
}

DESIGN_ORDER = {
    "Systematic review / meta-analysis": 1,
    "Randomized controlled trial": 2,
    "Non-randomized interventional study": 3,
    "Prospective cohort study": 4,
    "Retrospective cohort study": 5,
    "Case-control study": 6,
    "Cross-sectional study": 7,
    "Diagnostic / prediction model study": 8,
    "Case series / case report": 9,
    "Narrative review / guideline": 10,
    "Unclear from abstract": 11,
}


def _normalise(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def build_search_queries(question: str) -> dict[str, str]:
    """Build source-specific concept queries from the clinical question."""
    normalised = _normalise(question)
    matched = [
        concept for concept in CONCEPTS
        if any(_normalise(trigger) in normalised for trigger in concept["triggers"])
    ]
    if matched:
        pubmed_query = " AND ".join(f"({item['pubmed']})" for item in matched)
        epmc_query = " AND ".join(f"({item['europe_pmc']})" for item in matched)
        return {
            "pubmed": pubmed_query,
            "europe_pmc": epmc_query,
            "strategy": (
                f"Concept-based search: {len(matched)} mapped concept group(s), "
                "using source-specific synonyms. Discovery strategy only; "
                "not a validated systematic-review search."
            ),
        }

    terms = [
        token for token in re.findall(r"[A-Za-z0-9-]+", question.lower())
        if token not in STOPWORDS and len(token) > 2
    ]
    terms = list(dict.fromkeys(terms))[:8]
    if not terms:
        raise ValueError("The question did not contain searchable topic terms.")
    pubmed_query = " OR ".join(f'"{term}"[Title/Abstract]' for term in terms)
    epmc_query = " OR ".join(f'"{term}"' for term in terms)
    return {
        "pubmed": f"({pubmed_query})",
        "europe_pmc": f"({epmc_query})",
        "strategy": (
            "Broad keyword fallback using OR between extracted topic terms. "
            "Review the displayed query and refine it for a formal review."
        ),
    }


async def _request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    params: dict[str, Any],
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(MAX_ATTEMPTS):
        try:
            if method == "POST":
                response = await client.post(url, data=params)
            else:
                response = await client.get(url, params=params)
            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(max(float(retry_after), 0.25), 5.0)
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


async def search_pubmed(
    client: httpx.AsyncClient, query: str, limit: int
) -> tuple[list[dict[str, Any]], int]:
    response = await _request_with_retry(client, "GET", PUBMED_ESEARCH, {
        "db": "pubmed", "term": query, "retmode": "json",
        "retmax": limit, "sort": "relevance",
    })
    search_data = response.json().get("esearchresult", {})
    ids = search_data.get("idlist", [])
    total = int(search_data.get("count", len(ids)) or 0)
    if not ids:
        return [], total

    response = await _request_with_retry(client, "GET", PUBMED_EFETCH, {
        "db": "pubmed", "id": ",".join(ids), "retmode": "xml",
    })
    root = ET.fromstring(response.text)
    records: list[dict[str, Any]] = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title_node = article.find(".//ArticleTitle")
        title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
        abstract_parts = []
        for node in article.findall(".//Abstract/AbstractText"):
            abstract_text = " ".join("".join(node.itertext()).split())
            label = node.attrib.get("Label") or node.attrib.get("NlmCategory")
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
        publication_types = [
            " ".join("".join(node.itertext()).split())
            for node in article.findall(".//PublicationTypeList/PublicationType")
        ]
        authors = []
        for author in article.findall(".//AuthorList/Author"):
            collective = author.findtext("CollectiveName")
            last = author.findtext("LastName", default="")
            fore = author.findtext("ForeName", default="")
            name = collective or " ".join(part for part in (fore, last) if part)
            if name:
                authors.append(name)
        records.append({
            "title": title, "abstract": " ".join(abstract_parts),
            "pmid": pmid, "doi": doi, "pmcid": "",
            "journal": article.findtext(".//Journal/Title", default=""),
            "year": year, "authors": authors,
            "publication_types": publication_types,
            "cited_by_count": None, "is_open_access": None,
            "source": "PubMed",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
        })
    return records, total


async def search_europe_pmc(
    client: httpx.AsyncClient, query: str, limit: int
) -> tuple[list[dict[str, Any]], int, str]:
    params = {
        "query": query, "format": "json", "pageSize": limit,
        "resultType": "core", "synonym": "true",
    }
    try:
        response = await _request_with_retry(client, "GET", EUROPE_PMC, params)
        route = "GET"
    except Exception as get_error:
        try:
            response = await _request_with_retry(client, "POST", EUROPE_PMC_POST, params)
            route = "POST fallback"
        except Exception as post_error:
            raise RuntimeError(
                f"GET failed ({_error_message(get_error)}); "
                f"POST fallback failed ({_error_message(post_error)})"
            ) from post_error

    payload = response.json()
    items = payload.get("resultList", {}).get("result", [])
    total = int(payload.get("hitCount", len(items)) or 0)
    records: list[dict[str, Any]] = []
    for item in items:
        pmid, doi = item.get("pmid", ""), item.get("doi", "")
        pub_type_data = item.get("pubTypeList") or {}
        pub_types = pub_type_data.get("pubType", []) if isinstance(pub_type_data, dict) else pub_type_data
        if isinstance(pub_types, str):
            pub_types = [pub_types]
        if not isinstance(pub_types, list):
            pub_types = []
        author_string = item.get("authorString", "")
        records.append({
            "title": item.get("title", ""),
            "abstract": item.get("abstractText", ""),
            "pmid": pmid, "doi": doi, "pmcid": item.get("pmcid", ""),
            "journal": item.get("journalTitle", ""),
            "year": str(item.get("firstPublicationDate") or item.get("pubYear") or "")[:4],
            "authors": [author_string] if author_string else [],
            "publication_types": pub_types,
            "cited_by_count": item.get("citedByCount"),
            "is_open_access": item.get("isOpenAccess"),
            "source": "Europe PMC",
            "url": (
                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid
                else (f"https://doi.org/{doi}" if doi else "")
            ),
        })
    return records, total, route


def deduplicate(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: dict[str, int] = {}
    for record in records:
        key = (record.get("pmid") or "").lower() or (record.get("doi") or "").lower()
        if not key:
            key = re.sub(r"[^a-z0-9]", "", record.get("title", "").lower())
        if not key:
            continue
        if key in seen:
            index = seen[key]
            existing = result[index]
            sources = list(dict.fromkeys(
                existing.get("sources", [existing.get("source", "")]) +
                record.get("sources", [record.get("source", "")])
            ))
            if len(record.get("abstract", "")) > len(existing.get("abstract", "")):
                result[index] = {**record, "sources": [s for s in sources if s]}
            else:
                existing["sources"] = [s for s in sources if s]
            continue
        record["sources"] = [record.get("source", "")]
        seen[key] = len(result)
        result.append(record)
    return result


def _study_design(record: dict[str, Any], text: str) -> str:
    types = " ".join(record.get("publication_types") or []).lower()
    value = f"{types} {text}".lower()
    if re.search(r"systematic review|meta-analysis|meta analysis", value):
        return "Systematic review / meta-analysis"
    if re.search(r"randomized|randomised|randomly assigned|random allocation", value):
        return "Randomized controlled trial"
    if re.search(r"phase\s*(ii|2|iii|3|i|1)\b", value) and re.search(r"trial|study", value):
        return "Non-randomized interventional study"
    if re.search(r"prospective.{0,35}(cohort|observational)|prospectively enrolled|prospective study", value):
        return "Prospective cohort study"
    if re.search(r"retrospective.{0,35}(cohort|observational)|retrospective study|medical records were reviewed", value):
        return "Retrospective cohort study"
    if re.search(r"case.control", value):
        return "Case-control study"
    if re.search(r"cross.sectional", value):
        return "Cross-sectional study"
    if re.search(r"diagnostic accuracy|receiver operating characteristic|prediction model|radiomics.{0,30}model", value):
        return "Diagnostic / prediction model study"
    if re.search(r"case series|case report", value):
        return "Case series / case report"
    if re.search(r"review|guideline|consensus", types):
        return "Narrative review / guideline"
    return "Unclear from abstract"


def _result_signal(text: str) -> tuple[str, str]:
    lower = text.lower()
    favorable = bool(re.search(
        r"(significantly|significant) (improved|higher|better)|"
        r"improved (overall survival|progression.free survival|disease.free survival|local control|response|quality of life)|"
        r"reduced (mortality|recurrence|toxicity|xerostomia|risk)|"
        r"superior (overall survival|local control|response|outcome)", lower,
    ))
    null = bool(re.search(
        r"no significant difference|not significantly (different|improved|associated)|"
        r"no improvement|similar (overall survival|outcomes|rates)|"
        r"did not improve|failed to improve|equivalent outcomes", lower,
    ))
    unfavorable = bool(re.search(
        r"worse (overall survival|outcomes|local control)|inferior (overall survival|local control|outcomes)|"
        r"higher (grade\s*[3-5]|severe toxicity|treatment.related mortality)", lower,
    ))
    if sum((favorable, null, unfavorable)) > 1:
        return "Mixed / conflicting signal", "The abstract contains phrases pointing in more than one direction."
    if favorable:
        return "Favorable signal reported", "A favorable outcome phrase was detected in the abstract; verify the endpoint and comparator."
    if null:
        return "Null / no-benefit signal reported", "A no-difference or no-benefit phrase was detected in the abstract."
    if unfavorable:
        return "Unfavorable signal reported", "An unfavorable outcome phrase was detected in the abstract; verify the endpoint and context."
    return "Unclear from abstract", "The abstract does not contain a sufficiently clear outcome-direction phrase for automated grouping."


def appraise_abstract(record: dict[str, Any]) -> dict[str, Any]:
    abstract = record.get("abstract") or ""
    text = f"{record.get('title', '')}. {abstract}"
    design = _study_design(record, text)
    rank = DESIGN_ORDER[design]
    lower = text.lower()
    strengths: list[str] = []
    limitations: list[str] = []
    signals: list[str] = []

    checks = [
        (r"randomi[sz]ed|random allocation", "Random allocation is mentioned in the abstract."),
        (r"prospective|prospectively", "Prospective data collection is mentioned."),
        (r"multicentre|multicenter|multi-centre|multi-center", "A multicenter design is mentioned."),
        (r"blinded|double.blind|triple.blind", "Blinding is mentioned."),
        (r"intention.to.treat|intention to treat", "Intention-to-treat analysis is mentioned."),
        (r"multivariable|multivariate|adjusted analysis|propensity score", "Adjusted or multivariable analysis is mentioned."),
        (r"external validation|independent validation|external cohort", "External/independent validation is mentioned."),
        (r"registered|registration number|clinicaltrials.gov", "Study registration is mentioned."),
    ]
    for pattern, description in checks:
        if re.search(pattern, lower):
            strengths.append(description)
            signals.append(description)
    if re.search(r"retrospective", lower):
        limitations.append("Retrospective design is mentioned; selection and information bias need full-text assessment.")
    if re.search(r"single.center|single institution|single.institutional", lower):
        limitations.append("Single-center/institution setting is mentioned; generalizability needs assessment.")
    if re.search(r"small sample|limited sample|few patients|\b(n\s*[=<:]?\s*[0-4]?\d)\b", lower):
        limitations.append("A small sample or small cohort may be a concern; verify the actual sample size and power.")
    if re.search(r"short follow.up|limited follow.up|median follow.up.{0,30}(month|week)", lower):
        limitations.append("Follow-up duration may be limited; assess whether it is adequate for the endpoint.")
    if re.search(r"no control group|without a control|single.arm", lower):
        limitations.append("No concurrent control/comparator is indicated.")
    if re.search(r"limitations? (include|are|were|of this study)|limited by", lower):
        limitations.append("The authors explicitly discuss limitations in the abstract.")

    n_match = re.search(
        r"\b(?:n\s*=\s*|among\s+)(\d{2,5})\s*(?:patients|participants|subjects|cases)?",
        lower,
    )
    sample_size = int(n_match.group(1)) if n_match else None

    summary_sentences = []
    for _label, content in re.findall(
        r"(?:^|\s)(RESULTS?|FINDINGS?|CONCLUSIONS?|CONCLUSION)\s*:\s*(.*?)(?=\s(?:METHODS?|BACKGROUND|OBJECTIVE|AIMS?|RESULTS?|FINDINGS?|CONCLUSIONS?|CONCLUSION)\s*:|$)",
        abstract, flags=re.IGNORECASE,
    ):
        if content.strip():
            summary_sentences.append(content.strip())
    if not summary_sentences:
        sentences = re.split(r"(?<=[.!?])\s+", abstract.strip())
        summary_sentences = [
            sentence.strip() for sentence in sentences
            if re.search(r"result|found|observed|associated|survival|response|control|significant|conclud|demonstrat", sentence, re.I)
        ][:2]
    results_summary = " ".join(summary_sentences)[:900] if summary_sentences else (
        "No extractable results statement was identified in the available abstract."
    )

    signal, signal_note = _result_signal(results_summary)
    if not strengths:
        strengths = ["No specific methodological strength signal was detected in the abstract."]
    if not limitations:
        limitations = ["No explicit limitation signal was detected in the abstract; this does not mean the study has no limitations."]

    if rank <= 2:
        design_tier = "Higher-level design signal"
    elif rank <= 5:
        design_tier = "Comparative/interventional or cohort design signal"
    elif rank <= 8:
        design_tier = "Observational/model-based design signal"
    elif rank <= 10:
        design_tier = "Descriptive or secondary evidence signal"
    else:
        design_tier = "Design unclear from abstract"

    return {
        "study_design": design, "design_rank": rank, "design_tier": design_tier,
        "result_signal": signal, "result_signal_note": signal_note,
        "results_summary": results_summary, "sample_size_detected": sample_size,
        "strengths": strengths, "limitations": limitations,
        "methodology_signals": signals,
        "methodology_assessment": (
            "Preliminary abstract-level signals only. Correctness, risk of bias, "
            "allocation concealment, missing data, protocol deviations, outcome "
            "switching and statistical assumptions require full-text appraisal."
        ),
        "appraisal_scope": "Abstract-level automated screen; not a validated risk-of-bias tool.",
    }


async def search_all(question: str, limit: int) -> dict[str, Any]:
    queries = build_search_queries(question)
    timeout = httpx.Timeout(30.0, connect=12.0)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=True,
        headers={
            "User-Agent": "OncoEvidenceAI/0.3 (open clinical literature discovery)",
            "Accept": "application/json, application/xml;q=0.9, */*;q=0.8",
        },
    ) as client:
        pubmed_result, epmc_result = await asyncio.gather(
            search_pubmed(client, queries["pubmed"], limit),
            search_europe_pmc(client, queries["europe_pmc"], limit),
            return_exceptions=True,
        )

    errors = []
    if isinstance(pubmed_result, Exception):
        errors.append({"source": "PubMed", "error": _error_message(pubmed_result)})
        pubmed_records, pubmed_total = [], 0
    else:
        pubmed_records, pubmed_total = pubmed_result
    if isinstance(epmc_result, Exception):
        errors.append({"source": "Europe PMC", "error": _error_message(epmc_result)})
        epmc_records, epmc_total, epmc_route = [], 0, "failed"
    else:
        epmc_records, epmc_total, epmc_route = epmc_result

    records = deduplicate(pubmed_records + epmc_records)
    for record in records:
        record.update(appraise_abstract(record))

    signal_order = {
        "Favorable signal reported": 0,
        "Mixed / conflicting signal": 1,
        "Null / no-benefit signal reported": 2,
        "Unfavorable signal reported": 3,
        "Unclear from abstract": 4,
    }
    records.sort(key=lambda item: (
        item.get("design_rank", 99),
        signal_order.get(item.get("result_signal", ""), 5),
        -(int(item.get("year") or 0)),
    ))

    design_counts: dict[str, int] = {}
    signal_counts: dict[str, int] = {}
    year_counts: dict[str, int] = {}
    for item in records:
        design = item.get("study_design", "Unclear from abstract")
        signal = item.get("result_signal", "Unclear from abstract")
        design_counts[design] = design_counts.get(design, 0) + 1
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
        year = str(item.get("year") or "Unknown")
        year_counts[year] = year_counts.get(year, 0) + 1

    return {
        "question": question,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["PubMed", "Europe PMC"],
        "search_strategy": queries["strategy"],
        "queries": {"pubmed": queries["pubmed"], "europe_pmc": queries["europe_pmc"]},
        "requested_limit_per_source": limit,
        "counts": {
            "pubmed_retrieved": len(pubmed_records),
            "pubmed_total_matches": pubmed_total,
            "europe_pmc_retrieved": len(epmc_records),
            "europe_pmc_total_matches": epmc_total,
            "unique_records": len(records),
        },
        "source_status": {
            "PubMed": "error" if any(e["source"] == "PubMed" for e in errors) else "ok",
            "Europe PMC": "error" if any(e["source"] == "Europe PMC" for e in errors) else "ok",
            "Europe PMC route": epmc_route,
        },
        "appraisal_summary": {
            "by_study_design": design_counts,
            "by_reported_result_signal": signal_counts,
            "by_publication_year": year_counts,
        },
        "source_errors": errors,
        "records": records,
        "interpretation": (
            "Literature discovery with preliminary automated abstract-level grouping. "
            "Result-direction labels are phrase-based signals, not independent verification "
            "of the paper's conclusions. Methodology signals do not establish correctness "
            "or risk of bias. Read the full text and apply an appropriate validated tool "
            "(for example RoB 2, ROBINS-I, QUADAS-2 or AMSTAR 2) before clinical use. "
            "Search completeness is not guaranteed by any single database."
        ),
        "status": "partial" if errors and records else (
            "source_error" if errors and not records else ("no_results" if not records else "ok")
        ),
    }
