"""Bounded admission plus serial work, for the supported single-worker deployment."""
import threading


class BoundedSlot:
    def __init__(self, waiting=4):
        self._admission = threading.BoundedSemaphore(waiting + 1)
        self._worker = threading.BoundedSemaphore(1)

    def acquire(self, *, timeout=45):
        if not self._admission.acquire(blocking=False): return False
        if self._worker.acquire(timeout=timeout): return True
        self._admission.release()
        return False

    def release(self):
        self._worker.release()
        self._admission.release()
