from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.sources.base import SourceResult
from app.domain import (
    CanonicalFinding,
    ExtractedIndicator,
    normalize_text,
    normalize_username,
    normalize_url,
)


class GitHubSourceError(Exception):
    pass


class GitHubRateLimitError(GitHubSourceError):
    pass



class GitHubSource:
    name = "github"
    module_name = "github_person_search"

    def __init__(
        self,
        client: httpx.Client | None = None,
    ):
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "PAPIRO/0.1 (OSINT research platform)",
        }

        if settings.github_token:
            headers["Authorization"] = (
                f"Bearer {settings.github_token}"
            )

        self.client = (
            client
            or httpx.Client(
                base_url="https://api.github.com",
                headers=headers,
                timeout=settings.http_timeout_seconds,
                follow_redirects=True,
            )
        )

    @staticmethod
    def _remaining(
        response: httpx.Response,
    ) -> int | None:
        raw = response.headers.get(
            "x-ratelimit-remaining"
        )

        try:
            return (
                int(raw)
                if raw is not None
                else None
            )
        except ValueError:
            return None

    def _check_response(
        self,
        response: httpx.Response,
    ) -> None:
        if response.status_code in (
            403,
            429,
        ):
            remaining = self._remaining(
                response
            )

            if (
                remaining == 0
                or response.status_code == 429
            ):
                raise GitHubRateLimitError(
                    "GitHub rate limit reached "
                    f"(HTTP {response.status_code})"
                )

        response.raise_for_status()

    @staticmethod
    def _assess_name_evidence(
        input_name: str,
        profile_name: str | None,
        login: str,
    ) -> tuple[float, str]:
        """
        Assess the strength of observable name-based evidence.

        The returned value is NOT an identity probability and MUST NOT
        be interpreted as the probability that the GitHub account belongs
        to the searched person.

        Identity is assessed separately by the investigator.
        """

        target = normalize_text(
            input_name
        )
        actual = normalize_text(
            profile_name or ""
        )
        login_norm = normalize_text(
            login
        )

        if actual and actual == target:
            return (
                0.95,
                "exact_public_profile_name_match",
            )

        target_tokens = set(
            target.split()
        )
        actual_tokens = set(
            actual.split()
        )

        if (
            target_tokens
            and actual_tokens
        ):
            intersection = len(
                target_tokens
                & actual_tokens
            )
            union = len(
                target_tokens
                | actual_tokens
            )

            similarity = (
                intersection / union
                if union
                else 0.0
            )

            if similarity >= 0.75:
                return (
                    0.80,
                    "strong_public_profile_name_token_match",
                )

            if similarity >= 0.50:
                return (
                    0.60,
                    "partial_public_profile_name_token_match",
                )

        if (
            target
            and target in login_norm
        ):
            return (
                0.50,
                "input_name_present_in_login",
            )

        return (
            0.30,
            "github_search_candidate_without_strong_name_match",
        )

    @staticmethod
    def _indicators(
        profile: dict[str, Any],
    ) -> list[ExtractedIndicator]:
        indicators: list[
            ExtractedIndicator
        ] = []

        login = profile.get("login")

        if login:
            indicators.append(
                ExtractedIndicator(
                    indicator_type="username",
                    value=login,
                    normalized_value=normalize_username(
                        login
                    ),
                    provenance_field="login",
                )
            )

        email = profile.get("email")

        if email:
            indicators.append(
                ExtractedIndicator(
                    indicator_type="email",
                    value=email,
                    normalized_value=normalize_text(
                        email
                    ),
                    provenance_field="email",
                )
            )

        twitter = profile.get(
            "twitter_username"
        )

        if twitter:
            indicators.append(
                ExtractedIndicator(
                    indicator_type="username",
                    value=twitter,
                    normalized_value=normalize_username(
                        twitter
                    ),
                    provenance_field="twitter_username",
                )
            )

        blog = profile.get("blog")

        if blog:
            indicators.append(
                ExtractedIndicator(
                    indicator_type="url",
                    value=blog,
                    normalized_value=normalize_url(
                        blog
                    ),
                    provenance_field="blog",
                )
            )

        html_url = profile.get(
            "html_url"
        )

        if html_url:
            indicators.append(
                ExtractedIndicator(
                    indicator_type="url",
                    value=html_url,
                    normalized_value=normalize_url(
                        html_url
                    ),
                    provenance_field="html_url",
                )
            )

        return indicators

    def search_person_name(
        self,
        name: str,
    ) -> SourceResult:
        """
        Discover GitHub user profiles whose public name field is related
        to the supplied person name.

        The module discovers candidates and preserves evidence. It does
        not determine whether a discovered account belongs to the target.
        """

        search_response = self.client.get(
            "/search/users",
            params={
                "q": (
                    f"{name} "
                    "in:name "
                    "type:user"
                ),
                "per_page": settings.github_max_candidates,
            },
        )

        self._check_response(
            search_response
        )

        search_data = (
            search_response.json()
        )

        items = search_data.get(
            "items",
            [],
        )[
            : settings.github_max_candidates
        ]

        remaining = self._remaining(
            search_response
        )

        findings: list[
            tuple[
                CanonicalFinding,
                list[ExtractedIndicator],
            ]
        ] = []

        for item in items:
            login = item.get("login")

            if not login:
                continue

            profile_response = (
                self.client.get(
                    f"/users/{login}"
                )
            )

            self._check_response(
                profile_response
            )

            remaining = self._remaining(
                profile_response
            )

            profile = (
                profile_response.json()
            )

            evidence_strength, reason = (
                self._assess_name_evidence(
                    name,
                    profile.get("name"),
                    login,
                )
            )

            source_url = (
                profile.get("html_url")
                or item.get("html_url")
            )

            if not source_url:
                continue

            finding = CanonicalFinding(
                module=self.module_name,
                source=self.name,
                source_url=source_url,

                input_value=name,
                input_type="person_name",

                finding_type="social_profile",
                value=source_url,

                evidence_strength=evidence_strength,
                match_reason=reason,

                raw_evidence={
                    "search_candidate": item,
                    "public_profile": profile,
                },
            )

            findings.append(
                (
                    finding,
                    self._indicators(
                        profile
                    ),
                )
            )

        return SourceResult(
            findings=findings,
            http_status=search_response.status_code,
            rate_limit_remaining=remaining,
        )