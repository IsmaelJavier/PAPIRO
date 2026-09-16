import httpx

from app.sources.wikidata import WikidataSource


def make_client(handler):
    return httpx.Client(
        base_url="https://www.wikidata.org",
        transport=httpx.MockTransport(handler),
    )


def test_person_name_produces_knowledge_finding_and_indicators():
    def handler(request):
        if request.url.path == "/w/api.php":
            action = request.url.params.get("action")
            if action == "wbsearchentities":
                return httpx.Response(
                    200,
                    headers={"x-ratelimit-remaining": "99"},
                    json={
                        "search": [
                            {
                                "id": "Q34253",
                                "label": "Linus Torvalds",
                                "description": "Finnish-American software engineer",
                            }
                        ]
                    },
                )
            if action == "wbgetentities":
                return httpx.Response(
                    200,
                    headers={"x-ratelimit-remaining": "98"},
                    json={
                        "entities": {
                            "Q34253": {
                                "id": "Q34253",
                                "type": "item",
                                "labels": {"en": {"language": "en", "value": "Linus Torvalds"}},
                                "descriptions": {"en": {"language": "en", "value": "Finnish-American software engineer"}},
                                "aliases": {"en": [{"language": "en", "value": "Linus Benedict Torvalds"}]},
                                "sitelinks": {
                                    "enwiki": {"site": "enwiki", "title": "Linus Torvalds"},
                                    "eswiki": {"site": "eswiki", "title": "Linus Torvalds"},
                                },
                            }
                        }
                    },
                )
        return httpx.Response(404)

    result = WikidataSource(client=make_client(handler)).search_person_name("Linus Torvalds")
    assert len(result.findings) == 1
    finding, indicators = result.findings[0]
    assert finding.finding_type == "knowledge_entity"
    assert finding.value == "Q34253"
    assert finding.evidence_strength == 0.95
    assert finding.match_reason == "exact_wikidata_label_match"
    kinds = {(i.indicator_type, i.provenance_field) for i in indicators}
    assert ("wikidata_id", "id") in kinds
    assert ("url", "entity_url") in kinds
    assert ("url", "sitelinks.enwiki") in kinds
    assert ("url", "sitelinks.eswiki") in kinds


def test_alias_match_has_distinct_evidence_reason():
    def handler(request):
        action = request.url.params.get("action")
        if action == "wbsearchentities":
            return httpx.Response(200, json={
                "search": [{"id": "Q1", "label": "Someone Else"}]
            })
        if action == "wbgetentities":
            return httpx.Response(200, json={
                "entities": {
                    "Q1": {
                        "id": "Q1",
                        "labels": {"en": {"value": "Someone Else"}},
                        "descriptions": {},
                        "aliases": {"en": [{"value": "John Smith"}]},
                        "sitelinks": {},
                    }
                }
            })
        return httpx.Response(404)

    result = WikidataSource(client=make_client(handler)).search_person_name("John Smith")
    finding, _ = result.findings[0]
    assert finding.evidence_strength == 0.85
    assert finding.match_reason == "exact_wikidata_alias_match"
