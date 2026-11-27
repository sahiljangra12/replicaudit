"""Prompt templates. Kept in one place so they can be versioned and audited."""

SYSTEM = """You are a careful replication engineer for empirical research papers.
You write plain Python 3 scripts (pandas, numpy, statsmodels, pyfixest, scipy, pyreadstat are installed).
Rules:
- Reply with exactly one ```python code block, then at most three short lines of notes.
- Read inputs only from the folders in the environment variables PACKAGE_DIR (the authors' package, read-only)
  and WORK_DIR (your working folder). Never use the network.
- The last line your script prints must be:  RESULT_JSON: {...}  (one line of valid JSON).
- Compute every number from the data. Never type a target value from the paper into the code.
- Match the authors' method exactly when you can see their code (sample rules, transformations,
  winsorizing, fixed effects, clustering, small-sample corrections). When Stata is translated,
  remember Stata `gen` makes float32 variables and reghdfe drops singleton groups by default.
"""

CLAIMS = """Below is the text of a research paper. List its main quantitative claims that a replication
should check: the headline regression coefficients (with standard errors) in the main tables, and key
robustness or mechanism estimates. At most {max_claims} claims.

Reply with one ```json block holding a list of objects with keys:
  id (short, e.g. "T1c3"), description (table, column, variable, outcome, specification),
  b (coefficient exactly as printed, as a string), se (as printed, string, or null),
  n (sample size if printed, else null), main (true for the paper's headline result).

PAPER TEXT:
{paper}
"""

PREP = """Write prepare.py. It must build ONE analysis dataset that can be used to re-estimate every claim
below, following the authors' own data-preparation code as closely as possible, and save it to
os.path.join(os.environ["WORK_DIR"], "analysis.parquet").
Finish with: print("RESULT_JSON: " + json.dumps({{"rows": len(df), "cols": df.shape[1]}}))

CLAIMS TO SUPPORT:
{claims}

REPLICATION PACKAGE:
{profile}
{feedback}"""

REBUILD = """Write a script that re-estimates this one claim from the prepared dataset
os.path.join(os.environ["WORK_DIR"], "analysis.parquet").

CLAIM {cid}: {description}
Reported in the paper: b = {b}, se = {se}, N = {n}

It must end with:
print("RESULT_JSON: " + json.dumps({{"b": <coefficient>, "se": <std. error>, "n": <observations used>}}))

PREPARED DATASET:
{frame}

AUTHORS' CODE (for the exact specification):
{code}
{feedback}"""

ROBUST = """This script reproduces claim {cid} ({description}):

```python
{script}
```

Propose {k} reasonable robustness checks a careful referee would ask for: different but defensible
choices for controls, sample, fixed effects, clustering, outcome measurement, outliers, and especially
checks for measurement or observation-process problems in the data. Each must be a full, runnable
variant of the script above that prints RESULT_JSON with b, se, n for the same coefficient.

Reply with one ```json block: a list of objects with keys name (short), why (one sentence), code (full script).

PREPARED DATASET:
{frame}
"""

FEEDBACK = """
YOUR PREVIOUS ATTEMPT (attempt {attempt}) did not work:
{problem}

Previous script:
```python
{script}
```
Fix it."""
