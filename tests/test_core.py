from replicaudit.compare import robustness_summary, target_literals, verdict
from replicaudit.sandbox import extract_code


def test_exact_and_rounding():
    assert verdict("-.042", ".011", -0.04213, 0.01104, 1200, 1200)["verdict"] == "exact"
    assert verdict("-.042", ".011", -0.04213, 0.01104, 1200, 1250)["verdict"] == "close"  # N differs
    assert verdict("-.042", ".011", -0.0435, 0.011)["verdict"] == "close"
    assert verdict("-.042", ".011", -0.090, 0.011)["verdict"] == "same_sign"
    assert verdict("-.042", ".011", 0.010, 0.009)["verdict"] == "different"
    assert verdict("-.042", ".011", None, None)["verdict"] == "failed"


def test_hardcode_guard():
    lits = target_literals("-.042")
    assert "-0.042" in lits and "-.042" in lits
    assert target_literals("0.1") == []  # too short to police


def test_extract_code():
    assert extract_code("text\n```python\nprint(1)\n```\nnotes").strip() == "print(1)"
    assert extract_code("no code here") is None


def test_robustness_summary():
    s = robustness_summary(-1.0, [{"b": -1, "p": 0.01}, {"b": 0.5, "p": 0.3}, {"error": "x"}])
    assert s["n"] == 2 and s["n_failed"] == 1 and s["share_same_sign_sig05"] == 0.5 and s["fragile"]


def test_issue_form_parsing():
    from replicaudit.intake import claims_from_csv_text, first_link, parse_issue_form, slugify
    body = ("### Paper title\n\nA study of wetlands\n\n### Authors\n\nRivera, A.; Okafor, B.\n\n"
            "### Journal and year\n\nScience 2026\n\n### Paper DOI\n\n10.1/abc\n\n"
            "### Replication package\n\nsee [pkg.zip](https://github.com/user-attachments/files/1/pkg.zip)\n\n"
            "### Supplementary materials\n\n_No response_\n")
    s = parse_issue_form(body)
    assert s["title"] == "A study of wetlands" and s["supplement"] is None
    assert first_link(s["package"]) == "https://github.com/user-attachments/files/1/pkg.zip"
    assert first_link("10.7910/DVN/ABC") == "10.7910/DVN/ABC"
    assert slugify(s) == "rivera-2026-study-wetlands"


def test_claims_csv(tmp_path):
    from replicaudit.intake import claims_from_csv_text
    from replicaudit.pipeline import load_claims
    p = claims_from_csv_text("```csv\nT1,\"x\",-.01,.002,10,true\n```", tmp_path / "c.csv")
    c = load_claims(p)
    assert c[0]["b"] == "-.01" and c[0]["main"] is True
