# Google Colab inference for OncoEvidence AI

## Open the notebook
[Open OncoEvidence AI Colab notebook](https://colab.research.google.com/github/vishnuvcr/onco-evidence-ai/blob/main/colab/OncoEvidence_AI_Free_FullText_Appraisal.ipynb)

## Workflow
1. Run a literature search on the [OncoEvidence AI website](https://vishnuvcr.github.io/onco-evidence-ai/).
2. In **Full-text appraisal engine**, choose **Export for free Colab**.
3. Open the notebook above in Google Colab. Set **Runtime → Change runtime type → GPU** (GPU availability depends on Google's free-tier capacity).
4. Run the cells in order. Upload the exported JSON when prompted and approve Google Drive mounting.
5. The notebook downloads only reusable open-access full text exposed by Europe PMC. It writes one atomic JSON checkpoint per completed paper to `MyDrive/OncoEvidenceAI/checkpoints`.
6. If the runtime disconnects, reopen the same notebook, mount the same Drive, upload the same search export, and rerun. Existing completed checkpoints are skipped.
7. Download `oncoevidence_colab_results.json` when the run completes. Return to the same website search and choose **Import Colab results**.

## Model and appraisal safeguards
- The notebook uses local quantized open-weight inference; it does not call Groq or require an inference API key.
- It reads full accessible article sections and tables, extracts section-level evidence, synthesizes outcome-level findings, and validates every retained quotation against the retrieved article text.
- It carries forward the search record's recommended appraisal tool when present, with design-based fallback routing.
- AI risk-of-bias judgements are preliminary. They must be checked by reviewers against the official instrument; the notebook does not claim to replace independent RoB assessment.
- Non-OA / inaccessible full text is explicitly marked unavailable. No abstract-only substitute is silently treated as a full-text appraisal.

## Free-tier constraints
Google Colab free compute is not guaranteed or unlimited. GPU type/availability and session lifetime vary; free sessions may end before the maximum runtime. Drive checkpoints make the process restartable, not continuous or guaranteed. See [Google's Colab FAQ](https://research.google.com/colaboratory/faq.html).

## Data handling
Only public literature metadata and publicly reusable OA article text should be submitted. Do not upload patient-identifiable or confidential clinical data.
