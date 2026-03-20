import asyncio

import pytest

from app.runtime.broadcast import Broadcaster


@pytest.mark.asyncio
async def test_subscribe_returns_async_queue():
    broadcaster = Broadcaster()
    q = await broadcaster.subscribe()
    assert isinstance(q, asyncio.Queue)
    await broadcaster.unsubscribe(q)


@pytest.mark.asyncio
async def test_publish_delivers_item_to_single_subscriber():
    broadcaster = Broadcaster()
    q = await broadcaster.subscribe()
    await broadcaster.publish({"msg": "hello"})
    item = q.get_nowait()
    assert item == {"msg": "hello"}
    await broadcaster.unsubscribe(q)


@pytest.mark.asyncio
async def test_publish_delivers_to_multiple_subscribers():
    broadcaster = Broadcaster()
    q1 = await broadcaster.subscribe()
    q2 = await broadcaster.subscribe()
    await broadcaster.publish("broadcast_item")
    assert q1.get_nowait() == "broadcast_item"
    assert q2.get_nowait() == "broadcast_item"
    await broadcaster.unsubscribe(q1)
    await broadcaster.unsubscribe(q2)


@pytest.mark.asyncio
async def test_unsubscribe_removes_subscriber():
    broadcaster = Broadcaster()
    q = await broadcaster.subscribe()
    await broadcaster.unsubscribe(q)
    await broadcaster.publish("should_not_arrive")
    assert q.empty()


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_does_not_raise():
    broadcaster = Broadcaster()
    # Should complete without error even when there are no subscribers
    await broadcaster.publish({"data": "ignored"})


@pytest.mark.asyncio
async def test_slow_consumer_is_dropped_when_queue_full():
    broadcaster = Broadcaster(max_per_sub=2)
    q = await broadcaster.subscribe()
    # Fill the queue to its capacity
    await broadcaster.publish("item1")
    await broadcaster.publish("item2")
    # This publish exceeds capacity and should drop the slow subscriber
    await broadcaster.publish("item3")
    assert q not in broadcaster._subs


@pytest.mark.asyncio
async def test_fast_consumer_survives_while_slow_is_dropped():
    """Fast subscriber keeps receiving after slow one is evicted."""
    broadcaster = Broadcaster(max_per_sub=2)
    q_fast = await broadcaster.subscribe()
    q_slow = await broadcaster.subscribe()

    # Drain fast queue after each publish to keep it healthy
    await broadcaster.publish("item1")
    q_fast.get_nowait()
    await broadcaster.publish("item2")
    q_fast.get_nowait()
    # slow queue is now full; this publish evicts it
    await broadcaster.publish("item3")

    assert q_slow not in broadcaster._subs
    assert q_fast in broadcaster._subs


@pytest.mark.asyncio
async def test_unsubscribe_is_idempotent():
    broadcaster = Broadcaster()
    q = await broadcaster.subscribe()
    await broadcaster.unsubscribe(q)
    # Second call must not raise
    await broadcaster.unsubscribe(q)


@pytest.mark.asyncio
async def test_publish_multiple_items_in_order():
    broadcaster = Broadcaster()
    q = await broadcaster.subscribe()
    for i in range(5):
        await broadcaster.publish(i)
    received = [q.get_nowait() for _ in range(5)]
    assert received == list(range(5))
    await broadcaster.unsubscribe(q)


@pytest.mark.asyncio
async def test_subscriber_count_tracks_correctly():
    broadcaster = Broadcaster()
    assert len(broadcaster._subs) == 0
    q1 = await broadcaster.subscribe()
    q2 = await broadcaster.subscribe()
    assert len(broadcaster._subs) == 2
    await broadcaster.unsubscribe(q1)
    assert len(broadcaster._subs) == 1
    await broadcaster.unsubscribe(q2)
    assert len(broadcaster._subs) == 0
