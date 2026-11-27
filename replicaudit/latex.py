"""Typeset the published audit as a LaTeX report (PDF), in the house style (latex/style.tex).

    python -m replicaudit report-pdf audits/<slug> --out build/<slug>
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path

from .compare import VERDICTS, stars
from .figures import fig_deviation, fig_robustness
from .site import METHOD, SHORT, front_matter, summarize
from .suggest import auto_suggestions, reviewer_suggestions, strip_suggestions

STYLE = Path(__file__).resolve().parent.parent / "latex" / "style.tex"
SITE = "https://sahiljangra12.github.io/replicaudit"
REPO = "https://github.com/sahiljangra12/replicaudit"

_TEX = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
        "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}", "<": r"\textless{}", ">": r"\textgreater{}"}


def tex(s) -> str:
    s = "" if s is None else str(s)
    s = s.replace("\u2212", "-").replace("\u2013", "--").replace("\u2014", "---")
    return "".join(_TEX.get(ch, ch) for ch in s)


def md(text: str) -> str:
    """Markdown subset to LaTeX: paragraphs, bullet lists, **bold**, *italic*, `code`, [links](url)."""
    out, para, items = [], [], []

    def inline(s):
        links = []

        def keep(m):
            links.append((m.group(1), m.group(2)))
            return f"\x00{len(links) - 1}\x00"
        s = re.sub(r"\[(.+?)\]\((https?://[^\s)]+)\)", keep, s)
        s = tex(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
        s = re.sub(r"\*(.+?)\*", r"\\emph{\1}", s)
        s = re.sub(r"`(.+?)`", r"\\texttt{\1}", s)
        return re.sub("\x00(\\d+)\x00", lambda m: f"\\href{{{links[int(m.group(1))][1]}}}{{{tex(links[int(m.group(1))][0])}}}", s)

    def flush():
        if para:
            out.append(inline(" ".join(para)) + "\n")
            para.clear()
        if items:
            out.append("\\begin{itemize}\n" + "".join(f"\\item {inline(i)}\n" for i in items) + "\\end{itemize}\n")
            items.clear()
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            flush()
        elif s.startswith(("- ", "* ")):
            if para:
                flush()
            items.append(s[2:])
        elif s.startswith("#"):
            flush()
            out.append(f"\\subsection*{{{inline(s.lstrip('#').strip())}}}\n")
        else:
            para.append(s)
    flush()
    return "\n".join(out)


def _num(x, d=4):
    return "---" if x is None else f"{x:.{d}f}"


def build_tex(adir: Path, out: Path) -> Path:
    adir, out = Path(adir), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    sub = json.loads((adir / "submission.json").read_text())
    au = json.loads((adir / "audit.json").read_text())
    rmeta, rbody = front_matter((adir / "review.md").read_text()) if (adir / "review.md").exists() else ({}, "")
    a = {"dir": adir, "slug": adir.name, "sub": sub, "audit": au, "review": (rmeta, rbody), "response": ({}, "")}
    s = summarize(a)
    claims = au.get("claims", [])
    ac = au.get("authors_code") or {}
    pkg = sub.get("package") or {}
    doi = (sub.get("doi") or "").replace("https://doi.org/", "")
    shutil.copy(STYLE, out / "style.tex")

    figs = []
    if claims:
        fig_deviation(claims, out / "fig_estimates.pdf")
        figs.append("estimates")
    head = s["head"]
    R = (head or {}).get("robustness") or {}
    if R.get("variants") and (head.get("robust_base") or head.get("rebuilt")):
        fig_robustness(head.get("robust_base") or head["rebuilt"], R["variants"], out / "fig_robustness.pdf")
        figs.append("robustness")

    c = s["counts"]
    rs = s["rs"]
    auto = auto_suggestions(au, sub)
    from_reviewer = reviewer_suggestions(rbody)
    assessment = strip_suggestions(rbody)
    published = sub.get("status") == "published"
    rdate = rmeta.get("date") or date.today().isoformat()

    L = []
    w = L.append
    w(r"\documentclass[11pt]{article}")
    w(r"\input{style.tex}")
    w(r"\lhead{\small ReplicAudit --- replication audit}")
    w(r"\rhead{\small " + tex(rmeta.get("reviewer", "ReplicAudit")) + "}")
    w(r"\begin{document}")
    w(r"\begin{center}")
    w(r"{\LARGE\bfseries Replication audit of\\[3pt] ``" + tex(sub.get("title")) + r"''}\\[7pt]")
    w(r"{\large " + tex(sub.get("authors")) + r" \quad$\cdot$\quad \emph{" + tex(sub.get("journal_year")) + r"}}\\[5pt]")
    w(r"\href{https://doi.org/" + doi + r"}{doi:" + tex(doi) + r"}\\[8pt]")
    w(r"{\small Reviewed by " + tex(rmeta.get("reviewer", "---")) + r" \quad$\cdot$\quad " + tex(rdate) +
      r" \quad$\cdot$\quad ReplicAudit " + tex((au.get("environment") or {}).get("replicaudit", "")) + r"}")
    if not published:
        w(r"\\[6pt]{\color{red}\bfseries DRAFT --- not yet reviewed. Do not cite.}")
    w(r"\end{center}")

    # summary
    w(r"\begin{summarybox}\small\begin{itemize}[leftmargin=12pt]")
    w(r"\item \textbf{Reproduction.} " + f"{c.get('exact', 0)} of {s['n']} reported estimates were reproduced to the precision printed in the paper"
      + (f"; {c.get('not_found', 0) + c.get('failed', 0)} could not be found or rebuilt" if c.get('not_found', 0) + c.get('failed', 0) else "")
      + (f"; {c.get('close', 0) + c.get('same_sign', 0) + c.get('different', 0)} differ" if c.get('close', 0) + c.get('same_sign', 0) + c.get('different', 0) else "") + ".")
    if ac:
        w(r"\item \textbf{Authors' code.} " + tex(f"The {ac.get('language') or ''} code ") + tex({
            "ran": "ran without errors when run unchanged",
            "ran with errors": "ran, with errors in some scripts",
            "needs translation": "is Stata; the analysis was translated to Python by the AI stage",
            "no code": "was not found in the package"}.get(ac.get("status"), ac.get("status", ""))) +
          f"; {ac.get('found', 0)} estimates appeared directly in its output.")
    if rs.get("n"):
        w(r"\item \textbf{Robustness.} " + tex(f"The headline estimate ({head['id']}) kept its sign and 5% significance in "
                                               f"{rs['share_same_sign_sig05']:.0%} of {rs['n']} alternative specifications") +
          (r" --- \textbf{fragile}." if rs.get("fragile") else "."))
    if assessment.strip():
        first = re.split(r"(?<=[.!?])\s", assessment.strip().split("\n\n")[0])[0]
        w(r"\item \textbf{Reviewer.} " + tex(first))
    w(r"\end{itemize}\end{summarybox}")

    # 1 materials
    w(r"\section{The paper and the materials audited}")
    w(r"\begin{tabularx}{\textwidth}{@{}lX@{}}\toprule")
    rows = [("Paper", f"{sub.get('authors', '')}, {sub.get('journal_year', '')}"),
            ("DOI", doi),
            ("Replication package", ("uploaded file (kept private)" if str(pkg.get("source", "")).startswith("upload://") else pkg.get("source", "---"))),
            ("Version / commit", pkg.get("version") or pkg.get("commit") or "---"),
            ("Files fingerprinted", f"{len(pkg.get('manifest', []))} files; SHA-256 of manifest {pkg.get('package_sha256', '')[:24]}..."),
            ("Supplementary files", ", ".join((x.get("file") or "link") for x in sub.get("supplement") or [] if isinstance(x, dict)) or "---"),
            ("Estimates listed by", {"pdf_tables": "the PDF table reader", "model": "the model, from the paper"}.get(
                claims[0].get("source") if claims else None, "the submitter")),
            ("AI model", au.get("model") or ("none" if au.get("backend") in (None, "none") else au.get("backend"))),
            ("Software", f"Python {(au.get('environment') or {}).get('python', '')}, pandas {(au.get('environment') or {}).get('pandas', '')}, pyfixest {(au.get('environment') or {}).get('pyfixest', '')}")]
    for k, v in rows:
        w(r"\textbf{" + tex(k) + "} & " + tex(v) + r" \\")
    w(r"\bottomrule\end{tabularx}")

    # 2 method
    w(r"\section{How the audit was done}")
    w(r"The audit follows the published ReplicAudit protocol (\href{" + SITE + r"/methods.html}{Methods}). "
      r"First, the authors' own code is run unchanged on a clean machine, and every reported estimate is searched for in its output: "
      r"the coefficient followed closely by its standard error, both rounded to the decimals the paper prints. "
      r"Second, where the code cannot be run (for example Stata) or an estimate is not found, a language model rebuilds the analysis in Python, "
      r"following the authors' code; scripts that type in the paper's numbers are rejected. "
      r"Third, the headline estimate is re-estimated under alternative specifications a careful referee could ask for. "
      r"A person reviewed the result before publication.")

    # 3 results
    w(r"\section{Results: reported estimates}")
    w(r"{\small\begin{longtable}{@{}p{1.25cm}p{5.3cm}>{\raggedleft\arraybackslash}p{1.45cm}>{\raggedleft\arraybackslash}p{1.75cm}p{1.9cm}p{2.0cm}@{}}")
    w(r"\toprule \textbf{ID} & \textbf{Estimate} & \textbf{Paper} & \textbf{Audit} & \textbf{Verdict} & \textbf{How} \\ \midrule\endhead")
    for cl in claims:
        rb = cl.get("rebuilt") or {}
        cm = cl.get("compare") or {}
        paper = tex(cl["b"]) + (r"\newline{\footnotesize(" + tex(cl["se"]) + ")}" if cl.get("se") else "")
        mine = (_num(rb.get("b")) + tex(stars(cm.get("p"))) + r"\newline{\footnotesize(" + _num(rb.get("se")) + ")}") if rb.get("b") is not None else "---"
        w(r"\texttt{" + tex(cl["id"]) + "} & " + tex(cl["description"]) + (r" \textbf{(headline)}" if cl.get("main") else "") +
          r" & " + paper + r" & " + mine + " & " +
          tex(SHORT.get(cm.get("verdict"), cm.get("verdict", ""))) + " & " + tex(METHOD.get(cm.get("method"), "---")) + r" \\")
    w(r"\bottomrule\end{longtable}}")
    w(r"\noindent{\footnotesize Standard errors in parentheses. Stars on audit values: *** $p<0.01$, ** $p<0.05$, * $p<0.10$. "
      r"Verdicts: " + "; ".join(f"\\emph{{{tex(SHORT[k])}}}: {tex(VERDICTS[k].lower())}" for k in ("exact", "close", "same_sign", "different", "not_found")) + ".}")
    if "estimates" in figs:
        w(r"\begin{figure}[H]\centering\includegraphics[width=0.92\textwidth]{fig_estimates.pdf}")
        w(r"\caption{Distance between each audited estimate and the published one, in units of the paper's standard error. "
          r"The shaded band ($\pm0.5$) is within rounding; green points were reproduced, amber/red differ, grey were not found.}\end{figure}")

    # 4 authors' code
    if ac.get("ran"):
        w(r"\section{Running the authors' code}")
        w(r"\begin{tabularx}{\textwidth}{@{}Xrr@{}}\toprule \textbf{Script} & \textbf{Exit code} & \textbf{Time (s)} \\ \midrule")
        for r in ac["ran"]:
            w(r"\file{" + tex(r["script"]) + "} & " + tex(r["exit"]) + " & " + tex(r["seconds"]) + r" \\")
        w(r"\bottomrule\end{tabularx}")
        if ac.get("changed_files"):
            w(r"\noindent The only change made: hard-coded working-directory lines were disabled in " +
              ", ".join(r"\file{" + tex(f) + "}" for f in ac["changed_files"]) + ".")

    # 5 robustness
    if R.get("variants"):
        w(r"\section{Robustness of the headline result}")
        w(tex(f"Headline estimate {head['id']}: {head['description']}."))
        if "robustness" in figs:
            w(r"\begin{figure}[H]\centering\includegraphics[width=0.92\textwidth]{fig_robustness.pdf}")
            w(r"\caption{The headline estimate under alternative specifications, with 95\% confidence intervals. "
              r"Blue: same sign and significant at 5\%; red: not.}\end{figure}")
        w(r"{\small\begin{longtable}{@{}p{4.2cm}p{7.2cm}rr@{}}\toprule \textbf{Specification} & \textbf{Why} & \textbf{b} & \textbf{se} \\ \midrule\endhead")
        for v in R["variants"]:
            w(tex(v.get("name")) + " & " + tex(v.get("why") or "") + " & " + (_num(v.get("b")) + tex(stars(v.get("p"))) if v.get("b") is not None else "failed") +
              " & " + _num(v.get("se")) + r" \\")
        w(r"\bottomrule\end{longtable}}")

    # 6 assessment
    if assessment.strip():
        w(r"\section{Reviewer's assessment}")
        w(md(assessment))

    # 7 suggestions
    w(r"\section{Suggestions}")
    if not auto and not from_reviewer:
        w("No suggestions.")
    groups = {}
    for x in auto:
        groups.setdefault(x["area"], []).append(x)
    for area in ("Estimates", "Robustness", "Package", "Readers"):
        if area not in groups:
            continue
        w(r"\subsection*{" + {"Estimates": "Reported estimates", "Robustness": "Robustness", "Package": "Replication package",
                              "Readers": "For readers"}[area] + "}")
        w(r"\begin{itemize}")
        for x in groups[area]:
            w(r"\item " + tex(x["text"]) + r" {\footnotesize\color{gray}(" + tex(x["why"]) + ")}")
        w(r"\end{itemize}")
    if from_reviewer:
        w(r"\subsection*{From the reviewer}\begin{itemize}")
        for x in from_reviewer:
            w(r"\item " + md(x).strip())
        w(r"\end{itemize}")

    # 8 limitations + reproducibility
    w(r"\section{Limitations}")
    w(r"\begin{itemize}"
      r"\item This audit checks computational reproducibility and robustness with the authors' data. It does not test whether the result replicates in new data."
      r"\item ``Not found'' means the number did not appear in the code's output in a recognisable form. It is not evidence of an error."
      r"\item Robustness specifications were chosen after seeing the data and cannot cover every defensible analysis."
      r"\item Where an AI model rebuilt the analysis, small numerical differences can come from software defaults (for example small-sample corrections).\end{itemize}")
    w(r"\section*{Reproducing this audit}")
    w(r"All scripts, logs, model prompts and answers, and file checksums are at \url{" + REPO + "/tree/main/audits/" + adir.name + r"}. "
      r"The audit page is \url{" + SITE + "/audits/" + adir.name + r"/}.")
    w(r"\end{document}")
    (out / "report.tex").write_text("\n".join(L), encoding="utf-8")
    return out / "report.tex"


def compile_pdf(tex_path: Path) -> Path | None:
    tex_path = Path(tex_path)
    engines = [["tectonic", "--keep-logs", tex_path.name], ["latexmk", "-pdf", "-interaction=nonstopmode", tex_path.name],
               ["pdflatex", "-interaction=nonstopmode", tex_path.name]]
    for cmd in engines:
        if not shutil.which(cmd[0]):
            continue
        runs = 2 if cmd[0] == "pdflatex" else 1
        for _ in range(runs):
            subprocess.run(cmd, cwd=tex_path.parent, capture_output=True, text=True, timeout=600)
        pdf = tex_path.with_suffix(".pdf")
        if pdf.exists():
            return pdf
    return None
