# ReplicAudit

**Open, automated replication audits of published empirical research. Free to run.**
Website: https://sahiljangra12.github.io/replicaudit/

Someone submits a paper on the website: its DOI, the replication package, the paper PDF and any supplementary files, as links or uploads. ReplicAudit runs the authors' own code, checks every reported estimate against the paper, rebuilds what it can't run, stress-tests the headline result, and shows the results on the website. Every script, log and checksum is public, and a person reviews each audit before it joins the registry.

## How it works

```
Website (GitHub Pages)  ──►  intake function (Netlify, free)  ──►  request and files stored (Netlify Blobs)
        ▲                                                              │
        │                                                              ▼
 status page shows results  ◄──  results saved  ◄──  GitHub Actions (free on public repos)
                                                        1. fetch materials, checksum every file
                                                        2. run the authors' R / Python code as published
                                                           and find every reported number in its output
                                                        3. AI stage: Stata → Python, anything not found,
                                                           robustness checks (free open-source model on
                                                           the same machine, or Claude if a key is set)
```

* **No account needed** to submit. The visitor never leaves the website.
* **Estimates to check** can be typed, pasted from a spreadsheet, picked from suggestions (the website reads the PDF's tables in the browser), or left empty (the same table reader runs on the server).
* **Free:** standard GitHub Actions runners are free on public repositories, and the intake function fits in Netlify's free plan. The AI stage uses an open-source model (`qwen2.5-coder:7b` by default, set by the `OLLAMA_MODEL` variable) served by Ollama on the runner. If an `ANTHROPIC_API_KEY` secret is added, Claude is used instead.
* **Stata:** there is no free Stata, so Stata analyses are translated to Python by the AI stage.

## Maintainer setup (once)

No tokens or secrets are needed. Uploads and requests are kept in Netlify Blobs, and the GitHub workflows identify themselves to the intake API with GitHub's own OIDC identity token (only workflows on `main` of this repository are accepted).

1. **Netlify** (project `replicaudit-intake`): Project configuration → Build & deploy → **Link repository** → GitHub → `sahiljangra12/replicaudit` (branch `main`). Every push then deploys the intake API.
2. **GitHub** → this repository → Settings → Pages → Source → **GitHub Actions**.

How a request flows: website → intake API (stores files and the request) → the **Collect requests** workflow (every 5 minutes) opens the request as an issue and starts **Run audit** → the *fetch* job downloads the files and deletes them from the store → the *audit* job runs the code with no credentials → the *publish* job saves the results and rebuilds the website.

Optional: secret `ANTHROPIC_API_KEY` to use Claude instead of the free model; variable `OLLAMA_MODEL` to choose a different free model.

## Reviewing and publishing

New audits appear at once on the requester's status page and as an *unreviewed* page on the website, but not in the registry. Nobody is emailed. To publish one:

```bash
python -m replicaudit publish audits/<slug> --reviewer "Your Name"
```

This marks the audit as published and creates `audits/<slug>/review.md`. Write your assessment there, and add your own suggestions under `## Suggestions`, one per line. Check the estimates, the scripts behind anything not reproduced, and the robustness variants (delete any variant that isn't a defensible alternative). Then commit and push. The website rebuilds itself and the audit gets:

* its page in the registry, with the estimates table, the "audit vs paper" chart and the robustness chart,
* a **Suggestions** section: automatic ones from fixed rules (each states the finding it rests on) plus yours,
* a typeset **PDF report** (LaTeX, house style in `latex/style.tex`), downloadable from the page.

To preview a report locally: `python -m replicaudit report-pdf audits/<slug>`.

## Running locally

```bash
pip install -r requirements.txt
npm install --prefix tools --ignore-scripts      # PDF table reader (optional)

# no AI: run the authors' code, find the estimates
python -m replicaudit run --backend none --package path/to/package --paper paper.pdf --out runs/mypaper

# with a free local model (Ollama running) or Claude (ANTHROPIC_API_KEY set): --backend auto
python -m replicaudit run --backend auto --package path/to/package --claims claims.csv --out runs/mypaper

# replay a published audit exactly, from its saved model answers
python -m replicaudit run --backend replay --fixtures audits/<slug>/llm_log --package path/to/package \
    --claims audits/<slug>/claims_submitted.csv --out runs/replay

python -m replicaudit site --out _site            # build the website
```

## Verdicts

| Verdict | Meaning |
|---|---|
| Reproduced | b and se equal the paper's after rounding to its printed decimals (N too, where reported) |
| Close | same sign and within 5%, or exact b with a different N |
| Size differs / Sign differs | direction holds but size doesn't / sign reversed |
| Not rebuilt | the AI stage could not produce a working script |
| Not found | the number was not in the authors' outputs and no rebuild succeeded (not evidence of an error) |

Each estimate also shows **how** it was checked: *authors' own code* or *AI rebuild*. A headline result is **fragile** when fewer than 75% of robustness variants keep its sign and 5% significance. The full protocol is on the [Methods](https://sahiljangra12.github.io/replicaudit/methods.html) page.

## Safeguards

* Authors' code and model-written scripts run with credentials removed from their environment and with time limits. The job that runs them can only read the repository; a separate job saves the results.
* Only the *fetch* job can read uploaded files (via its OIDC identity); the *audit* job that runs submitted code has no identity token and read-only repository access.
* Scripts that contain the paper's reported value as a literal are rejected.
* Uploaded files and authors' data are never published; derived data files are not saved.
* Nothing joins the registry without human review.

## Layout

```
replicaudit/   fetch.py (DOI/Zenodo/Dataverse/OSF/GitHub/zip/uploads) · intake.py · runcode.py (authors' code)
               match.py (find estimates in output) · pipeline.py · backends.py · sandbox.py · compare.py
               suggest.py (suggestions) · figures.py · latex.py (PDF report) · prompts.py · report.py · site.py · cli.py
latex/         style.tex — the report's LaTeX style
site_src/      website styles and scripts (form, PDF estimate finder, status page) + bundled pdf.js
netlify/       intake function (Netlify builds only this folder) (website → stored files + request queue)
tools/         server-side PDF table reader (same code as the website)
audits/        one folder per audit
.github/       workflows (audit, website, tests) and the request form
```

## Licence

Code: MIT. Audit reports: CC BY 4.0. Bundled pdf.js: Apache-2.0. Please cite using `CITATION.cff`.
