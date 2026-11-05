"""Реєстр хендлерів: щоб збирати новий aiogram Router на кожен Dispatcher.

aiogram дозволяє приєднати Router лише до одного батька; тести й перезапуски
створюють кілька диспетчерів, тому хендлери реєструються тут, а роутер — у build().
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from aiogram import Router


class HandlerRegistry:
    def __init__(self, name: str) -> None:
        self.name = name
        self._handlers: list[tuple[str, tuple[Any, ...], Callable[..., Any]]] = []
        self._filters: list[tuple[str, tuple[Any, ...]]] = []

    def message(self, *filters: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._deco("message", filters)

    def callback_query(self, *filters: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        return self._deco("callback_query", filters)

    def filter(self, observer: str, *filters: Any) -> None:
        self._filters.append((observer, filters))

    def _deco(self, observer: str, filters: tuple[Any, ...]):  # noqa: ANN202
        def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._handlers.append((observer, filters, fn))
            return fn

        return deco

    def build(self) -> Router:
        router = Router(name=self.name)
        for observer, filters in self._filters:
            getattr(router, observer).filter(*filters)
        for observer, filters, fn in self._handlers:
            getattr(router, observer).register(fn, *filters)
        return router
