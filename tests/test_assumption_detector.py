"""
Tests for analyzers/assumption_detector.py

Covers:
- _parse_response: JSON parsing and field mapping (unchanged logic)
- _deduplicate: duplicate removal and severity preference
- _normalise: whitespace/case normalisation
- detect_assumptions: parallel dispatch and result merging (LLM mocked)
"""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from analyzers.assumption_detector import (
    _deduplicate,
    _normalise,
    _parse_response,
    detect_assumptions,
    _SYSTEM_PROMPTS,
)
from models.assumption import Assumption

# ── Fixtures ──────────────────────────────────────────────────────────────────

INPUT_DATA_ITEMS = [
    {
        "line": 7,
        "assumption": "user_id is assumed to be a non-None integer",
        "evidence": "cursor.execute(query, (user_id,))",
        "risk": "SQL error if user_id is None",
        "severity": "High",
        "suggested_test": "Call with user_id=None and assert ValueError",
    },
]

BOUNDARY_API_ITEMS = [
    {
        "line": 12,
        "assumption": "response JSON always contains the 'data' key",
        "evidence": "results = response.json()['data']",
        "risk": "KeyError crash on error envelope",
        "severity": "Medium",
        "suggested_test": "Mock requests.get to return {'error': 'not found'}",
    },
]

STATE_AUTH_ITEMS = [
    {
        "line": 20,
        "assumption": "current user always has admin permission",
        "evidence": "if user.role == 'admin':",
        "risk": "Unauthorised action if role check is bypassed",
        "severity": "High",
        "suggested_test": "Call endpoint as a non-admin user and assert 403",
    },
]

ALL_ITEMS = INPUT_DATA_ITEMS + BOUNDARY_API_ITEMS + STATE_AUTH_ITEMS


def _make_assumption(**kwargs) -> Assumption:
    defaults = dict(
        file="f.py", line=1,
        assumption="x assumed non-null", evidence="x.attr",
        risk="crash", severity="Medium", suggested_test="pass None",
    )
    return Assumption(**{**defaults, **kwargs})


def _mock_groq_for(category_items: dict):
    """
    Returns a Groq class mock whose instances return per-category JSON.
    category_items: {category_name: list_of_raw_dicts}
    """
    calls_seen = []

    def fake_create(**kwargs):
        system_content = kwargs["messages"][0]["content"]
        # Match by a unique phrase that appears only in that prompt
        chosen = []
        if "input and data integrity" in system_content:
            chosen = category_items.get("input_data", [])
        elif "external boundaries" in system_content:
            chosen = category_items.get("boundary_api", [])
        elif "state, authentication" in system_content:
            chosen = category_items.get("state_auth", [])
        msg = MagicMock()
        msg.content = json.dumps(chosen)
        choice = MagicMock()
        choice.message = msg
        resp = MagicMock()
        resp.choices = [choice]
        calls_seen.append(system_content[:30])
        return resp

    instance = MagicMock()
    instance.chat.completions.create.side_effect = fake_create
    klass = MagicMock(return_value=instance)
    return klass


# ── _normalise ────────────────────────────────────────────────────────────────

class TestNormalise:
    def test_lowercases(self):
        assert _normalise("UserID Is Non-Null") == "userid is non-null"

    def test_collapses_whitespace(self):
        assert _normalise("  foo   bar  ") == "foo bar"

    def test_strips_edges(self):
        assert _normalise("\t leading \n") == "leading"


# ── _parse_response ───────────────────────────────────────────────────────────

class TestParseResponse:
    def test_valid_json_returns_assumptions(self):
        result = _parse_response(json.dumps(ALL_ITEMS), "sample.py")
        assert len(result) == 3
        assert all(isinstance(a, Assumption) for a in result)

    def test_fields_mapped_correctly(self):
        result = _parse_response(json.dumps(INPUT_DATA_ITEMS), "myfile.py")
        a = result[0]
        assert a.file == "myfile.py"
        assert a.line == 7
        assert a.severity == "High"
        assert "user_id" in a.assumption
        assert "cursor.execute" in a.evidence

    def test_strips_markdown_fences(self):
        raw = "```json\n" + json.dumps(INPUT_DATA_ITEMS) + "\n```"
        assert len(_parse_response(raw, "f.py")) == 1

    def test_empty_array(self):
        assert _parse_response("[]", "f.py") == []

    def test_invalid_json(self):
        assert _parse_response("not json", "f.py") == []

    def test_non_list_json(self):
        assert _parse_response('{"key": "val"}', "f.py") == []

    def test_unknown_severity_defaults_to_medium(self):
        item = {**INPUT_DATA_ITEMS[0], "severity": "CRITICAL"}
        assert _parse_response(json.dumps([item]), "f.py")[0].severity == "Medium"

    def test_missing_line_defaults_to_zero(self):
        item = {k: v for k, v in INPUT_DATA_ITEMS[0].items() if k != "line"}
        assert _parse_response(json.dumps([item]), "f.py")[0].line == 0

    def test_entry_without_assumption_skipped(self):
        item = {**INPUT_DATA_ITEMS[0], "assumption": ""}
        assert _parse_response(json.dumps([item]), "f.py") == []

    def test_message_and_snippet_aliases(self):
        a = _parse_response(json.dumps(INPUT_DATA_ITEMS), "f.py")[0]
        assert a.message == a.assumption
        assert a.snippet == a.evidence


