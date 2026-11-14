"""Deterministic baseline assessment that runs without any AI.

The baseline gives every user an instant, reproducible result and grounds
the AI-generated strategy in concrete gaps rather than generic advice.
Control references are to NIST CSF 2.0 functions and CIS Controls v8.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import OrgProfile


@dataclass(frozen=True)
class Control:
    id: str
    name: str
    function: str  # NIST CSF 2.0 function
    cis: str       # CIS Controls v8 reference
    weight: int    # 1 (nice to have) .. 5 (foundational)
    why: str


CATALOG: tuple[Control, ...] = (
    Control("security_owner", "Named security owner and governance", "Govern", "CIS 14/17", 4,
            "Without an accountable owner, security work stalls and risk decisions go unmade."),
    Control("vendor_risk", "Third-party / vendor risk management", "Govern", "CIS 15", 3,
            "Suppliers and SaaS vendors are a leading source of breaches."),
    Control("asset_inventory", "Hardware, software and cloud asset inventory", "Identify", "CIS 1-2", 4,
            "You cannot protect what you do not know you have."),
    Control("vulnerability_scanning", "Continuous vulnerability scanning", "Identify", "CIS 7", 3,
            "Finds exploitable weaknesses before attackers do."),
    Control("mfa", "Multi-factor authentication everywhere", "Protect", "CIS 6", 5,
            "Stops the large majority of credential-stuffing and phishing account takeovers."),
    Control("least_privilege", "Least privilege and admin account separation", "Protect", "CIS 5-6", 4,
            "Limits blast radius when any single account is compromised."),
    Control("patch_management", "Timely patching of OS and applications", "Protect", "CIS 7", 5,
            "Known, unpatched vulnerabilities are a top initial-access vector."),
    Control("email_security", "Email filtering, SPF/DKIM/DMARC", "Protect", "CIS 9", 3,
            "Email remains the main delivery path for phishing and business email compromise."),
    Control("data_encryption", "Encryption of sensitive data at rest and in transit", "Protect", "CIS 3", 3,
            "Reduces the impact of lost devices and data exposure."),
    Control("network_segmentation", "Network segmentation", "Protect", "CIS 12-13", 3,
            "Slows lateral movement and contains ransomware."),
    Control("secure_sdlc", "Secure software development lifecycle", "Protect", "CIS 16", 2,
            "Prevents vulnerabilities in software you build from reaching production."),
    Control("security_training", "Security awareness training and phishing simulation", "Protect", "CIS 14", 3,
            "People are both the most targeted surface and the best early-warning sensor."),
    Control("edr", "Endpoint detection and response (EDR)", "Detect", "CIS 10/13", 4,
            "Detects and stops malware and hands-on-keyboard attackers on endpoints."),
    Control("central_logging", "Centralised logging and alerting (SIEM)", "Detect", "CIS 8", 3,
            "Without logs, incidents go unnoticed and cannot be investigated."),
    Control("incident_response_plan", "Tested incident response plan", "Respond", "CIS 17", 4,
            "A rehearsed plan cuts response time and cost during a real incident."),
    Control("offline_backups", "Immutable / offline backups with tested restores", "Recover", "CIS 11", 5,
            "The decisive control for surviving ransomware."),
)

CSF_FUNCTIONS = ("Govern", "Identify", "Protect", "Detect", "Respond", "Recover")

SENSITIVE_DATA = {"PHI", "Payment cards", "PII", "Financial", "Children's data", "Government / classified"}


def _priority_multiplier(control: Control, p: OrgProfile) -> float:
    """Raise the priority of a gap when the organisation's context makes it riskier."""
    m = 1.0
    data = set(p.data_types)
    infra = set(p.infrastructure)
    if control.id in {"data_encryption", "central_logging"} and data & SENSITIVE_DATA:
        m += 0.5
    if control.id == "network_segmentation" and ({"Payment cards"} & data or "OT / ICS" in infra):
        m += 0.8
    if control.id == "vendor_risk" and "SaaS-heavy" in infra:
        m += 0.5
    if control.id == "secure_sdlc" and "In-house software" in infra:
        m += 1.0
    if control.id in {"mfa", "least_privilege"} and infra & {"AWS", "Azure", "GCP", "SaaS-heavy", "Remote workforce"}:
        m += 0.3
    if control.id == "offline_backups" and p.industry.lower() in {"healthcare", "manufacturing", "education", "government"}:
        m += 0.3
    if control.id in {"incident_response_plan", "central_logging"} and p.recent_incidents.strip():
        m += 0.4
    return m


