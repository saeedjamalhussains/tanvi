"""Prompt construction for the strategy generator."""

from __future__ import annotations

import json

from .models import OrgProfile

SYSTEM_PROMPT = """\
You are a senior security strategist (CISO-level) helping an organisation build a \
practical, defensive cybersecurity strategy. You write for two readers at once: \
executives who need priorities, cost and risk in plain language, and the engineers \
who will carry out the work.

Ground every recommendation in the organisation profile and the baseline assessment \
you are given. Prefer a few high-impact actions over long generic checklists, and \
fit the plan to the stated budget, staffing and timeframe. Reference NIST CSF 2.0 \
functions (Govern, Identify, Protect, Detect, Respond, Recover) and CIS Controls v8 \
where they help, and name compliance obligations only when they actually apply. \
When something is uncertain or depends on facts you were not given, say so in the \
Assumptions section instead of guessing silently. Keep the plan defensive: it is \
about protecting this organisation, not attacking anyone.
"""

PLAN_SECTIONS = """\
Write the strategy in GitHub-flavoured Markdown with exactly these sections:

# Security Strategy: <organisation name or "Your Organisation">
## 1. Executive summary
Three to five sentences: current posture, the biggest risks, and what the plan achieves.
## 2. Top risks
A table: Risk | Likelihood (Low/Med/High) | Impact (Low/Med/High) | Why it matters here.
## 3. Strategic priorities
Three to five priorities, each tied to a NIST CSF 2.0 function.
## 4. Roadmap
Sub-sections "First 30 days (quick wins)", "Days 31-90", and "Months 4-{months}". \
For each item give: the action, owner role, rough effort (S/M/L), and the gap or risk it closes.
## 5. Compliance considerations
Only for the frameworks or data types that apply; otherwise say none were identified.
## 6. Budget and staffing
How to deliver this within the stated budget; what to build, buy or outsource.
## 7. Metrics to track
Five to eight measurable KPIs with target values.
## 8. Assumptions and open questions
"""


def build_plan_prompt(profile: OrgProfile, baseline: dict) -> str:
    profile_json = profile.model_dump_json(indent=2)
    baseline_json = json.dumps(baseline, indent=2)
    return (
        "Create a security strategy for the organisation below.\n\n"
        f"<organisation_profile>\n{profile_json}\n</organisation_profile>\n\n"
        "The baseline below was computed by rules from the profile. Controls marked "
        "true in `controls` are in place; everything in `gaps` is missing.\n\n"
        f"<baseline_assessment>\n{baseline_json}\n</baseline_assessment>\n\n"
        + PLAN_SECTIONS.format(months=profile.timeframe_months)
    )
