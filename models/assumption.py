from dataclasses import dataclass, field


@dataclass
class Assumption:
    """Represents a single potential silent assumption detected in source code.

    These are labelled *potential silent assumptions* — not confirmed bugs.
    They reflect things the code takes for granted without validating.
    """

    # ── Location ──────────────────────────────────────────────────────────────
    file: str        # Path to the file where the assumption was found
    line: int        # 1-based line number (best estimate from LLM; 0 if unknown)

    # ── What was assumed ──────────────────────────────────────────────────────
    assumption: str  # The implicit assumption being made, in plain English
    evidence: str    # Verbatim code snippet or pattern that reveals the assumption

    # ── Impact ────────────────────────────────────────────────────────────────
    risk: str        # What could go wrong if the assumption is violated
    severity: str    # "High", "Medium", or "Low"

    # ── Actionability ─────────────────────────────────────────────────────────
    suggested_test: str  # A concrete test case that would expose the assumption

    # ── Legacy / optional fields kept for compatibility ───────────────────────
    column: int = 0
    kind: str = "potential_silent_assumption"
    message: str = field(default="", repr=False)
    snippet: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        # Keep `message` and `snippet` in sync with the richer fields so that
        # any code still using the old interface keeps working.
        if not self.message:
            self.message = self.assumption
        if not self.snippet:
            self.snippet = self.evidence

    def __str__(self) -> str:
        return (
            f"{self.file}:{self.line} [{self.severity.upper()}] "
            f"{self.assumption}"
        )
