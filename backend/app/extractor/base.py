from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path


@dataclass
class StatementData:
    fund_name: str
    statement_date: date
    current_value: float | None       # None = found in doc but unparseable
    raw_fields: dict = field(default_factory=dict)   # full LLM output for audit
    confidence: float = 1.0
    extraction_notes: str = ""        # which field label was used, or warnings


class BaseExtractor(ABC):
    @abstractmethod
    async def extract(self, file_path: Path) -> StatementData:
        """
        Extract structured data from a capital account statement PDF.
        Raises ValueError if the document cannot be parsed at all.
        """
        ...
