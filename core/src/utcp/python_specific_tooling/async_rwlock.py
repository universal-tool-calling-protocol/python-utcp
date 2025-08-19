from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager


class AsyncRWLock:
    """An asyncio-compatible reader-writer lock with writer preference.

    - Multiple readers can hold the lock concurrently.
    - Writers acquire exclusive access.
    - Writer preference via a turnstile prevents writer starvation.
    """

    def __init__(self) -> None:
        self._readers = 0
        self._readers_lock = asyncio.Lock()        # protects _readers counter
        self._resource_lock = asyncio.Lock()       # exclusive resource access
        self._turnstile = asyncio.Lock()           # blocks readers when a writer is waiting/active
        self._writers_lock = asyncio.Lock()        # serialize writers acquiring the turnstile

    async def acquire_read(self) -> None:
        # Readers pass through the turnstile so queued writers can block new readers
        await self._turnstile.acquire()
        self._turnstile.release()

        await self._readers_lock.acquire()
        try:
            self._readers += 1
            if self._readers == 1:
                # First reader locks the resource
                await self._resource_lock.acquire()
        finally:
            self._readers_lock.release()

    async def release_read(self) -> None:
        await self._readers_lock.acquire()
        try:
            self._readers -= 1
            if self._readers == 0:
                # Last reader releases the resource
                self._resource_lock.release()
        finally:
            self._readers_lock.release()

    async def acquire_write(self) -> None:
        # Ensure only one writer at a time attempts to block readers
        await self._writers_lock.acquire()
        try:
            await self._turnstile.acquire()
            # Now block new readers and take the resource
            await self._resource_lock.acquire()
        finally:
            self._writers_lock.release()

    async def release_write(self) -> None:
        self._resource_lock.release()
        self._turnstile.release()

    @asynccontextmanager
    async def read(self):
        await self.acquire_read()
        try:
            yield
        finally:
            await self.release_read()

    @asynccontextmanager
    async def write(self):
        await self.acquire_write()
        try:
            yield
        finally:
            await self.release_write()
