from contextlib import contextmanager
from typing import Iterator

from app.settings import get_settings


class NoopSpan:
    def __enter__(self) -> "NoopSpan":
        return self

    def __exit__(self, *args) -> None:
        return None

    def update(self, **kwargs) -> None:
        return None


class Observability:
    def __init__(self) -> None:
        settings = get_settings()
        self.enabled = bool(settings.langfuse_public_key and settings.langfuse_secret_key)
        self.langfuse = None
        if self.enabled:
            from langfuse import Langfuse

            self.langfuse = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )

    @contextmanager
    def trace(self, name: str, **metadata) -> Iterator:
        if not self.langfuse:
            yield NoopSpan()
            return
        trace = self.langfuse.trace(name=name, metadata=metadata)
        try:
            yield trace
        finally:
            self.langfuse.flush()

    @contextmanager
    def span(self, trace, name: str, **metadata) -> Iterator:
        if not self.langfuse:
            yield NoopSpan()
            return
        span = trace.span(name=name, metadata=metadata)
        try:
            yield span
        finally:
            span.end()
