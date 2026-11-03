import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any
import httpx

from app.services.literature import appraise_abstract, recommend_appraisal_tool

EPMC = "https://www.ebi.ac.uk/europepmc/webservices/rest"
GROQ = "https://api.groq.com/openai/v1/chat/completions"


def tidy(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def get_key(record: dict[str, Any]) -> str:
    return tidy(str(record.get("pmcid") or record.get("pmid") or record.get("doi") or record.get("title") or ""))


def parse_pmc_xml(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    titles = root.findall(".//article-title")
    title = tidy(" ".join(titles[0].itertext())) if titles else ""
    abstract = tidy(" ".join(" ".join(x.itertext()) for x in root.findall(".//abstract")))
    body = root.find(".//body")
    blocks: list[str] = []

    def walk(section: ET.Element) -> None:
        heading_nodes = section.findall("./title")
        heading = tidy(" ".join(heading_nodes[0].itertext())) if heading_nodes else "Untitled section"
        blocks.append("\n## " + heading)
        for child in list(section):
            kind = child.tag.split("}")[-1].lower()
            if kind == "sec":
                walk(child)
            elif kind in ("p", "table-wrap", "fig"):
                text = tidy(" ".join(child.itertext()))
                if text:
                    blocks.append(text if kind == "p" else "[" + kind.upper() + "] " + text)

    if body is not None:
        for node in list(body):
            if node.tag.split("}")[-1].lower() == "sec":
                walk(node)
            elif node.tag.split("}")[-1].lower() in ("table-wrap", "fig"):
                value = tidy(" ".join(node.itertext()))
                if value:
                    blocks.append("[TABLE/FIGURE] " + value)

    body_text = "\n".join(blocks)
    if len(body_text) > 14000:
        method, other = [], []
        for block in body_text.split("\n## "):
            header = block[:130].lower()
            if any(word in header for word in ("method", "result", "discussion", "table", "outcome", "statistical")):
                method.append(block)
            else:
                other.append(block)
        body_text = "\n## ".join(method + other)[:14000]

    licences = root.findall(".//license")
    licence = tidy(" ".join(" ".join(x.itertext()) for x in licences))[:600]
    if licences:
        licence_url = licences[0].attrib.get("{http://www.w3.org/1999/xlink}href", "")
        if licence_url:
            licence += " (" + licence_url + ")"
    return {"title": title, "abstract": abstract, "body": body_text, "license": licence}


def domains_for(tool: str) -> list[str]:
    if "RoB 2" in tool:
        return ["Randomization process", "Deviations from intended interventions", "Missing outcome data", "Outcome measurement", "Selection of reported result"]
    if "ROBINS-I" in tool:
        return ["Confounding", "Participant selection", "Intervention classification", "Deviations", "Missing data", "Outcome measurement", "Selective reporting"]
    if "PROBAST" in tool:
        return ["Participants and data sources", "Predictors", "Outcome", "Analysis", "Applicability"]
    if "QUADAS" in tool:
        return ["Patient selection", "Index test", "Reference standard", "Flow and timing", "Applicability"]
    if "AMSTAR" in tool:
        return ["Protocol", "Search and selection", "Risk-of-bias assessment", "Synthesis methods", "Publication bias", "Conflicts of interest"]
    if "AGREE" in tool:
        return ["Scope and purpose", "Stakeholder involvement", "Rigor of development", "Clarity", "Applicability", "Editorial independence"]
    if "SANRA" in tool:
        return ["Importance", "Aims", "Literature search", "Referencing", "Scientific reasoning", "Data presentation"]
    return ["Participant selection", "Intervention or exposure measurement", "Outcome measurement", "Confounding and follow-up", "Statistical analysis"]


async def resolve_pmc(client: httpx.AsyncClient, record: dict[str, Any]) -> dict[str, Any] | None:
    if record.get("pmcid"):
        query = "EXT_ID:" + tidy(str(record["pmcid"]))
    elif record.get("pmid"):
        query = "EXT_ID:" + tidy(str(record["pmid"]))
    elif record.get("doi"):
        query = 'DOI:"' + tidy(str(record["doi"])) + '"'
    else:
        return None
    response = await client.get(EPMC + "/search", params={"query": query, "format": "json", "resultType": "core", "pageSize": 1})
    response.raise_for_status()
    rows = response.json().get("resultList", {}).get("result", [])
    return rows[0] if rows else None


async def call_groq(client: httpx.AsyncClient, record: dict[str, Any], text: dict[str, str], tool: str, domains: list[str]) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured on the backend.")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    system = """You are a clinical evidence reviewer. Appraise only the supplied paper text.
Never invent data, effect estimates, confidence intervals, p-values or quotations.
Do not classify an entire paper as favourable or unfavourable. Classify each outcome separately
relative to comparator and endpoint direction. A non-significant result does not prove equivalence.
Distinguish statistical significance from clinical importance. If data are missing, say not reported.
Make risk-of-bias judgements only when evidence supports them; otherwise use unclear.
Quotes must be exact excerpts copied from the source text. Return JSON only."""
    schema = {
      "study_design_verified": "Study design stated in Methods",
      "population": "Population and setting",
      "intervention": "Intervention or exposure",
      "comparator": "Comparator",
      "follow_up": "Follow up",
      "outcomes": [{
        "outcome": "Outcome name",
        "outcome_group": "benefit | no_clear_difference | harm | mixed | unclear | not_reported",
        "endpoint": "Endpoint and its direction",
        "timepoint": "Timepoint",
        "population_n": "Analyzed N",
        "events_or_summary": "Events or summary data",
        "effect_measure": "HR/RR/OR/MD/AUC or other",
        "effect_estimate": "Exact estimate",
        "confidence_interval": "Exact CI",
        "p_value": "Exact p-value",
        "statistical_significance": "significant / not significant / not reported",
        "clinical_interpretation": "Balanced interpretation",
        "evidence_quotes": [{"section": "Results or table", "excerpt": "Exact text", "location": "Table or figure"}]
      }],
      "main_findings": "Balanced findings",
      "methods_assessment": "Design, selection, allocation, confounding, missing data and analysis",
      "limitations_reported": ["Author-reported limitations"],
      "funding_and_conflicts": "As reported",
      "risk_of_bias": {"overall_judgement": "low | some_concerns | high | unclear",
        "domains": [{"domain": "One framework domain", "judgement": "low | some_concerns | high | unclear | not_applicable",
          "rationale": "Evidence-based rationale", "evidence_quotes": [{"section": "Methods", "excerpt": "Exact text"}]}]},
      "appraisal_warnings": ["Missing or ambiguous information"]
    }
    user = {"paper": {k: record.get(k, "") for k in ("title", "journal", "year", "pmid", "doi", "pmcid")},
            "framework": tool, "domains_to_assess": domains, "required_json": schema,
            "full_text": "TITLE: " + text["title"] + "\nABSTRACT: " + text["abstract"][:1500] + "\n" + text["body"]}
    response = await client.post(GROQ, headers={"Authorization": "Bearer " + api_key},
      json={"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}],
            "temperature": 0.1, "max_completion_tokens": 1800, "response_format": {"type": "json_object"}}, timeout=90)
    if response.status_code == 429:
        raise RuntimeError("Groq free-tier rate limit reached. Wait for the quota window to reset.")
    response.raise_for_status()
    raw = response.json()["choices"][0]["message"]["content"].strip()
    if raw.startswith(chr(96) * 3):
        raw = raw.partition("\n")[2]
    if raw.endswith(chr(96) * 3):
        raw = raw[:-3]
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Appraisal model returned invalid JSON.")
    return json.loads(raw[start:end + 1])


def check_quotes(data: dict[str, Any], source: str, tool: str) -> dict[str, Any]:
    allowed = {"benefit", "no_clear_difference", "harm", "mixed", "unclear", "not_reported"}
    outcomes = []
    for item in (data.get("outcomes") or [])[:12]:
        if not isinstance(item, dict):
            continue
        group = str(item.get("outcome_group") or "unclear").lower()
        if group not in allowed:
            group = "unclear"
        quotes = []
        for q in (item.get("evidence_quotes") or [])[:4]:
            excerpt = tidy(str(q.get("excerpt") or "")) if isinstance(q, dict) else ""
            if excerpt and excerpt.lower() in source.lower():
                quotes.append({"section": tidy(str(q.get("section") or "Full text")), "excerpt": excerpt[:400],
                               "location": tidy(str(q.get("location") or ""))})
        outcome = {"outcome": tidy(str(item.get("outcome") or "Outcome not specified")), "outcome_group": group, "evidence_quotes": quotes}
        for field in ("endpoint", "timepoint", "population_n", "events_or_summary", "effect_measure", "effect_estimate",
                      "confidence_interval", "p_value", "statistical_significance", "clinical_interpretation"):
            outcome[field] = tidy(str(item.get(field) or ""))
        outcomes.append(outcome)

    risk = data.get("risk_of_bias") if isinstance(data.get("risk_of_bias"), dict) else {}
    allowed_judgements = {"low", "some_concerns", "high", "unclear", "not_applicable"}
    domains = []
    for item in (risk.get("domains") or [])[:12]:
        if not isinstance(item, dict):
            continue
        judgement = str(item.get("judgement") or "unclear").lower().replace(" ", "_")
        if judgement not in allowed_judgements:
            judgement = "unclear"
        quotes = []
        for q in (item.get("evidence_quotes") or [])[:3]:
            excerpt = tidy(str(q.get("excerpt") or "")) if isinstance(q, dict) else ""
            if excerpt and excerpt.lower() in source.lower():
                quotes.append({"section": tidy(str(q.get("section") or "Full text")), "excerpt": excerpt[:400]})
        domains.append({"domain": tidy(str(item.get("domain") or "Domain")), "judgement": judgement,
                        "rationale": tidy(str(item.get("rationale") or "")), "evidence_quotes": quotes})
    overall = str(risk.get("overall_judgement") or "unclear").lower().replace(" ", "_")
    if overall not in allowed_judgements or len(domains) < 2:
        overall = "not_assessable"
    return {
      "status": "appraised", "study_design_verified": tidy(str(data.get("study_design_verified") or "")),
      "population": tidy(str(data.get("population") or "")), "intervention": tidy(str(data.get("intervention") or "")),
      "comparator": tidy(str(data.get("comparator") or "")), "follow_up": tidy(str(data.get("follow_up") or "")),
      "outcomes": outcomes, "outcome_groups": list(dict.fromkeys(x["outcome_group"] for x in outcomes)) or ["unclear"],
      "main_findings": tidy(str(data.get("main_findings") or "")),
      "methods_assessment": tidy(str(data.get("methods_assessment") or "")),
      "limitations_reported": [tidy(str(x)) for x in (data.get("limitations_reported") or [])[:8]],
      "funding_and_conflicts": tidy(str(data.get("funding_and_conflicts") or "Not identified in extracted text")),
      "risk_of_bias": {"tool": tool, "overall_judgement": overall, "domains": domains,
        "note": "AI-assisted preliminary domain judgements; verify against the official instrument and complete article."},
      "appraisal_warnings": [tidy(str(x)) for x in (data.get("appraisal_warnings") or [])[:8]],
      "evidence_integrity": {"verified_excerpt_count": sum(len(x["evidence_quotes"]) for x in outcomes) + sum(len(x["evidence_quotes"]) for x in domains),
        "unverified_quotes_removed": True, "full_text_characters_reviewed": len(source)}
    }


async def appraise_full_text(record: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(35, connect=12), follow_redirects=True,
      headers={"User-Agent": "OncoEvidenceAI/0.4 evidence review"}) as client:
        meta = await resolve_pmc(client, record)
        if not meta:
            return {"status": "full_text_unavailable", "reason": "No matching Europe PMC full-text record was found.", "record_key": get_key(record)}
        pmcid = tidy(str(meta.get("pmcid") or ""))
        if not pmcid:
            return {"status": "full_text_unavailable", "reason": "No PMC full-text identifier is available.", "record_key": get_key(record)}
        if str(meta.get("isOpenAccess") or "").upper() != "Y" or str(meta.get("inEPMC") or "").upper() != "Y":
            return {"status": "full_text_unavailable", "reason": "Europe PMC does not mark this paper as reusable open-access full text.", "pmcid": pmcid, "record_key": get_key(record)}
        response = await client.get(EPMC + "/" + pmcid + "/fullTextXML")
        if response.status_code == 404:
            return {"status": "full_text_unavailable", "reason": "Reusable full-text XML is not exposed for this paper.", "pmcid": pmcid, "record_key": get_key(record)}
        response.raise_for_status()
        full = parse_pmc_xml(response.text)
        if len(full["body"]) < 1200:
            return {"status": "full_text_incomplete", "reason": "Retrieved full text is too short for appraisal.", "pmcid": pmcid, "record_key": get_key(record)}
        paper = {**record, "pmcid": pmcid}
        design = appraise_abstract(paper).get("study_design", "Unclear from abstract")
        recommendation = recommend_appraisal_tool(paper, design)
        tool = recommendation.get("recommended_appraisal_tool", "JBI")
        data = await call_groq(client, paper, full, tool, domains_for(tool))
        source = full["title"] + "\n" + full["abstract"] + "\n" + full["body"]
        appraisal = check_quotes(data, source, tool)
        appraisal.update({"retrieved_from": "Europe PMC fullTextXML", "pmcid": pmcid,
          "license": full["license"] or tidy(str(meta.get("license") or "")),
          "framework_url": recommendation.get("appraisal_tool_url", ""),
          "framework_note": recommendation.get("appraisal_tool_note", ""),
          "model": os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")})
        return {"status": "appraised", "record_key": get_key(record), "pmcid": pmcid, "appraisal": appraisal}
