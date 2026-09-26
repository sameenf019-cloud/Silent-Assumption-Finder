"""
app.py – Streamlit UI for the Silent Assumption Finder
"""

import os
from typing import List

import pandas as pd
import streamlit as st

from analyzers.assumption_detector import detect_assumptions
from file_reader import read_source_files
from models.assumption import Assumption

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Silent Assumption Finder",
    page_icon="🔍",
    layout="wide",
)

# ── Minimal global style ──────────────────────────────────────────────────────
# Only overrides that Streamlit's theme can't handle: metric card borders and
# footer text.  No color/contrast overrides — those are left to Streamlit.

st.markdown(
    """
    <style>
    /* Subtle border around each metric card */
    [data-testid="stMetric"] {
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 8px;
        padding: 14px 18px;
    }
    /* Footer */
    .saf-footer {
        margin-top: 2.5rem;
        padding-top: 1rem;
        border-top: 1px solid rgba(128,128,128,0.2);
        font-size: 0.82rem;
        color: rgba(128,128,128,0.85);
        text-align: center;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
_SEVERITY_EMOJI = {"high": "🔴", "medium": "🟡", "low": "🟢"}


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline(folder: str) -> tuple[List[Assumption], List[str], int]:
    """Read files, run detection on each, return (findings, errors, file_count)."""
    sources = read_source_files(folder)
    if not sources:
        return [], [], 0

    all_assumptions: List[Assumption] = []
    errors: List[str] = []

    for file_path, content in sorted(sources.items()):
        try:
            found = detect_assumptions(content, file_name=file_path)
            all_assumptions.extend(found)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{file_path}: {exc}")

    sorted_findings = sorted(
        all_assumptions,
        key=lambda a: (_SEVERITY_RANK.get(a.severity.lower(), 9), a.file, a.line),
    )
    return sorted_findings, errors, len(sources)


# ── Results table ─────────────────────────────────────────────────────────────

def _severity_style(val: str) -> str:
    """Return a CSS string for a severity cell — background only, no text color
    override so Streamlit's theme controls contrast."""
    colors = {"high": "#fecaca", "medium": "#fde68a", "low": "#bbf7d0"}
    bg = colors.get(val.lower(), "transparent")
    return f"background-color: {bg};"


def _render_table(assumptions: List[Assumption]) -> None:
    rows = [
        {
            "Severity": f"{_SEVERITY_EMOJI.get(a.severity.lower(), '')} {a.severity.capitalize()}",
            "File": os.path.basename(a.file),
            "Line": a.line if a.line else None,
            "Assumption": a.assumption,
            "Risk": a.risk,
            "Suggested Test": a.suggested_test,
        }
        for a in assumptions
    ]
    df = pd.DataFrame(rows)

    styled = df.style.apply(
        lambda col: [_severity_style(v.split(" ", 1)[-1]) for v in col],
        subset=["Severity"],
    )

    st.dataframe(
        styled,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Severity": st.column_config.TextColumn("Severity", width="small"),
            "File":     st.column_config.TextColumn("File",     width="small"),
            "Line":     st.column_config.NumberColumn("Line",   width="small", format="%d"),
            "Assumption":    st.column_config.TextColumn("Assumption",    width="large"),
            "Risk":          st.column_config.TextColumn("Risk",          width="medium"),
            "Suggested Test": st.column_config.TextColumn("Suggested Test", width="large"),
        },
    )


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("## 🔍 Silent Assumption Finder")
st.markdown(
    "Analyses Python and PHP source code for implicit assumptions "
    "that are never validated — such as non-null inputs, non-empty collections, "
    "successful API responses, or expected data types."
)

st.divider()

# ── Input row ─────────────────────────────────────────────────────────────────

col_input, col_btn = st.columns([5, 1], vertical_alignment="bottom")
with col_input:
    st.markdown("**Folder path**")
    folder_path = st.text_input(
        "Folder path",
        placeholder="/path/to/your/project",
        label_visibility="collapsed",
    )
with col_btn:
    analyze_clicked = st.button("Analyze", type="primary", use_container_width=True)

# ── Results ───────────────────────────────────────────────────────────────────

if analyze_clicked:
    folder_path = folder_path.strip()

    if not folder_path:
        st.warning("Please enter a folder path.")
    elif not os.path.isdir(folder_path):
        st.error(f"**Not a valid directory:** `{folder_path}`")
    else:
        with st.spinner("Running analysis — sending each file to the LLM in parallel…"):
            findings, errors, file_count = run_pipeline(folder_path)

        st.markdown("")  # breathing room

        # ── Errors ────────────────────────────────────────────────────────────
        if errors:
            with st.expander(f"⚠️ {len(errors)} file(s) failed to analyse", expanded=False):
                for err in errors:
                    st.code(err, language=None)

        # ── No files found ────────────────────────────────────────────────────
        if file_count == 0:
            st.info("No `.py` or `.php` files found in that folder.")

        else:
            # ── Summary metrics ───────────────────────────────────────────────
            high_n = sum(1 for a in findings if a.severity.lower() == "high")
            med_n  = sum(1 for a in findings if a.severity.lower() == "medium")
            low_n  = sum(1 for a in findings if a.severity.lower() == "low")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Files scanned", file_count)
            m2.metric("🔴 High",       high_n)
            m3.metric("🟡 Medium",     med_n)
            m4.metric("🟢 Low",        low_n)

            st.markdown("")  # spacing before table

            # ── Results table ─────────────────────────────────────────────────
            if not findings:
                st.success("✅ No potential silent assumptions detected.")
            else:
                st.markdown(
                    f"**{len(findings)} potential silent assumption(s)** detected "
                    f"across {file_count} file(s) — sorted by severity."
                )
                st.markdown("")
                _render_table(findings)

# ── Footer ────────────────────────────────────────────────────────────────────

st.markdown(
    '<p class="saf-footer">'
    "Detected assumptions are potential risks, not confirmed bugs."
    "</p>",
    unsafe_allow_html=True,
)
