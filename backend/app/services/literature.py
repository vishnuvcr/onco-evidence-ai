import asyncio
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPE_PMC = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

def make_pubmed_query(question: str) -> str:
    # Conservative MVP query construction; not a validated systematic-review search.
    terms = re.findall(r"[A-Za-z0-9-]+", question)
    return " AND ".join(f'"{term}"' for term in terms[:18])

async def search_pubmed(client, question, limit):
    query = make_pubmed_query(question)
    response = await client.get(PUBMED_ESEARCH, params={
        "db": "pubmed", "term": query, "retmode": "json",
        "retmax": limit, "sort": "relevance"
    })
    response.raise_for_status()
    ids = response.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return []
    response = await client.get(PUBMED_EFETCH, params={
        "db": "pubmed", "id": ",".join(ids), "retmode": "xml"
    })
    response.raise_for_status()
    root = ET.fromstring(response.text)
    records = []
    for article in root.findall(".//PubmedArticle"):
        pmid = article.findtext(".//PMID", default="")
        title_node = article.find(".//ArticleTitle")
        title = " ".join("".join(title_node.itertext()).split()) if title_node is not None else ""
        abstract = []
        for node in article.findall(".//Abstract/AbstractText"):
            text = " ".join("".join(node.itertext()).split())
            label = node.attrib.get("Label")
            abstract.append(f"{label}: {text}" if label else text)
        doi = ""
        for node in article.findall(".//ArticleId"):
            if node.attrib.get("IdType") == "doi":
                doi = node.text or ""
        records.append({
            "title": title, "abstract": " ".join(abstract), "pmid": pmid,
            "doi": doi, "journal": article.findtext(".//Journal/Title", default=""),
            "year": article.findtext(".//PubDate/Year", default=""),
            "source": "PubMed",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        })
    return records

async def search_europe_pmc(client, question, limit):
    response = await client.get(EUROPE_PMC, params={
        "query": question, "format": "json", "pageSize": limit,
        "resultType": "core", "sort": "RELEVANCE"
    })
    response.raise_for_status()
    items = response.json().get("resultList", {}).get("result", [])
    records = []
    for item in items:
        pmid, doi = item.get("pmid", ""), item.get("doi", "")
        records.append({
            "title": item.get("title", ""), "abstract": item.get("abstractText", ""),
            "pmid": pmid, "doi": doi, "journal": item.get("journalTitle", ""),
            "year": str(item.get("firstPublicationDate", ""))[:4],
            "source": "Europe PMC",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else
                   (f"https://doi.org/{doi}" if doi else "")
        })
    return records

def deduplicate(records):
    result, seen = [], set()
    for record in records:
        key = (record.get("pmid") or "").lower() or (record.get("doi") or "").lower()
        if not key:
            key = re.sub(r"[^a-z0-9]", "", record.get("title", "").lower())
        if key and key not in seen:
            seen.add(key)
            result.append(record)
    return result

async def search_all(question, limit):
    async with httpx.AsyncClient(timeout=30.0, headers={
        "User-Agent": "OncoEvidenceAI/0.1 research prototype"
    }) as client:
        pubmed, epmc = await asyncio.gather(
            search_pubmed(client, question, limit),
            search_europe_pmc(client, question, limit),
            return_exceptions=True
        )
    errors, pubmed_records, epmc_records = [], [], []
    if isinstance(pubmed, Exception):
        errors.append({"source": "PubMed", "error": str(pubmed)})
    else:
        pubmed_records = pubmed
    if isinstance(epmc, Exception):
        errors.append({"source": "Europe PMC", "error": str(epmc)})
    else:
        epmc_records = epmc
    records = deduplicate(pubmed_records + epmc_records)
    return {
        "question": question,
        "searched_at": datetime.now(timezone.utc).isoformat(),
        "sources": ["PubMed", "Europe PMC"],
        "counts": {
            "pubmed_retrieved": len(pubmed_records),
            "europe_pmc_retrieved": len(epmc_records),
            "unique_records": len(records)
        },
        "source_errors": errors,
        "records": records,
        "interpretation": (
            "Discovery results only. Records have not been screened or critically "
            "appraised; no supporting/contradicting labels or clinical conclusions "
            "are assigned automatically."
        )
    }
