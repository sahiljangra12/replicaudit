# ReplicAudit

**Open, automated replication audits of published empirical research.**
Website: https://sahiljangra12.github.io/replicaudit/

ReplicAudit takes a published paper and its public replication package (data + code). It re-runs the analysis, checks every reported estimate against the paper, and tests whether the headline result survives reasonable alternative choices. Every script, model prompt, model answer and file checksum is published, and a person reviews each audit before it appears in the registry.

## How a paper gets audited

```
Submission form (GitHub issue)  ──►  maintainer adds label "run-audit"
        │
        ▼
GitHub Action, read-only job:  fetch package → checksums → claims → rebuild data → re-estimate → robustness
        │
        ▼
Pull request with audits/<slug>/  ──►  human review + authors invited to reply (≥14 days)
        │
        ▼
Merge with status "published"  ──►  website rebuilt and deployed by GitHub Pages
```

**Submitting:** fill in the form on the website's [Submit page](https://sahiljangra12.github.io/replicaudit/submit.html). It fills in the paper's details from its DOI, accepts each material as a link or a file (any number of supplementary files), reads chosen PDFs in the browser to suggest the estimates to check, and hands everything to a pre-filled GitHub request, which the submitter sends from their own account so the request is on the public record. The [GitHub form](https://github.com/sahiljangra12/replicaudit/issues/new?template=audit-request.yml) can also be used directly. It asks for:

| Item | How |
|---|---|
| Paper title, authors, journal, DOI | typed |
| Replication package (required) | DOI or link: Zenodo, Dataverse, OSF, GitHub repo, direct .zip, or attach a .zip ≤ 25 MB. Inner .zip/.rar/.7z/.tar.gz archives are unpacked. |
| Paper PDF | open-access link or attachment (not stored) |
| Supplementary materials | any number of links and/or files; PDFs are read for estimates, other files (.zip, .xlsx, .csv) join the package |
| Claims table (optional) | `id,description,b,se,n,main`, numbers exactly as printed; otherwise extracted from the PDF |

## Repository layout

```
replicaudit/          the pipeline
  fetch.py            download from DOI/Zenodo/Dataverse/OSF/GitHub/URL, unpack archives, SHA-256 manifest
  intake.py           parse the submission form → audits/<slug>/
  pipeline.py         profile → claims → prepare data → rebuild each claim → compare → robustness
  sandbox.py          runs model-written scripts in a separate process, no credentials, with a timeout
  compare.py          verdicts at the paper's reported precision
  backends.py         Claude (Anthropic API), any OpenAI-compatible server (e.g. Ollama), replay
  report.py, site.py  machine report and the website
audits/<slug>/        one folder per audit: submission.json, audit.json, results.csv, scripts/, llm_log/,
                      review.md (reviewer), author_response.md (authors)
site_src/             website stylesheet and script
.github/              submission form; workflows for audits, the website and tests
```

Authors' data and papers are **never committed**; only checksums, our scripts and our results are.

## Maintainer setup (once)

1. Repository **Settings → Secrets and variables → Actions**: add secret `ANTHROPIC_API_KEY`. Optionally add variable `REPLICAUDIT_MODEL` (default `claude-sonnet-5-5`).
2. **Settings → Pages → Source: GitHub Actions.**
3. **Settings → Actions → General → Workflow permissions:** allow GitHub Actions to create pull requests.
4. Create the labels `audit-request`, `run-audit` and `audit-result`.

## Publishing an audit (reviewer checklist)

In the pull request: check the claims against the paper, read the scripts behind every non-reproduced verdict, delete any robustness variant that is not a defensible alternative, and write `review.md`:

```
---
reviewer: Your Name
date: 2026-12-15
---
Short assessment in plain language.
```

Email the corresponding authors and record `"authors_contacted": "YYYY-MM-DD"` in `submission.json`. After 14 days or a reply, set `"status": "published"`, save any reply as `author_response.md`, and merge.

## Running locally

```bash
pip install -r requirements.txt

# with Claude (ANTHROPIC_API_KEY set)
python -m replicaudit run --package path/to/package --paper paper.pdf --out runs/mypaper

# with a free local model through Ollama
python -m replicaudit run --backend openai --model qwen2.5-coder:32b --base-url http://localhost:11434/v1 \
    --package path/to/package --claims claims.csv --out runs/mypaper

# replay a published audit exactly (no model): its saved answers are in audits/<slug>/llm_log
python -m replicaudit run --backend replay --fixtures audits/<slug>/llm_log \
    --package path/to/package --claims audits/<slug>/claims_submitted.csv --out runs/replay

# the website, including drafts
python -m replicaudit site --out _site --include-drafts
```

## Verdicts

| Verdict | Meaning |
|---|---|
| Reproduced | b and se equal the paper's after rounding to its printed decimals; N matches where reported |
| Close | same sign and within 5%, or exact b with a different N |
| Size differs | same sign, different magnitude |
| Sign differs | sign reversed |
| Not rebuilt | no working script within 4 attempts (a statement about the pipeline, not the paper) |

A headline result is **fragile** when fewer than 75% of robustness variants keep its sign and 5% significance. The full protocol is on the [Methods](https://sahiljangra12.github.io/replicaudit/methods.html) page.

## Safeguards

- Scripts that contain the paper's reported value as a literal are rejected.
- API keys and tokens are removed from every script's environment. The audit job has read-only repository access; a separate job opens the pull request.
- Issue text is passed to scripts through environment variables, never pasted into shell commands.
- Nothing is published without human review and an invitation to the authors to reply.

## Related work

CORE-Bench, REPRO-Bench, ReplicatorBench, PaperBench and ReplicationBench benchmark AI agents on reproduction tasks; the Institute for Replication runs human replication games. ReplicAudit runs audits on published literature, reports robustness alongside reproduction, and starts with environmental and sustainability research.

## Licence

Code: MIT. Audit reports: CC BY 4.0. Please cite using `CITATION.cff`.
