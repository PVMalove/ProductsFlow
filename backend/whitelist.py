# Сгенерировано `vulture --make-whitelist .` — ложные срабатывания, чтобы
# vulture молчал.
# configured_identity_key (тесты kernel-platform) — параметр pytest-фикстуры,
# запрашиваемый только ради побочного эффекта настройки (генерирует ключ и
# подменяет путь в identity core settings) — тесты никогда не используют
# само значение.
configured_identity_key = None
__all__ = ["configured_identity_key"]
