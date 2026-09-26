from abc import ABC, abstractmethod
from typing import List

from models.assumption import Assumption


class BaseAnalyzer(ABC):
    """Abstract base class for all assumption analyzers."""

    @abstractmethod
    def analyze(self, file_path: str, source: str) -> List[Assumption]:
        """
        Analyze the given source code and return a list of detected assumptions.

        Args:
            file_path: The path of the file being analyzed (used for reporting).
            source:    The full text content of the file.

        Returns:
            A (possibly empty) list of Assumption instances.
        """
