from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models.file_record import FileType


@dataclass
class ClassificationResult:
    file_type: FileType
    confidence: float                          # 0.0 – 1.0
    method: Literal["portal", "heuristic", "llm", "none"]
    reasoning: str = ""

    @property
    def is_uncertain(self) -> bool:
        return self.confidence < 0.70


class BaseClassifier(ABC):
    @abstractmethod
    async def classify(
        self,
        file_path: Path,
        filename: str,
        portal_document_type: str | None = None,
    ) -> ClassificationResult:
        """
        Classify a file. Uncertain results (confidence < 0.70) are surfaced
        rather than silently bucketed.
        """
        ...
