import json
from dataclasses import asdict
from typing import List

from models.assumption import Assumption


class JsonReporter:
    """Serialises detected assumptions to JSON."""

    def report(self, assumptions: List[Assumption]) -> str:
        return json.dumps([asdict(a) for a in assumptions], indent=2)