def _risk_drivers(p: OrgProfile) -> list[dict]:
    infra = set(p.infrastructure)
    data = set(p.data_types)
    drivers = []

    def add(name: str, score: int, reason: str) -> None:
        drivers.append({"threat": name, "score": max(1, min(score, 10)), "reason": reason})

    ransomware = 5 + (0 if p.has("offline_backups") else 3) + (0 if p.has("edr") else 1)
    add("Ransomware", ransomware, "Prevalent across all sectors; impact depends on backups and endpoint coverage.")
    bec = 4 + (0 if p.has("mfa") else 3) + (0 if p.has("email_security") else 2)
    add("Phishing & business email compromise", bec, "Credential theft and payment fraud via email.")
    if infra & {"AWS", "Azure", "GCP"}:
        add("Cloud misconfiguration", 6 + (0 if p.has("asset_inventory") else 2),
            "Public storage, over-permissive IAM and exposed services.")
    if "SaaS-heavy" in infra or p.compliance:
        add("Third-party / supply chain compromise", 5 + (0 if p.has("vendor_risk") else 2),
            "Breaches originating at vendors or in software dependencies.")
    if data & SENSITIVE_DATA:
        add("Sensitive data breach", 6 + (0 if p.has("data_encryption") else 2),
            f"Holds {', '.join(sorted(data & SENSITIVE_DATA))}; carries regulatory and reputational cost.")
    if "OT / ICS" in infra:
        add("Operational technology disruption", 7 + (0 if p.has("network_segmentation") else 2),
            "IT-to-OT pivoting can halt physical operations.")
    add("Insider misuse", 3 + (0 if p.has("least_privilege") else 2),
        "Excess access lets mistakes or malicious insiders cause outsized harm.")
    return sorted(drivers, key=lambda d: -d["score"])


def assess(p: OrgProfile) -> dict:
    """Return a maturity score, prioritised gaps and coverage by CSF function."""
    total = sum(c.weight for c in CATALOG)
    achieved = sum(c.weight for c in CATALOG if p.has(c.id))
    score = round(100 * achieved / total)
    tier = 1 if score < 35 else 2 if score < 60 else 3 if score < 85 else 4
    tier_names = {1: "Partial", 2: "Risk-informed", 3: "Repeatable", 4: "Adaptive"}

    coverage = {}
    for fn in CSF_FUNCTIONS:
        controls = [c for c in CATALOG if c.function == fn]
        have = sum(c.weight for c in controls if p.has(c.id))
        coverage[fn] = round(100 * have / sum(c.weight for c in controls))

    gaps = []
    for c in CATALOG:
        if p.has(c.id):
            continue
        priority = round(c.weight * _priority_multiplier(c, p), 1)
        gaps.append({
            "id": c.id, "name": c.name, "function": c.function, "cis": c.cis,
            "priority": priority,
            "severity": "critical" if priority >= 5 else "high" if priority >= 3.5 else "medium",
            "why": c.why,
        })
    gaps.sort(key=lambda g: -g["priority"])

    return {
        "maturity_score": score,
        "tier": tier,
        "tier_name": tier_names[tier],
        "csf_coverage": coverage,
        "gaps": gaps,
        "in_place": [c.name for c in CATALOG if p.has(c.id)],
        "risk_drivers": _risk_drivers(p),
    }


def catalog_public() -> list[dict]:
    return [{"id": c.id, "name": c.name, "function": c.function} for c in CATALOG]
