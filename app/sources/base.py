from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain import CanonicalFinding, ExtractedIndicator


@dataclass
class SourceResult:
    """Standard result returned by every person-name OSINT source."""

    findings: list[tuple[CanonicalFinding, list[ExtractedIndicator]]]
    http_status: int
    rate_limit_remaining: int | None = None


class PersonSource(Protocol):
    """Contract implemented by sources that search for a person by name."""

    name: str
    module_name: str

    def search_person_name(self, name: str) -> SourceResult:
        ...
