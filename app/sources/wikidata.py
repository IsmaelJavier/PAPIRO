from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings
from app.domain import (
    CanonicalFinding,
    ExtractedIndicator,
    normalize_text,
    normalize_url,
)


class WikidataSourceError(Exception):
    pass


class WikidataRateLimitError(WikidataSourceError):
    pass


@dataclass
class WikidataSearchResult:
    findings: list[
        tuple[
            CanonicalFinding,
            list[ExtractedIndicator],
        ]
    ]
    http_status: int
    rate_limit_remaining: int | None


class WikidataSource:
    """Collect public Wikidata entities matching a person name.

    The module discovers knowledge-graph candidates and preserves the
    returned evidence. It does not decide whether an entity represents
    the target person.
    """

    name = "wikidata"
    module_name = "wikidata_person_search"

    def __init__(self, client: httpx.Client | None = None):
        headers = {
            "Accept": "application/json",
            "User-Agent": "Kami-no-Eye/0.1 (OSINT research prototype)",
        }
        self.client = client or httpx.Client(
            base_url="https://www.wikidata.org",
            headers=headers,
            timeout=settings.http_timeout_seconds,
            follow_redirects=True,
        )

    @staticmethod
    def _remaining(response: httpx.Response) -> int | None:
        raw = response.headers.get("x-ratelimit-remaining")
        try:
            return int(raw) if raw is not None else None
        except ValueError:
            return None

    @staticmethod
    def _check_response(response: httpx.Response) -> None:
        if response.status_code == 429:
            raise WikidataRateLimitError(
                "Wikidata rate limit reached (HTTP 429)"
            )
        response.raise_for_status()

    @staticmethod
    def _language_value(mapping: dict[str, Any], language: str = "en") -> str | None:
        value = mapping.get(language)
        if isinstance(value, dict):
            return value.get("value")
        return None

    @staticmethod
    def _aliases(entity: dict[str, Any], language: str = "en") -> list[str]:
        aliases = entity.get("aliases", {}).get(language, [])
        return [item.get("value") for item in aliases if item.get("value")]

    @staticmethod
    def _assess_name_evidence(
        input_name: str,
        label: str | None,
        aliases: list[str],
        description: str | None,
        search_label: str | None,
    ) -> tuple[float, str]:
        target = normalize_text(input_name)
        label_norm = normalize_text(label or "")
        search_norm = normalize_text(search_label or "")
        alias_norm = {normalize_text(alias) for alias in aliases}

        if label_norm == target and target:
            return 0.95, "exact_wikidata_label_match"

        if target in alias_norm:
            return 0.85, "exact_wikidata_alias_match"

        if search_norm == target and target:
            return 0.80, "exact_wikidata_search_label_match"

        target_tokens = set(target.split())
        actual_tokens = set(label_norm.split())
        if target_tokens and actual_tokens:
            union = len(target_tokens | actual_tokens)
            similarity = (
                len(target_tokens & actual_tokens) / union
                if union
                else 0.0
            )
            if similarity >= 0.75:
                return 0.70, "strong_wikidata_label_token_match"
            if similarity >= 0.50:
                return 0.55, "partial_wikidata_label_token_match"

        if description and target and target in normalize_text(description):
            return 0.45, "input_name_present_in_wikidata_description"

        return 0.30, "wikidata_search_candidate_without_strong_name_match"

    @staticmethod
    def _indicators(
        entity_id: str,
        entity: dict[str, Any],
    ) -> list[ExtractedIndicator]:
        indicators: list[ExtractedIndicator] = []
        entity_url = f"https://www.wikidata.org/wiki/{entity_id}"

        indicators.append(
            ExtractedIndicator(
                indicator_type="wikidata_id",
                value=entity_id,
                normalized_value=normalize_text(entity_id),
                provenance_field="id",
            )
        )
        indicators.append(
            ExtractedIndicator(
                indicator_type="url",
                value=entity_url,
                normalized_value=normalize_url(entity_url),
                provenance_field="entity_url",
            )
        )

        sitelinks = entity.get("sitelinks", {})
        for site in ("enwiki", "eswiki"):
            title = sitelinks.get(site, {}).get("title")
            if not title:
                continue
            language = site.removesuffix("wiki")
            wikipedia_url = (
                f"https://{language}.wikipedia.org/wiki/"
                f"{title.replace(' ', '_')}"
            )
            indicators.append(
                ExtractedIndicator(
                    indicator_type="url",
                    value=wikipedia_url,
                    normalized_value=normalize_url(wikipedia_url),
                    provenance_field=f"sitelinks.{site}",
                )
            )

        return indicators

    def search_person_name(self, name: str) -> WikidataSearchResult:
        search_response = self.client.get(
            "/w/api.php",
            params={
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "uselang": "en",
                "type": "item",
                "limit": settings.wikidata_max_candidates,
                "format": "json",
                "formatversion": "2",
            },
        )
        self._check_response(search_response)
        search_data = search_response.json()
        search_items = search_data.get("search", [])[
            : settings.wikidata_max_candidates
        ]
        remaining = self._remaining(search_response)

        ids = [item.get("id") for item in search_items if item.get("id")]
        if not ids:
            return WikidataSearchResult(
                findings=[],
                http_status=search_response.status_code,
                rate_limit_remaining=remaining,
            )

        entity_response = self.client.get(
            "/w/api.php",
            params={
                "action": "wbgetentities",
                "ids": "|".join(ids),
                "props": "labels|descriptions|aliases|sitelinks",
                "languages": "en",
                "languagefallback": "1",
                "sitefilter": "enwiki|eswiki",
                "format": "json",
                "formatversion": "2",
            },
        )
        self._check_response(entity_response)
        remaining = self._remaining(entity_response)
        entities = entity_response.json().get("entities", {})

        findings: list[
            tuple[CanonicalFinding, list[ExtractedIndicator]]
        ] = []

        for item in search_items:
            entity_id = item.get("id")
            if not entity_id:
                continue
            entity = entities.get(entity_id)
            if not entity or entity.get("missing"):
                continue

            label = self._language_value(entity.get("labels", {}))
            description = self._language_value(entity.get("descriptions", {}))
            aliases = self._aliases(entity)
            search_label = item.get("label")
            evidence_strength, reason = self._assess_name_evidence(
                name,
                label,
                aliases,
                description,
                search_label,
            )

            source_url = f"https://www.wikidata.org/wiki/{entity_id}"
            finding = CanonicalFinding(
                module=self.module_name,
                source=self.name,
                source_url=source_url,
                input_value=name,
                input_type="person_name",
                finding_type="knowledge_entity",
                value=entity_id,
                confidence=evidence_strength,
                relevance_reason=reason,
                raw_evidence={
                    "search_entity": item,
                    "entity": entity,
                },
            )
            findings.append((finding, self._indicators(entity_id, entity)))

        return WikidataSearchResult(
            findings=findings,
            http_status=search_response.status_code,
            rate_limit_remaining=remaining,
        )
