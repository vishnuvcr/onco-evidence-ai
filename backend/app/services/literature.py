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
            'TITLE:radiomics OR ABSTRACT:radiomics OR '
            'TITLE:radiomic OR ABSTRACT:radiomic OR '
            'TITLE:radiogenomics OR ABSTRACT:radiogenomics OR '
            'TITLE:"quantitative imaging" OR ABSTRACT:"quantitative imaging"'
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
    """Build a focused, field-restricted query from the clinical question."""
    normalised = _normalise(question)
    matched = [
        concept for concept in CONCEPTS
        if any(_normalise(trigger) in normalised for trigger in concept["triggers"])
    ]

    groups_pubmed = [f"({item['pubmed']})" for item in matched]
    groups_epmc = [f"({item['europe_pmc']})" for item in matched]
    strategy_parts = []

    if matched:
        strategy_parts.append(f"{len(matched)} mapped topic concept group(s)")

    # The site is oncology-focused. When radiomics is asked in the context of
    # radiation oncology/radiotherapy, require both the radiomics concept and
    # a radiotherapy-domain concept. This prevents a generic radiomics-only
    # query from returning unrelated diagnostic imaging papers.
    asks_radiomics = any(_normalise(x) in normalised for x in ("radiomics", "radiomic", "radiogenomics"))
    asks_radiotherapy_context = any(
        _normalise(x) in normalised
        for x in (
            "radiation oncology", "radiotherapy", "radiation therapy",
            "radiation treatment", "radiation therapy oncology",
        )
    )

    if asks_radiomics and asks_radiotherapy_context:
        rt_pubmed = (
            '"radiation oncology"[Title/Abstract] OR '
            '"radiotherapy"[Title/Abstract] OR '
            '"radiation therapy"[Title/Abstract] OR '
            '"radiation treatment"[Title/Abstract] OR '
            '"Radiotherapy"[MeSH Terms] OR '
            '"image-guided radiotherapy"[Title/Abstract] OR '
            '"intensity-modulated radiotherapy"[Title/Abstract] OR '
            '"intensity modulated radiation therapy"[Title/Abstract] OR '
            'IMRT[Title/Abstract] OR VMAT[Title/Abstract] OR '
            'SBRT[Title/Abstract] OR SABR[Title/Abstract] OR '
            'SRS[Title/Abstract] OR radiosurgery[Title/Abstract] OR '
            'brachytherapy[Title/Abstract] OR '
            '"proton therapy"[Title/Abstract] OR '
            '"stereotactic radiotherapy"[Title/Abstract] OR '
            'chemoradiotherapy[Title/Abstract]'
        )
        rt_epmc = (
            'TITLE:"radiation oncology" OR ABSTRACT:"radiation oncology" OR '
            'TITLE:radiotherapy OR ABSTRACT:radiotherapy OR '
            'TITLE:"radiation therapy" OR ABSTRACT:"radiation therapy" OR '
            'TITLE:"radiation treatment" OR ABSTRACT:"radiation treatment" OR '
            'TITLE:"image-guided radiotherapy" OR ABSTRACT:"image-guided radiotherapy" OR '
            'TITLE:"intensity-modulated radiotherapy" OR ABSTRACT:"intensity-modulated radiotherapy" OR '
            'TITLE:IMRT OR ABSTRACT:IMRT OR TITLE:VMAT OR ABSTRACT:VMAT OR '
            'TITLE:SBRT OR ABSTRACT:SBRT OR TITLE:SABR OR ABSTRACT:SABR OR '
            'TITLE:SRS OR ABSTRACT:SRS OR TITLE:radiosurgery OR ABSTRACT:radiosurgery OR '
            'TITLE:brachytherapy OR ABSTRACT:brachytherapy OR '
            'TITLE:"proton therapy" OR ABSTRACT:"proton therapy" OR '
            'TITLE:"stereotactic radiotherapy" OR ABSTRACT:"stereotactic radiotherapy" OR '
            'TITLE:chemoradiotherapy OR ABSTRACT:chemoradiotherapy'
        )
        groups_pubmed.append(f"({rt_pubmed})")
        groups_epmc.append(f"({rt_epmc})")
        strategy_parts.append("radiomics AND radiation-oncology context")
    elif matched:
        # Keep mapped concepts together using AND; synonyms remain OR'ed
        # within each concept group.
        pass

    if not groups_pubmed:
        terms = [
            token for token in re.findall(r"[A-Za-z0-9-]+", question.lower())
            if token not in STOPWORDS and len(token) > 2
        ]
        terms = list(dict.fromkeys(terms))[:8]
        if not terms:
            raise ValueError("The question did not contain searchable topic terms.")
        pubmed_terms = [f'"{term}"[Title/Abstract]' for term in terms]
        groups_pubmed = ["(" + " OR ".join(pubmed_terms) + ")"]
        groups_epmc = [
            "(" + " OR ".join(
                f"(TITLE:{term} OR ABSTRACT:{term})" for term in terms
            ) + ")"
        ]
        strategy_parts.append("field-restricted keyword fallback")

    return {
        "pubmed": " AND ".join(groups_pubmed),
        "europe_pmc": " AND ".join(groups_epmc),
        "strategy": (
            "Focused discovery query: " + "; ".join(strategy_parts) +
            ". Synonyms are OR'ed within concepts and distinct concepts are AND'ed. "
            "Outcome terms are not mandatory filters, to avoid excluding relevant "
            "radiotherapy studies that report endpoints using different terminology. "
            "This is not yet a peer-reviewed systematic-review search strategy."
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

    # NCBI recommends POST for EFetch requests containing more than
    # about 200 PMIDs. Posting the identifier list avoids HTTP 414 errors
    # caused by extremely long GET URLs.
    response = await _request_with_retry(client, "POST", PUBMED_EFETCH, {
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


RADIOMICS_MATCH_TERMS = (
    "radiomics", "radiomic", "radiogenomics", "delta radiomics",
    "texture analysis", "imaging biomarker", "quantitative imaging",
)
RADIOTHERAPY_MATCH_TERMS = (
    "radiation oncology", "radiotherapy", "radiation therapy",
    "radiation treatment", "image guided radiotherapy",
    "intensity modulated radiotherapy", "intensity modulated radiation",
    "imrt", "vmat", "sbrt", "sabr", "srs", "radiosurgery",
    "brachytherapy", "proton therapy", "stereotactic radiotherapy",
    "chemoradiotherapy",
)


def _relevance_assessment(record: dict[str, Any]) -> dict[str, Any]:
    title = _normalise(record.get("title", ""))
    abstract = _normalise(record.get("abstract", ""))
    full_text = f"{title} {abstract}"

    has_radiomics_title = any(term in title for term in RADIOMICS_MATCH_TERMS)
    has_rt_title = any(term in title for term in RADIOTHERAPY_MATCH_TERMS)
    has_radiomics = any(term in full_text for term in RADIOMICS_MATCH_TERMS)
    has_rt = any(term in full_text for term in RADIOTHERAPY_MATCH_TERMS)

    if has_radiomics_title and has_rt_title:
        tier, rank = "Very high: both concepts in title", 1
        reasons = ["Radiomics concept in title", "Radiotherapy context in title"]
    elif has_radiomics and has_rt and (has_radiomics_title or has_rt_title):
        tier, rank = "High: title + abstract context", 2
        reasons = ["Both concepts detected; at least one appears in the title"]
    elif has_radiomics and has_rt:
        tier, rank = "Moderate: both concepts in abstract", 3
        reasons = ["Both concepts detected in title/abstract metadata"]
    elif has_radiomics or has_rt:
        tier, rank = "Low: one concept detected", 4
        reasons = ["Only one of the two required concepts was detected in the returned metadata"]
    else:
        tier, rank = "Unclear relevance", 5
        reasons = ["Could not confirm both concepts from title/abstract text"]

    return {
        "relevance_tier": tier,
        "relevance_rank": rank,
        "relevance_reasons": reasons,
    }


def recommend_appraisal_tool(record: dict[str, Any], design: str) -> dict[str, str]:
    """Suggest a design-appropriate instrument; this is routing, not an appraisal."""
    text = _normalise(f"{record.get('title', '')} {record.get('abstract', '')}")

    if design == "Systematic review / meta-analysis":
        return {
            "recommended_appraisal_tool": "AMSTAR 2",
            "appraisal_tool_url": "https://www.amstar.ca/docs/AMSTAR-2.pdf",
            "appraisal_tool_note": "For systematic reviews of healthcare interventions. It appraises the review, not the included primary studies.",
        }
    if design == "Randomized controlled trial":
        return {
            "recommended_appraisal_tool": "Cochrane RoB 2",
            "appraisal_tool_url": "https://www.riskofbias.info/welcome/rob-2-0-tool",
            "appraisal_tool_note": "Assess a specific result/outcome from the RCT. Select the correct individually randomized, cluster, or crossover variant.",
        }
    if design == "Non-randomized interventional study":
        return {
            "recommended_appraisal_tool": "ROBINS-I V2 (draft)",
            "appraisal_tool_url": "https://www.riskofbias.info/welcome/robins-i-v2",
            "appraisal_tool_note": "The November 2025 V2 release is still a draft and is scoped to follow-up cohort studies; confirm applicability before use.",
        }
    if design == "Diagnostic / prediction model study":
        if any(term in text for term in ("radiomics", "radiomic", "machine learning", "artificial intelligence", "prediction model", "prognostic model", "risk prediction")):
            return {
                "recommended_appraisal_tool": "PROBAST+AI",
                "appraisal_tool_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC11931409/",
                "appraisal_tool_note": "For prediction models using regression or AI. Confirm that the paper is actually developing or validating a prediction model.",
            }
        return {
            "recommended_appraisal_tool": "QUADAS-3",
            "appraisal_tool_url": "https://www.bristol.ac.uk/population-health-sciences/projects/quadas/quadas-3/quadas-3-tool/",
            "appraisal_tool_note": "Current diagnostic test accuracy tool. Apply to the diagnostic accuracy estimates and applicability questions.",
        }
    if design in ("Prospective cohort study", "Retrospective cohort study"):
        if any(term in text for term in ("radiotherapy", "radiation therapy", "treatment", "intervention", "chemotherapy", "surgery")):
            return {
                "recommended_appraisal_tool": "ROBINS-I V2 (draft; confirm design)",
                "appraisal_tool_url": "https://www.riskofbias.info/welcome/robins-i-v2",
                "appraisal_tool_note": "Potentially appropriate for follow-up cohort studies evaluating interventions; V2 remains a draft. Otherwise select a JBI cohort or exposure-specific tool.",
            }
        return {
            "recommended_appraisal_tool": "ROBINS-E (exposure cohort)",
            "appraisal_tool_url": "https://www.riskofbias.info/welcome/robins-e-tool",
            "appraisal_tool_note": "For non-randomized follow-up cohort studies estimating the causal effect of an exposure. If this is not an exposure-effect question, use the appropriate JBI cohort checklist.",
        }
    if design in ("Case-control study", "Cross-sectional study", "Case series / case report"):
        return {
            "recommended_appraisal_tool": "JBI design-specific checklist",
            "appraisal_tool_url": "https://jbi.global/critical-appraisal-tools",
            "appraisal_tool_note": "Choose the matching case-control, analytical cross-sectional, case-series, or case-report checklist after full-text design confirmation.",
        }
    if design == "Narrative review / guideline":
        if "guideline" in text or "recommendation" in text:
            return {
                "recommended_appraisal_tool": "AGREE II",
                "appraisal_tool_url": "https://www.agreetrust.org/agree-ii/",
                "appraisal_tool_note": "For clinical practice guidelines; verify that the document is a guideline rather than a narrative review.",
            }
        return {
            "recommended_appraisal_tool": "SANRA",
            "appraisal_tool_url": "https://doi.org/10.1186/s41073-019-0064-8",
            "appraisal_tool_note": "For narrative reviews. SANRA assesses review quality, not formal risk of bias, and should not be confused with systematic-review appraisal.",
        }
    return {
        "recommended_appraisal_tool": "Manual design confirmation required",
        "appraisal_tool_url": "https://jbi.global/critical-appraisal-tools",
        "appraisal_tool_note": "The abstract does not establish a reliable study design. Inspect the full Methods section before selecting an appraisal tool.",
    }


def appraise_abstract(record: dict[str, Any]) -> dict[str, Any]:
    """Return screening metadata only; never infer outcome direction or study quality from abstract wording."""
    abstract = record.get("abstract") or ""
    text = f"{record.get('title', '')}. {abstract}"
    design = _study_design(record, text)
    rank = DESIGN_ORDER[design]

    return {
        "study_design": design,
        "design_rank": rank,
        "design_tier": "Provisional study-design classification — verify using the full Methods section.",
        "result_signal": "Not assessed — full text required",
        "result_signal_note": (
            "No favorable, unfavorable, or neutral conclusion is assigned from keyword "
            "or phrase matching. Outcomes must be extracted and compared with the "
            "prespecified comparator, endpoint, time point, effect estimate, and confidence interval."
        ),
        "results_summary": (
            "Full-text results extraction has not yet been completed. The abstract is "
            "retained for discovery and screening only."
        ),
        "sample_size_detected": None,
        "strengths": [],
        "limitations": [],
        "methodology_signals": [],
        "methodology_assessment": (
            "Not yet appraised. A full-text review of Methods, Results, tables, figures, "
            "supplements, protocol/registration, and statistical methods is required. "
            "A design-specific validated risk-of-bias tool must then be applied."
        ),
        "appraisal_scope": "Discovery metadata only — no critical appraisal performed.",
        "full_text_status": (
            "Full text not yet retrieved or analysed. Where a PMC identifier is present, "
            "the article can be checked for reusable full text under its own licence."
        ),
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
        record.update(_relevance_assessment(record))
        record.update(appraise_abstract(record))
        record.update(recommend_appraisal_tool(record, record.get("study_design", "Unclear from abstract")))

    signal_order = {
        "Favorable signal reported": 0,
        "Mixed / conflicting signal": 1,
        "Null / no-benefit signal reported": 2,
        "Unfavorable signal reported": 3,
        "Unclear from abstract": 4,
    }
    records.sort(key=lambda item: (
        item.get("relevance_rank", 99),
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
