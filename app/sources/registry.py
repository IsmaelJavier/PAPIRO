from app.sources.base import PersonSource
from app.sources.github import GitHubSource
from app.sources.wikidata import WikidataSource


def get_person_name_sources() -> list[PersonSource]:
    """Return the configured person-name source implementations."""
    return [
        GitHubSource(),
        WikidataSource(),
    ]