# ── _deduplicate ──────────────────────────────────────────────────────────────

class TestDeduplicate:
    def test_no_duplicates_unchanged(self):
        items = [
            _make_assumption(line=1, assumption="a is null", severity="High"),
            _make_assumption(line=2, assumption="b is empty", severity="Low"),
        ]
        result = _deduplicate(items)
        assert len(result) == 2

    def test_exact_duplicate_removed(self):
        a = _make_assumption(line=5, assumption="x assumed non-null", severity="Medium")
        b = _make_assumption(line=5, assumption="x assumed non-null", severity="Medium")
        assert len(_deduplicate([a, b])) == 1

    def test_higher_severity_wins(self):
        low = _make_assumption(line=5, assumption="x assumed non-null", severity="Low")
        high = _make_assumption(line=5, assumption="x assumed non-null", severity="High")
        result = _deduplicate([low, high])
        assert len(result) == 1
        assert result[0].severity == "High"

    def test_case_insensitive_dedup(self):
        a = _make_assumption(line=3, assumption="User is Always Logged In")
        b = _make_assumption(line=3, assumption="user is always logged in")
        assert len(_deduplicate([a, b])) == 1

    def test_sorted_by_line(self):
        items = [
            _make_assumption(line=10, assumption="c"),
            _make_assumption(line=1,  assumption="a"),
            _make_assumption(line=5,  assumption="b"),
        ]
        lines = [a.line for a in _deduplicate(items)]
        assert lines == sorted(lines)

    def test_empty_input(self):
        assert _deduplicate([]) == []


# ── detect_assumptions (mocked) ───────────────────────────────────────────────

class TestDetectAssumptions:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        with pytest.raises(ValueError, match="No Groq API key"):
            detect_assumptions("code = 1", file_name="f.py", api_key=None)

    def test_merges_results_from_all_three_categories(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        mock_klass = _mock_groq_for({
            "input_data":   INPUT_DATA_ITEMS,
            "boundary_api": BOUNDARY_API_ITEMS,
            "state_auth":   STATE_AUTH_ITEMS,
        })
        with patch("analyzers.assumption_detector.Groq", mock_klass):
            result = detect_assumptions("some code", file_name="sample.py")

        assert len(result) == 3
        lines = {a.line for a in result}
        assert lines == {7, 12, 20}

    def test_deduplicates_across_categories(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        duplicate_item = INPUT_DATA_ITEMS[0]
        mock_klass = _mock_groq_for({
            "input_data":   [duplicate_item],
            "boundary_api": [duplicate_item],   # same finding from two analyzers
            "state_auth":   [],
        })
        with patch("analyzers.assumption_detector.Groq", mock_klass):
            result = detect_assumptions("some code", file_name="sample.py")

        assert len(result) == 1

    def test_result_sorted_by_line(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        mock_klass = _mock_groq_for({
            "input_data":   INPUT_DATA_ITEMS,   # line 7
            "boundary_api": BOUNDARY_API_ITEMS, # line 12
            "state_auth":   STATE_AUTH_ITEMS,   # line 20
        })
        with patch("analyzers.assumption_detector.Groq", mock_klass):
            result = detect_assumptions("code", file_name="f.py")

        lines = [a.line for a in result]
        assert lines == sorted(lines)

    def test_uses_provided_api_key(self, monkeypatch):
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        mock_klass = _mock_groq_for({"input_data": [], "boundary_api": [], "state_auth": []})
        with patch("analyzers.assumption_detector.Groq", mock_klass):
            detect_assumptions("x = 1", file_name="f.py", api_key="my-key")

        for c in mock_klass.call_args_list:
            assert c == call(api_key="my-key")

    def test_all_empty_returns_empty_list(self, monkeypatch):
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        mock_klass = _mock_groq_for({"input_data": [], "boundary_api": [], "state_auth": []})
        with patch("analyzers.assumption_detector.Groq", mock_klass):
            result = detect_assumptions("pass", file_name="empty.py")
        assert result == []

    def test_three_separate_groq_clients_created(self, monkeypatch):
        """Each thread should instantiate its own Groq client."""
        monkeypatch.setenv("GROQ_API_KEY", "test-key")
        mock_klass = _mock_groq_for({"input_data": [], "boundary_api": [], "state_auth": []})
        with patch("analyzers.assumption_detector.Groq", mock_klass):
            detect_assumptions("code", file_name="f.py")

        assert mock_klass.call_count == 3

    def test_three_prompts_are_distinct(self):
        """Sanity-check: no two system prompts share the same focus phrase."""
        prompts = list(_SYSTEM_PROMPTS.values())
        assert len(set(prompts)) == 3
