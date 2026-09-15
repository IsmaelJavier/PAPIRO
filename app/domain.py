import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return value


def normalize_username(value: str) -> str:
    return (value or "").strip().lstrip("@").casefold()


def normalize_url(value: str) -> str:
    return (value or "").strip()


def dedupe_key(*parts: str) -> str:
    payload = "\x1f".join(normalize_text(x) for x in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CanonicalFinding:
    module: str
    source: str
    source_url: str
    input_value: str
    input_type: str
    finding_type: str
    value: str
    confidence: float
    relevance_reason: str
    raw_evidence: dict[str, Any]

    @property
    def dedupe_key(self) -> str:
        return dedupe_key(self.source, self.finding_type, self.value, self.source_url)


@dataclass(frozen=True)
class ExtractedIndicator:
    indicator_type: str
    value: str
    normalized_value: str
    provenance_field: str
