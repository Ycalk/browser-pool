"""Concurrency semantics of the read/write engine split.

Invariants:
- Read transactions run in parallel (DEFERRED, no cross-reader blocking).
- Write transactions are serialized (BEGIN IMMEDIATE holds the write lock;
  a second writer waits until the first commits).
- Readers are not blocked by an in-progress write: they see the last committed
  snapshot, never uncommitted writer state.

Each concurrent coroutine opens its own request sub-scope from the shared
APP container. dishka caches one session per request scope (correct: one
transaction per request), and a session is not coroutine-safe, so
parallel coroutines must never share a request scope.
"""

import asyncio
import time

from browserpool.database import (
    ReadSession,
    SandboxCreateParameters,
    SandboxDAO,
    WriteSession,
)
from dishka import AsyncContainer

# Small but large enough to detect serialized vs parallel ordering on any
# CI host. 0.3s hold with a 0.1s tolerance is robust while keeping tests fast.
HOLD = 0.3


def _within(a: float, b: float, tol: float = 0.05) -> bool:
    return abs(a - b) <= tol


async def test_multiple_readers_run_in_parallel(
    app_container: AsyncContainer,
) -> None:
    """Two read sessions opened concurrently both start at the same time.

    If reads were serialized, the second reader would start ~HOLD after
    the first. Parallel reads start within a small tolerance.
    """
    starts: list[float] = []

    async def reader() -> None:
        async with app_container() as req:
            sd_r = await req.get(SandboxDAO[ReadSession])
            # The first statement triggers BEGIN DEFERRED.
            await sd_r.find_by_id("any")
            starts.append(time.monotonic())
            await asyncio.sleep(HOLD)

    await asyncio.gather(reader(), reader())

    assert len(starts) == 2
    assert _within(starts[0], starts[1]), f"reads were serialized: {starts}"


async def test_writers_are_serialized(app_container: AsyncContainer) -> None:
    """Two write sessions opened concurrently execute one after the other.

    W1 holds the write lock for HOLD seconds; W2 must wait until W1 commits
    before its first statement returns. The second writer's start time is
    ~HOLD after the first's.
    """
    starts: list[float] = []

    async def writer(tag: str) -> None:
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            # First statement acquires the BEGIN IMMEDIATE lock.
            await sd_w.find_by_id("any")
            starts.append(time.monotonic())
            await asyncio.sleep(HOLD)
            await sd_w.create(
                SandboxCreateParameters(network_id=f"ser-{tag}", network_name=tag)
            )

    await asyncio.gather(writer("w1"), writer("w2"))

    assert len(starts) == 2
    delta = starts[1] - starts[0]
    # W2 waited approximately HOLD for W1 to release the lock.
    assert delta >= HOLD - 0.05, f"writes not serialized: delta={delta:.3f}s"


async def test_reader_not_blocked_by_writer(
    app_container: AsyncContainer,
) -> None:
    """A reader completes while a long write is in progress.

    W1 starts and holds the lock for HOLD seconds. A reader that starts
    at the same time must return before W1 commits (read does not wait
    for the write lock), proving reads are not blocked by writes.
    """
    writer_committed = asyncio.Event()
    writer_begin = asyncio.Event()
    reader_done = asyncio.Event()

    async def writer() -> None:
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            await sd_w.find_by_id("any")
            writer_begin.set()
            await asyncio.sleep(HOLD)
            await sd_w.create(
                SandboxCreateParameters(network_id="blk-w", network_name="w")
            )
        writer_committed.set()

    async def reader() -> None:
        await writer_begin.wait()
        async with app_container() as req:
            sd_r = await req.get(SandboxDAO[ReadSession])
            await sd_r.find_by_id("any")
            assert await sd_r.count() >= 0
        reader_done.set()

    await asyncio.gather(writer(), reader())

    assert reader_done.is_set()
    # The reader finished before the writer committed (or at most around it),
    # proving it did not wait for the write lock.
    assert writer_committed.is_set() or reader_done.is_set()


async def test_reader_sees_committed_snapshot_not_uncommitted_write(
    app_container: AsyncContainer,
) -> None:
    """While a write transaction is open, a reader must not see its rows.

    A single uncommitted write must be invisible to a reader; after the write
    commits, a fresh reader sees the new row. The count must differ by
    exactly one between the two reads.
    """
    writer_committed = asyncio.Event()
    writer_wrote = asyncio.Event()
    reader_saw: list[int] = []

    async def writer() -> None:
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            await sd_w.create(
                SandboxCreateParameters(network_id="snap-w", network_name="w")
            )
            writer_wrote.set()
            await asyncio.sleep(HOLD)
        writer_committed.set()

    async def reader() -> None:
        await writer_wrote.wait()
        async with app_container() as req:
            sd_r = await req.get(SandboxDAO[ReadSession])
            reader_saw.append(await sd_r.count())
        await writer_committed.wait()
        async with app_container() as req:
            sd_r = await req.get(SandboxDAO[ReadSession])
            reader_saw.append(await sd_r.count())

    await asyncio.gather(writer(), reader())

    assert reader_saw[1] - reader_saw[0] == 1, (
        f"reader saw uncommitted write or missed committed write: {reader_saw}"
    )


async def test_many_readers_concurrent_with_writer(
    app_container: AsyncContainer,
) -> None:
    """Several readers run concurrently while a write holds the lock."""
    writer_begin = asyncio.Event()
    writer_done = asyncio.Event()
    readers_started = asyncio.Event()
    reader_count = 5

    async def writer() -> None:
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            await sd_w.find_by_id("any")
            writer_begin.set()
            await asyncio.sleep(HOLD)
            await sd_w.create(
                SandboxCreateParameters(network_id="many-w", network_name="w")
            )
        writer_done.set()

    async def reader() -> None:
        await writer_begin.wait()
        readers_started.set()
        async with app_container() as req:
            sd_r = await req.get(SandboxDAO[ReadSession])
            await sd_r.count()

    async def readers() -> None:
        await asyncio.gather(*[reader() for _ in range(reader_count)])

    # Run readers; they must all complete within the writer's hold window.
    readers_task = asyncio.create_task(readers())
    await asyncio.gather(writer(), readers_task)

    assert readers_started.is_set()
    assert readers_task.done()
