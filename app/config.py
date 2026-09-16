from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://osint:osint@postgres:5432/osint"
    redis_url: str = "redis://redis:6379/0"
    github_token: str | None = None
    github_max_candidates: int = 5
    wikidata_max_candidates: int = 5
    http_timeout_seconds: float = 15.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
