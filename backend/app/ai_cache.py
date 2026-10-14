"""Bounded private TTL cache with in-flight de-duplication and short error cooldown."""
import copy
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future


class RequestCache:
    def __init__(self, ttl=900, capacity=256, error_ttl=20):
        self.ttl, self.capacity, self.error_ttl = ttl, capacity, error_ttl
        self.entries = OrderedDict()
        self.pending = {}
        self.lock = threading.Lock()

    @property
    def size(self):
        with self.lock:
            return len(self.entries)

    def clear(self):
        with self.lock:
            self.entries.clear()

    def peek(self, key):
        with self.lock:
            entry = self.entries.get(key)
            if entry and entry[0] > time.monotonic() and not entry[2]:
                return copy.deepcopy(entry[1])
            return None

    def get_or_create(self, key, producer):
        now = time.monotonic()
        with self.lock:
            entry = self.entries.get(key)
            if entry and entry[0] > now:
                self.entries.move_to_end(key)
                if entry[2]:
                    raise entry[1]
                return copy.deepcopy(entry[1]), True
            self.entries.pop(key, None)
            future = self.pending.get(key)
            leader = future is None
            if leader:
                if len(self.pending) >= self.capacity:
                    raise RuntimeError("AI请求过多，请稍后重试")
                future = Future()
                self.pending[key] = future
        if not leader:
            return copy.deepcopy(future.result(timeout=55)), True
        try:
            value = producer()
        except Exception as error:
            # Avoid retaining a traceback (which can contain a prompt/key) in the cache.
            cached_error = type(error)(str(error))
            with self.lock:
                self.entries[key] = (time.monotonic() + self.error_ttl, cached_error, True)
                self.pending.pop(key, None)
                while len(self.entries) > self.capacity:
                    self.entries.popitem(last=False)
            future.set_exception(cached_error)
            raise
        with self.lock:
            self.entries[key] = (time.monotonic() + self.ttl, copy.deepcopy(value), False)
            self.pending.pop(key, None)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
        future.set_result(copy.deepcopy(value))
        return copy.deepcopy(value), False
