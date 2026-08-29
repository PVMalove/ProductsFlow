from observability.formatters import (
    ColorFormatter,
    JsonFormatter,
    select_formatter,
)


def test_dev_app_env_selects_color_formatter() -> None:
    formatter = select_formatter(app_env="dev", service="identity-service")

    assert isinstance(formatter, ColorFormatter)


def test_any_other_app_env_selects_json_formatter() -> None:
    for app_env in ("prod", "staging", "test", ""):
        formatter = select_formatter(app_env=app_env, service="identity-service")

        assert isinstance(formatter, JsonFormatter)
