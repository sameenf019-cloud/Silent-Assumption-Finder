from typing import List

from models.assumption import Assumption


class ConsoleReporter:
    """Prints detected assumptions to stdout."""

    def report(self, assumptions: List[Assumption]) -> None:
        if not assumptions:
            print("No assumptions detected.")
            return

        print(f"Found {len(assumptions)} assumption(s):\n")
        for assumption in assumptions:
            print(f"  {assumption}")
            print(f"    {assumption.snippet.strip()}\n")
