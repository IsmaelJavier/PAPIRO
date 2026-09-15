from app.domain import dedupe_key, normalize_text, normalize_username


def test_normalization_is_deterministic():
    assert normalize_text("  John   SMITH ") == "john smith"
    assert normalize_username("@Example_User") == "example_user"


def test_dedupe_key_is_stable():
    a = dedupe_key("GitHub", "social_profile", "https://github.com/example")
    b = dedupe_key(" github ", "SOCIAL_PROFILE", "https://github.com/example")
    assert a == b
