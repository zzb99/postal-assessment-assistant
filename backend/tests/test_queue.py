import threading
from concurrent.futures import ThreadPoolExecutor
from backend.app.work_queue import BoundedSlot


def test_finite_queue_serializes_and_times_out_without_slot_leak():
    slot = BoundedSlot(waiting=1)
    assert slot.acquire(timeout=0)
    entered = threading.Event()
    def waiting():
        entered.set()
        return slot.acquire(timeout=.05)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(waiting)
        entered.wait(1)
        assert not slot.acquire(timeout=0)
        assert future.result() is False
    slot.release()
    assert slot.acquire(timeout=0)
    slot.release()


def test_multiple_waiters_complete_one_at_a_time():
    slot = BoundedSlot(waiting=3); lock = threading.Lock(); running = 0; maximum = 0
    def work():
        nonlocal running, maximum
        assert slot.acquire(timeout=1)
        try:
            with lock: running += 1; maximum = max(maximum, running)
            threading.Event().wait(.01)
            with lock: running -= 1
        finally: slot.release()
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(lambda _: work(), range(4)))
    assert maximum == 1
