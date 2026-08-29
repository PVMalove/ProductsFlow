from typing import Protocol, runtime_checkable


@runtime_checkable
class VisibilityPolicy[TViewer, TResource](Protocol):
    """Форма политики видимости (ADR 0013): единый предикат «viewer видит
    resource», общий для read-моделей всех будущих сервисов. Kernel фиксирует
    только контракт — ни одна реализация здесь не живёт, каждый сервис пишет
    свою против собственной read-модели."""

    def is_visible(self, viewer: TViewer, resource: TResource) -> bool: ...
