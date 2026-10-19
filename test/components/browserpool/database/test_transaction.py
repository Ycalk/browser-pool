"""Transaction lifecycle: atomicity within a scope, and lock handoff on exit.

In this design, `session.begin()` is opened by the provider and committed
on scope exit (no manual `commit()` on DAO). Within a single request scope
exactly one write transaction is open; multiple DAO operations are atomic
together. When the scope exits, the transaction commits and the write lock
is released; a waiting writer acquires it immediately.
"""

import asyncio
import time

from browserpool.database import (
    SandboxCreateParameters,
    SandboxDAO,
)
from browserpool.database.models import ReadSession, WriteSession
from dishka import AsyncContainer


async def test_multiple_writes_in_one_scope_are_atomic(
    app_container: AsyncContainer,
) -> None:
    """Several creates in one request scope are committed together at exit.

    Inside the scope the rows are visible (identity map / same transaction).
    After exit, all three rows are visible to a fresh read session.
    """
    created_ids = {"a", "b", "c"}

    async with app_container() as req:
        sd_w = await req.get(SandboxDAO[WriteSession])
        await sd_w.create(
            SandboxCreateParameters(network_id="a", network_name="n", index=0)
        )
        await sd_w.create(
            SandboxCreateParameters(network_id="b", network_name="n", index=0)
        )
        await sd_w.create(
            SandboxCreateParameters(network_id="c", network_name="n", index=0)
        )
        # Visible within the open transaction.
        assert await sd_w.count() == 3

    async with app_container() as req:
        sd_r = await req.get(SandboxDAO[ReadSession])
        count = await sd_r.count()
        assert count == 3
        for nid in created_ids:
            assert await sd_r.find_by_id(nid) is not None


async def test_write_scope_release_allows_next_writer(
    app_container: AsyncContainer,
) -> None:
    """On scope exit, the write lock is released; a waiting writer proceeds.

    W1 holds the lock for HOLD; W2 (started concurrently) must wait. After W1's
    scope exits (transaction commits), W2 acquires the lock and proceeds
    promptly. W2's start time is ~HOLD after W1's start.
    """
    HOLD = 0.3
    w1_started = asyncio.Event()
    w2_started = asyncio.Event()
    events: list[float] = []

    async def w1() -> None:
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            await sd_w.find_by_id("any")
            events.append(time.monotonic())
            w1_started.set()
            await asyncio.sleep(HOLD)
            await sd_w.create(
                SandboxCreateParameters(network_id="w1", network_name="n", index=0)
            )

    async def w2() -> None:
        await w1_started.wait()
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            await sd_w.find_by_id("any")
            events.append(time.monotonic())
            w2_started.set()
            await sd_w.create(
                SandboxCreateParameters(network_id="w2", network_name="n", index=0)
            )

    await asyncio.gather(w1(), w2())

    assert len(events) == 2
    delta = events[1] - events[0]
    # W2 waited ~HOLD for W1 to release the lock.
    assert delta >= HOLD - 0.05, (
        f"writer handoff did not wait for lock release: delta={delta:.3f}s"
    )
    assert w2_started.is_set()


async def test_failed_write_rolls_back_entire_scope(
    app_container: AsyncContainer,
) -> None:
    """An exception in a write scope rolls back all writes in that scope.

    Two rows are inserted, then an exception raises. The transaction rolls
    back (no partial commit), and a fresh read sees none.
    """
    raised = False
    try:
        async with app_container() as req:
            sd_w = await req.get(SandboxDAO[WriteSession])
            await sd_w.create(
                SandboxCreateParameters(network_id="rb-1", network_name="n", index=0)
            )
            await sd_w.create(
                SandboxCreateParameters(network_id="rb-2", network_name="n", index=0)
            )
            raise ValueError("fail mid-transaction")
    except ValueError:
        raised = True

    assert raised, "expected ValueError to propagate out of the scope"

    async with app_container() as req:
        sd_r = await req.get(SandboxDAO[ReadSession])
        assert await sd_r.count() == 0
        assert await sd_r.find_by_id("rb-1") is None
        assert await sd_r.find_by_id("rb-2") is None


async def test_sequential_writes_each_get_fresh_transaction(
    app_container: AsyncContainer,
) -> None:
    """Each new write scope is its own transaction; rows from prior scopes
    are visible to the next scope's read-side checks.
    """
    async with app_container() as req:
        sd_w = await req.get(SandboxDAO[WriteSession])
        await sd_w.create(
            SandboxCreateParameters(network_id="seq-1", network_name="n", index=0)
        )

    async with app_container() as req:
        sd_w = await req.get(SandboxDAO[WriteSession])
        # Prior row visible in the fresh transaction.
        assert await sd_w.find_by_id("seq-1") is not None
        await sd_w.create(
            SandboxCreateParameters(network_id="seq-2", network_name="n", index=0)
        )

    async with app_container() as req:
        sd_r = await req.get(SandboxDAO[ReadSession])
        assert await sd_r.count() == 2
