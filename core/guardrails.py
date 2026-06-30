"""
core/guardrails.py
Deterministic, non-LLM guardrail checks that run on every agent output
BEFORE it is allowed to move to the next stage of the pipeline. These are
intentionally simple/explainable (not another LLM call) so they are fast,
auditable, and cannot be talked out of their job by a clever prompt.
"""
import re

PII_PATTERNS = [
    (r"\b\d{3}-\d{2}-\d{4}\b", "possible SSN-like pattern"),
    (r"\b\d{10}\b", "possible raw phone number"),
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email address"),
    (r"\b\d{12,19}\b", "possible card/account number"),
]

UNLABELLED_STAT_PATTERN = re.compile(r"\b\d{1,3}(\.\d+)?%\b")


def check_pii(text: str) -> list:
    findings = []
    for pattern, label in PII_PATTERNS:
        if re.search(pattern, text or ""):
            findings.append(label)
    return findings


def check_scope(agent_name: str, parsed_output: dict) -> list:
    """Flags an agent producing content outside its declared lane (cheap heuristic)."""
    violations = []
    if not parsed_output:
        return ["output was not valid JSON — cannot verify scope"]
    text_blob = str(parsed_output).lower()
    forbidden_terms = {
        "market_analysis": ["roi judgment", "hard_stop"],
        "financial_analysis": ["competitive_threats", "hard_stop"],
        "risk_assessment": ["roi_judgment", "competitive_threats"],
    }
    for term in forbidden_terms.get(agent_name, []):
        if term in text_blob:
            violations.append(f"{agent_name} output referenced out-of-scope field '{term}'")
    return violations


def check_unlabelled_numbers(agent_name: str, raw_text: str) -> list:
    """Heuristic: if a specialist output contains percentage/number claims with no nearby
    'assumption' marker anywhere in the JSON, flag it for human review rather than blocking."""
    if agent_name == "strategy_synthesis" or agent_name == "evaluation" or agent_name == "router":
        return []
    has_numbers = bool(UNLABELLED_STAT_PATTERN.search(raw_text or ""))
    has_assumption_marker = "assumption" in (raw_text or "").lower()
    if has_numbers and not has_assumption_marker:
        return ["numeric claim(s) detected with no 'assumption' labelling anywhere in output"]
    return []


def run_guardrails(agent_name: str, raw_text: str, parsed_output: dict) -> dict:
    findings = {
        "pii_findings": check_pii(raw_text),
        "scope_violations": check_scope(agent_name, parsed_output),
        "unlabelled_number_warnings": check_unlabelled_numbers(agent_name, raw_text),
    }
    findings["blocked"] = bool(findings["pii_findings"]) or bool(findings["scope_violations"])
    findings["status"] = "BLOCKED" if findings["blocked"] else (
        "WARN" if findings["unlabelled_number_warnings"] else "PASS"
    )
    return findings
