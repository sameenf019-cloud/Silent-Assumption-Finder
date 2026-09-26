# 🔍 Silent Assumption Finder

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://silent-assumption-finder-k4bzuvvtnhlyphbmwqhmxy.streamlit.app/)

🚀 **Live Demo:** [Launch Silent Assumption Finder App](https://silent-assumption-finder-k4bzuvvtnhlyphbmwqhmxy.streamlit.app/)

A static analysis tool that reads Python and PHP source code and surfaces
**implicit assumptions developers make without validating them** — powered by
an LLM running on Groq.

---

## The Problem

Every codebase is full of silent assumptions: beliefs the code relies on that
are never actually checked. Some common examples:

- A function argument is assumed to never be `None`
- A list is assumed to always have at least one element
- An API call is assumed to always succeed
- A config key or environment variable is assumed to always exist
- A user is assumed to always have the required permission

These assumptions don't cause immediate errors — they hide quietly until
production throws an unexpected `NullPointerException`, `KeyError`, or `403`.
The Silent Assumption Finder makes them visible before that happens.

> **Note:** Detected assumptions are potential risks, not confirmed bugs.
> They represent blind spots worth reviewing, not definitive defects.

---

## How It Works

The tool runs **three specialised LLM analyzers in parallel**, each focused on
a distinct category of assumption:

| Analyzer | Detects |
|---|---|
| **Input / Data** | `None`/null checks, empty collections, type assumptions, missing dict keys |
| **Boundary / API** | External calls, HTTP responses, timeouts, env vars, malformed data |
| **State / Auth** | Permissions, session validity, concurrency, transaction safety |

Results from all three are merged and deduplicated, then sorted by severity
(High → Medium → Low).

---

## Project Structure

```
silent-assumption-finder/
├── app.py                     # Streamlit web UI
├── main.py                    # CLI entry point
├── file_reader.py             # Recursively reads .py and .php files
├── requirements.txt
├── analyzers/
│   ├── __init__.py
│   ├── assumption_detector.py # LLM-based detection (3 parallel sub-analyzers)
│   └── base_analyzer.py       # Abstract base class for analyzers
├── models/
│   ├── __init__.py
│   └── assumption.py          # Assumption data model
├── reporters/
│   ├── __init__.py
│   ├── console_reporter.py    # Prints findings to stdout
│   └── json_reporter.py       # Outputs findings as JSON
└── tests/
    ├── __init__.py
    ├── test_file_reader.py
    ├── test_assumption_detector.py
    └── fixtures/
        ├── sample.py
        └── sample.php
```

---

## Getting Started

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set your Groq API key

```bash
# macOS / Linux
export GROQ_API_KEY=your_key_here

# Windows (PowerShell)
$env:GROQ_API_KEY = "your_key_here"
```

Get a free API key at [console.groq.com](https://console.groq.com).

### 3. Run the Streamlit app

```bash
streamlit run app.py
```

Enter a folder path in the UI and click **Analyze**. Results appear in a
color-coded table — 🔴 High, 🟡 Medium, 🟢 Low.

### Run via CLI instead

```bash
python main.py /path/to/your/project
```

### Run tests

```bash
python -m pytest tests/
```

---

## Built with IBM Bob

This project was built iteratively using **IBM Bob** in Agent mode. Key Bob
features used during development:

| Feature | How it was used |
|---|---|
| **Agent mode** | Iterative, step-by-step implementation — file reader, data model, analyzer, CLI, and UI all built and refined in a single continuous session |
| **Parallel subagents** | The three-category detection strategy (input/data, boundary/API, state/auth) was designed around Bob's ability to reason about parallel execution — each category runs as an independent thread against the Groq API |
| **Code understanding** | Bob read and reasoned across all project files at each step to ensure consistency — imports, data models, and function signatures stayed aligned as the codebase grew |
| **Iterative refinement** | The UI went through multiple passes (custom HTML → native `st.dataframe` with pandas Styler) guided by feedback, with Bob making precise surgical edits rather than full rewrites |
