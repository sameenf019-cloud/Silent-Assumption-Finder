import os
import sys
from typing import List

from analyzers.assumption_detector import detect_assumptions
from file_reader import read_source_files
from models.assumption import Assumption

# ── Severity sort order ───────────────────────────────────────────────────────

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}

# ── Column widths ─────────────────────────────────────────────────────────────

_COL_WIDTHS = {
    "file":           28,
    "line":            4,
    "assumption":     42,
    "risk":           34,
    "severity":        8,
    "suggested_test": 44,
}

_HEADERS = {
    "file":           "File",
    "line":           "Line",
    "assumption":     "Assumption",
    "risk":           "Risk",
    "severity":       "Sev.",
    "suggested_test": "Suggested Test",
}


# ── Formatting helpers ────────────────────────────────────────────────────────

def _trunc(text: str, width: int) -> str:
    """Truncate *text* to *width* chars, appending '…' if cut."""
    if len(text) <= width:
        return text.ljust(width)
    return text[: width - 1] + "…"


def _severity_label(sev: str) -> str:
    labels = {"high": "HIGH", "medium": "MED ", "low": "LOW "}
    return labels.get(sev.lower(), sev[:4].upper().ljust(4))


def _print_row(values: dict) -> None:
    parts = [_trunc(str(values[col]), w) for col, w in _COL_WIDTHS.items()]
    print("  ".join(parts))


def _separator() -> str:
    return "  ".join("─" * w for w in _COL_WIDTHS.values())


def _print_table(assumptions: List[Assumption]) -> None:
    _print_row(_HEADERS)
    print(_separator())
    for a in assumptions:
        _print_row({
            "file":           os.path.basename(a.file),
            "line":           str(a.line) if a.line else "?",
            "assumption":     a.assumption,
            "risk":           a.risk,
            "severity":       _severity_label(a.severity),
            "suggested_test": a.suggested_test,
        })


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python main.py <path-to-source-folder>")
        sys.exit(1)

    folder = sys.argv[1]

    # ── Read files ────────────────────────────────────────────────────────────
    try:
        sources = read_source_files(folder)
    except NotADirectoryError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if not sources:
        print(f"No .py or .php files found in '{folder}'.")
        sys.exit(0)

    print(f"Scanning {len(sources)} file(s) in '{folder}' …\n")

    # ── Analyse each file ─────────────────────────────────────────────────────
    all_assumptions: List[Assumption] = []
    errors: List[str] = []

    for file_path, content in sorted(sources.items()):
        print(f"  • {file_path}", end="", flush=True)
        try:
            found = detect_assumptions(content, file_name=file_path)
            all_assumptions.extend(found)
            print(f"  → {len(found)} finding(s)")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{file_path}: {exc}")
            print(f"  → ERROR: {exc}")

    print()

    # ── Report errors ─────────────────────────────────────────────────────────
    if errors:
        print(f"⚠  {len(errors)} file(s) could not be analysed (see above).\n")

    # ── Sort and print ────────────────────────────────────────────────────────
    if not all_assumptions:
        print("No potential silent assumptions detected.")
        sys.exit(0)

    sorted_assumptions = sorted(
        all_assumptions,
        key=lambda a: (_SEVERITY_RANK.get(a.severity.lower(), 9), a.file, a.line),
    )

    total = len(sorted_assumptions)
    high  = sum(1 for a in sorted_assumptions if a.severity.lower() == "high")
    med   = sum(1 for a in sorted_assumptions if a.severity.lower() == "medium")
    low   = sum(1 for a in sorted_assumptions if a.severity.lower() == "low")

    print(
        f"Found {total} potential silent assumption(s) — "
        f"HIGH: {high}  MED: {med}  LOW: {low}\n"
    )

    _print_table(sorted_assumptions)
    print()


if __name__ == "__main__":
    main()
