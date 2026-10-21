"""Bound request admission, body buffering, and processing per worker."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import logging
from tempfile import SpooledTemporaryFile
from time import monotonic

from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResourceLimits:
    requests_per_minute: int = 600
    auth_per_minute: int = 20
    expensive_per_minute: int = 10
    concurrent_requests: int = 32
    concurrent_expensive: int = 4
    tracked_clients: int = 10000
    json_bytes: int = 2 * 1024 * 1024
    upload_bytes: int = 52 * 1024 * 1024
    read_seconds: float = 60
    processing_seconds: float = 300
    trusted_proxies: tuple[str, ...] = ()

    def __post_init__(self):
        for key, value in vars(self).items():
            if key != "trusted_proxies" and value <= 0:
                raise ValueError(f"{key} must be positive")


class ResourceLimitMiddleware:
    def __init__(self, app, limits: ResourceLimits | None = None):
        self.app = app
        self.limits = limits or ResourceLimits()
        self.clients = OrderedDict()
        self.active = 0
        self.expensive_active = 0
        self.last_warning = {}

    async def reject(self, scope, receive, send, status, detail):
        now = monotonic()
        if now - self.last_warning.get(detail, -60) >= 60:
            logger.warning("Resource protection: status=%s reason=%s", status, detail)
            self.last_warning[detail] = now
        headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                   "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
                   "Content-Security-Policy": "default-src 'none'; script-src 'none'; frame-ancestors 'none'"}
        if status in {429, 503}:
            headers["Retry-After"] = "60" if status == 429 else "5"
        await JSONResponse({"detail": detail}, status_code=status, headers=headers)(scope, receive, send)

    def admit(self, client, category):
        now = monotonic()
        # Entries expire from creation, so expiry remains ordered. Never evict
        # active buckets: rotating client addresses cannot reset existing limits.
        while self.clients and next(iter(self.clients.values()))[0] <= now:
            self.clients.popitem(last=False)
        if client not in self.clients:
            if len(self.clients) >= self.limits.tracked_clients:
                return False
            self.clients[client] = [now + 60, 0, 0, 0]
        bucket = self.clients[client]
        bucket[1] += 1
        index = {"auth": 2, "expensive": 3}.get(category)
        if index:
            bucket[index] += 1
        return bucket[1] <= self.limits.requests_per_minute and (
            not index or bucket[index] <= (self.limits.auth_per_minute if index == 2 else self.limits.expensive_per_minute))

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        peer = (scope.get("client") or ("unknown", 0))[0]
        # Trust a single address only from an explicitly configured proxy that
        # overwrites X-Forwarded-For. Client-supplied cookies never reset IP quotas.
        client = peer
        forwarded = headers.get(b"x-forwarded-for", b"").decode("latin1").strip()
        if peer in self.limits.trusted_proxies and forwarded and "," not in forwarded:
            from ipaddress import ip_address
            try:
                client = str(ip_address(forwarded))
            except ValueError:
                pass
        path = scope.get("path", "")
        write = scope.get("method") not in {"GET", "HEAD", "OPTIONS"}
        expensive = write and any(token in path for token in (
            "/generate", "/draft", "/export", "/report", "/sync", "/documents", "/uploads", "/library", "/template", "/extract-theme", "/theme/extract", "/moderate"))
        category = "auth" if write and path.startswith("/api/auth/") else "expensive" if expensive else "normal"
        if not self.admit(client, category):
            return await self.reject(scope, receive, send, 429, "Too many requests. Try again later.")
        if self.active >= self.limits.concurrent_requests or (expensive and self.expensive_active >= self.limits.concurrent_expensive):
            return await self.reject(scope, receive, send, 503, "Server is busy. Try again later.")
        content_type = headers.get(b"content-type", b"").lower()
        limit = self.limits.upload_bytes if content_type.startswith(b"multipart/form-data") else self.limits.json_bytes
        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError()
        except ValueError:
            return await self.reject(scope, receive, send, 400, "Invalid request length.")
        if length > limit:
            return await self.reject(scope, receive, send, 413, "Request body is too large.")
        self.active += 1
        self.expensive_active += int(expensive)
        started = False
        async def tracked_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)
        try:
            # Spill uploads to disk rather than retaining large bodies in memory.
            # Count actual bytes, including requests without Content-Length.
            with SpooledTemporaryFile(max_size=1024 * 1024) as body:
                total = 0
                try:
                    async with asyncio.timeout(self.limits.read_seconds):
                        while True:
                            message = await receive()
                            if message["type"] == "http.disconnect":
                                return
                            chunk = message.get("body", b"")
                            total += len(chunk)
                            if total > limit:
                                return await self.reject(scope, receive, send, 413, "Request body is too large.")
                            body.write(chunk)
                            if not message.get("more_body", False):
                                break
                except TimeoutError:
                    return await self.reject(scope, receive, send, 408, "Request body timed out.")
                body.seek(0)
                exhausted = False
                async def replay():
                    nonlocal exhausted
                    if exhausted:
                        return await receive()
                    chunk = body.read(64 * 1024)
                    more = body.tell() < total
                    exhausted = not more
                    return {"type": "http.request", "body": chunk, "more_body": more}
                try:
                    async with asyncio.timeout(self.limits.processing_seconds):
                        await self.app(scope, replay, tracked_send)
                except TimeoutError:
                    if started:
                        raise  # Never send a second response after streaming starts.
                    await self.reject(scope, receive, send, 504, "Request processing timed out.")
        finally:
            self.active -= 1
            self.expensive_active -= int(expensive)
