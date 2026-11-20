"""Reusable bounded async batching primitives for scraper and assessment tasks."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

T = TypeVar("T")


async def process_chunks(items: Sequence[str], worker: Callable[[int, str], Awaitable[T]],
                         chunk_size: int) -> list[T]:
    """Run one bounded chunk at a time, retain the original URL order.

    The worker supplies its own semaphore(s) to control network/LLM concurrency.
    Creating at most ``chunk_size`` tasks avoids unbounded pending jobs for 10k URLs.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")
    results: list[T] = []
    for begin in range(0, len(items), chunk_size):
        subset = items[begin:begin + chunk_size]
        results.extend(await asyncio.gather(*(worker(begin + offset, url) for offset, url in enumerate(subset))))
    return results
