import httpx
from app.sources.github import GitHubSource


def make_client(handler):
    return httpx.Client(base_url="https://api.github.com", transport=httpx.MockTransport(handler))


def test_person_name_produces_canonical_finding_and_indicators():
    def handler(request):
        if request.url.path == "/search/users":
            return httpx.Response(200, headers={"x-ratelimit-remaining": "9"}, json={
                "items": [{"login": "monalisa", "html_url": "https://github.com/monalisa"}]
            })
        if request.url.path == "/users/monalisa":
            return httpx.Response(200, headers={"x-ratelimit-remaining": "8"}, json={
                "login": "monalisa",
                "name": "Monalisa Octocat",
                "html_url": "https://github.com/monalisa",
                "email": "public@example.com",
                "twitter_username": "mona_public",
                "blog": "https://example.com",
            })
        return httpx.Response(404)

    result = GitHubSource(client=make_client(handler)).search_person_name("Monalisa Octocat")
    assert len(result.findings) == 1
    finding, indicators = result.findings[0]
    assert finding.finding_type == "social_profile"
    assert finding.value == "https://github.com/monalisa"
    assert finding.evidence_strength == 0.95
    assert finding.match_reason == "exact_public_profile_name_match"
    kinds = {(i.indicator_type, i.provenance_field) for i in indicators}
    assert ("username", "login") in kinds
    assert ("email", "email") in kinds
    assert ("username", "twitter_username") in kinds
    assert ("url", "blog") in kinds
    assert ("url", "html_url") in kinds


def test_weak_name_match_is_not_asserted_as_identity():
    def handler(request):
        if request.url.path == "/search/users":
            return httpx.Response(200, json={
                "items": [{"login": "other", "html_url": "https://github.com/other"}]
            })
        if request.url.path == "/users/other":
            return httpx.Response(200, json={
                "login": "other", "name": "Completely Different",
                "html_url": "https://github.com/other"
            })
        return httpx.Response(404)

    result = GitHubSource(client=make_client(handler)).search_person_name("John Smith")
    finding, _ = result.findings[0]
    assert finding.evidence_strength == 0.30
    assert finding.match_reason == "github_search_candidate_without_strong_name_match"
