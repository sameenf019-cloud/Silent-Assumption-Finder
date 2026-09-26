"""
analyzers/assumption_detector.py
---------------------------------
LLM-powered analyzer that detects potential silent assumptions in source code.

Three focused sub-analyzers run in parallel via threads, each looking at a
distinct category of assumption:

  • input_data   – null/None checks, empty collections, type assumptions
  • boundary_api – external calls, HTTP responses, timeouts, malformed data
  • state_auth   – permissions, session state, concurrency

Results from all three are merged and deduplicated before being returned.
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from groq import Groq

from models.assumption import Assumption

# ── Per-category system prompts ───────────────────────────────────────────────

_SHARED_OUTPUT_RULES = """\
Return your findings as a JSON array. Each item must have exactly these keys:
  "line"           – best-guess 1-based line number (integer); use 0 if unknown
  "assumption"     – one concise sentence describing the implicit assumption
  "evidence"       – the exact code fragment (≤ 120 chars) that reveals it
  "risk"           – what breaks if the assumption is wrong
  "severity"       – one of "High", "Medium", or "Low"
  "suggested_test" – a concrete unit-test scenario that would expose this assumption

Rules:
- Only report genuine silent assumptions within your assigned category.
- Do NOT label findings as bugs or confirmed errors.
- If no assumptions are found, return an empty array [].
- Output raw JSON only — no markdown fences, no commentary.
"""

_SYSTEM_PROMPTS: Dict[str, str] = {
    "input_data": (
        "You are a senior software engineer specialising in defensive programming.\n"
        "Your task is to find *potential silent assumptions* related to "
        "**input and data integrity** only:\n"
        "- Assuming a function argument is never None/null\n"
        "- Assuming a string is non-empty before using it\n"
        "- Assuming a list, dict, or set is non-empty before accessing elements\n"
        "- Assuming a value can be safely cast to a specific type\n"
        "- Assuming a dict key always exists\n"
        "- Assuming numeric values are within an expected range\n"
        "Ignore anything related to external APIs, auth, or concurrency.\n\n"
        + _SHARED_OUTPUT_RULES
    ),
    "boundary_api": (
        "You are a senior software engineer specialising in defensive programming.\n"
        "Your task is to find *potential silent assumptions* related to "
        "**external boundaries and API calls** only:\n"
        "- Assuming an HTTP / RPC call always succeeds (no timeout, no error status)\n"
        "- Assuming an API response always contains expected fields\n"
        "- Assuming a third-party service is always available\n"
        "- Assuming a file or resource always exists before opening it\n"
        "- Assuming environment variables or config keys are always set\n"
        "- Assuming external data is always well-formed / schema-valid\n"
        "Ignore input-validation assumptions and auth/concurrency concerns.\n\n"
        + _SHARED_OUTPUT_RULES
    ),
    "state_auth": (
        "You are a senior software engineer specialising in defensive programming.\n"
        "Your task is to find *potential silent assumptions* related to "
        "**state, authentication, and concurrency** only:\n"
        "- Assuming the current user always has the required permission or role\n"
        "- Assuming a session or token is always valid and not expired\n"
        "- Assuming shared state is not modified concurrently\n"
        "- Assuming a database transaction always commits successfully\n"
        "- Assuming global or module-level state is initialised before use\n"
        "- Assuming operations are idempotent when they may not be\n"
        "Ignore pure input-validation and external-API assumptions.\n\n"
        + _SHARED_OUTPUT_RULES
    ),
}

_USER_PROMPT_TEMPLATE = """\
Analyse the following source file for potential silent assumptions.
File: {file_name}

