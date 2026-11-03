# OncoEvidence AI — simple Colab guide (no coding required)

## Open the notebook
[Tap here to open the one-click Google Colab notebook](https://colab.research.google.com/github/vishnuvcr/onco-evidence-ai/blob/main/colab/OncoEvidence_AI_Free_FullText_Appraisal.ipynb).

## Do these steps

1. Open the [OncoEvidence AI website](https://vishnuvcr.github.io/onco-evidence-ai/) and search for your clinical question.
2. In the **Full-text appraisal engine**, tap **Export for free Colab**. Keep the downloaded file.
3. Open the Colab notebook using the link above. Sign in to your Google account if asked.
4. If Google offers a GPU option, choose **Runtime → Change runtime type → GPU**. If no GPU is offered, try again later.
5. Find the large code box and tap its **▶ Run** button once.
6. When a file window appears, choose the file you downloaded in step 2.
7. Google will ask for permission to use Google Drive. Choose your Google account and allow access. Drive is used to save progress.
8. Wait while the papers are processed. At the end, Colab downloads a file named `oncoevidence_colab_results.json`.
9. Return to the same search on the website. Tap **Import Colab results** and choose that downloaded results file.

That's it. You do not need to edit or understand the code.

## If the process stops halfway

1. Open the same Colab notebook again.
2. Tap the same **▶ Run** button.
3. Upload the same original search export file.
4. Allow Google Drive access if asked.

The notebook checks its saved progress in `My Drive/OncoEvidenceAI/checkpoints` and skips papers already completed. Papers that failed are retried.

## What it appraises

- Retrieves reusable open-access full text from Europe PMC.
- Reads article sections and extracted tables, not just abstracts.
- Separates findings by outcome, including effect estimates, confidence intervals and timepoints where reported.
- Uses a design-appropriate risk-of-bias framework when one is identified.
- Verifies retained quotations against the retrieved article text.

AI risk-of-bias judgements are preliminary and must be checked against the official instrument by a reviewer. Papers without accessible reusable full text are marked unavailable, not guessed from abstracts.

## Free-use note

Google Colab is free, but free GPU availability, usage limits and session duration are not guaranteed. Sessions can stop early. Checkpoints allow you to resume, but cannot guarantee that every batch will finish in one session. [Google's official Colab FAQ](https://research.google.com/colaboratory/faq.html).

Only process public literature and reusable full-text articles. Do not upload patient-identifiable or confidential clinical information.