```
{source}
```
"""

# ── Public API ────────────────────────────────────────────────────────────────


def detect_assumptions(
    source: str,
    file_name: str = "<unknown>",
    *,
    api_key: str | None = None,
    model: str = "openai/gpt-oss-20b",
    temperature: float = 0.2,
) -> List[Assumption]:
    """
    Run three focused sub-analyzers in parallel and return a merged,
    deduplicated list of potential silent assumptions.

    Sub-analyzers:
        - **input_data**   – null/empty/type assumptions
        - **boundary_api** – external calls, responses, config, files
        - **state_auth**   – permissions, session, concurrency

    Args:
        source:      Full text content of the source file to analyse.
        file_name:   Name / path of the file (used in results and the prompt).
        api_key:     Groq API key.  Falls back to the ``GROQ_API_KEY``
                     environment variable when omitted.
        model:       Model identifier to use (default: ``"openai/gpt-oss-20b"``).
        temperature: Sampling temperature — keep low for deterministic output.

    Returns:
        A deduplicated list of :class:`~models.assumption.Assumption` instances
        sorted by line number.  Returns an empty list when nothing is found or
        responses cannot be parsed.

    Raises:
        ValueError:    If no API key is available.
        groq.APIError: On network or API-level failures (propagated from any
                       thread).
    """
    resolved_key = api_key or os.environ.get("GROQ_API_KEY")
    if not resolved_key:
        raise ValueError(
            "No Groq API key provided.  Pass api_key= or set the "
            "GROQ_API_KEY environment variable."
        )

    user_message = _USER_PROMPT_TEMPLATE.format(
        file_name=file_name,
        source=source,
    )

    def _run_category(category: str) -> Tuple[str, List[Assumption]]:
        """Call the LLM for one category and return (category, findings)."""
        client = Groq(api_key=resolved_key)
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPTS[category]},
                {"role": "user", "content": user_message},
            ],
        )
        raw = response.choices[0].message.content or ""
        return category, _parse_response(raw, file_name)

    all_findings: List[Assumption] = []

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_run_category, category): category
            for category in _SYSTEM_PROMPTS
        }
        for future in as_completed(futures):
            _category, findings = future.result()  # re-raises any thread exception
            all_findings.extend(findings)

    return _deduplicate(all_findings)


# ── Internal helpers ──────────────────────────────────────────────────────────

_SEVERITY_VALUES = {"high", "medium", "low"}


def _parse_response(raw: str, file_name: str) -> List[Assumption]:
    """Parse the LLM's JSON output into a list of Assumption objects."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()

    try:
        items = json.loads(cleaned)
    except json.JSONDecodeError:
        return []

    if not isinstance(items, list):
        return []

    assumptions: List[Assumption] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        severity = str(item.get("severity", "Medium")).strip()
        if severity.lower() not in _SEVERITY_VALUES:
            severity = "Medium"

        try:
            line = int(item.get("line", 0))
        except (TypeError, ValueError):
            line = 0

        assumption_text = str(item.get("assumption", "")).strip()
        evidence_text = str(item.get("evidence", "")).strip()

        if not assumption_text:
            continue

        assumptions.append(
            Assumption(
                file=file_name,
                line=line,
                assumption=assumption_text,
                evidence=evidence_text,
                risk=str(item.get("risk", "")).strip(),
                severity=severity.capitalize(),
                suggested_test=str(item.get("suggested_test", "")).strip(),
            )
        )

    return assumptions


def _deduplicate(assumptions: List[Assumption]) -> List[Assumption]:
    """Remove near-duplicate assumptions and sort by line number.

    Two findings are considered duplicates when they share the same
    (file, line, normalised assumption text).  When duplicates exist the one
    with the higher severity is kept.
    """
    _severity_rank = {"high": 3, "medium": 2, "low": 1}

    best: Dict[Tuple[str, int, str], Assumption] = {}
    for a in assumptions:
        key = (a.file, a.line, _normalise(a.assumption))
        existing = best.get(key)
        if existing is None:
            best[key] = a
        else:
            # Keep whichever finding has the higher severity
            if _severity_rank.get(a.severity.lower(), 0) > _severity_rank.get(
                existing.severity.lower(), 0
            ):
                best[key] = a

    return sorted(best.values(), key=lambda a: a.line)


def _normalise(text: str) -> str:
    """Lowercase and collapse whitespace for fuzzy key comparison."""
    return re.sub(r"\s+", " ", text.lower().strip())
