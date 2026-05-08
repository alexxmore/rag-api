import math
import time

import redis.asyncio as redis
from fastapi import HTTPException, status

from app.schemas import ApiKeyConfig
from app.settings import get_settings

_memory_buckets: dict[str, tuple[float, float]] = {}


class TokenRateLimiter:
    def __init__(self) -> None:
        settings = get_settings()
        self.client = redis.from_url(settings.redis_url, decode_responses=True)

    async def _redis_available(self) -> bool:
        try:
            await self.client.ping()
            return True
        except Exception:
            return False

    async def preflight(self, api_key: str, config: ApiKeyConfig) -> None:
        allowed, retry_after = await self._consume(api_key, config, estimated_tokens=500)
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Token rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )

    async def refund_preflight(self, api_key: str, config: ApiKeyConfig) -> None:
        await self.add_tokens(api_key, config, 500)

    async def charge_actual(self, api_key: str, config: ApiKeyConfig, actual_tokens: int) -> None:
        extra = max(0, actual_tokens - 500)
        if extra:
            await self._consume(api_key, config, estimated_tokens=extra)

    async def add_tokens(self, api_key: str, config: ApiKeyConfig, tokens: int) -> None:
        if await self._redis_available():
            key = f"rl:{api_key}"
            raw_tokens = await self.client.get(f"{key}:tokens")
            current = float(raw_tokens or config.tokens_per_minute)
            await self.client.set(f"{key}:tokens", min(config.tokens_per_minute, current + tokens), ex=120)
        else:
            tokens_now, updated = _memory_buckets.get(api_key, (config.tokens_per_minute, time.time()))
            _memory_buckets[api_key] = (min(config.tokens_per_minute, tokens_now + tokens), updated)

    async def _consume(self, api_key: str, config: ApiKeyConfig, estimated_tokens: int) -> tuple[bool, int]:
        if await self._redis_available():
            return await self._consume_redis(api_key, config, estimated_tokens)
        return self._consume_memory(api_key, config, estimated_tokens)

    async def _consume_redis(self, api_key: str, config: ApiKeyConfig, estimated_tokens: int) -> tuple[bool, int]:
        key = f"rl:{api_key}"
        now = time.time()
        refill_per_second = config.tokens_per_minute / 60

        raw_tokens = await self.client.get(f"{key}:tokens")
        raw_updated = await self.client.get(f"{key}:updated")
        tokens = float(raw_tokens or config.tokens_per_minute)
        updated = float(raw_updated or now)
        tokens = min(config.tokens_per_minute, tokens + (now - updated) * refill_per_second)

        if tokens < estimated_tokens:
            retry_after = math.ceil((estimated_tokens - tokens) / refill_per_second)
            await self.client.incr(f"{key}:limited")
            await self.client.expire(f"{key}:limited", 120)
            return False, retry_after

        tokens -= estimated_tokens
        await self.client.set(f"{key}:tokens", tokens, ex=120)
        await self.client.set(f"{key}:updated", now, ex=120)
        await self.client.incr(f"{key}:accepted")
        await self.client.expire(f"{key}:accepted", 120)
        return True, 0

    def _consume_memory(self, api_key: str, config: ApiKeyConfig, estimated_tokens: int) -> tuple[bool, int]:
        now = time.time()
        refill_per_second = config.tokens_per_minute / 60
        tokens, updated = _memory_buckets.get(api_key, (config.tokens_per_minute, now))
        tokens = min(config.tokens_per_minute, tokens + (now - updated) * refill_per_second)
        if tokens < estimated_tokens:
            return False, math.ceil((estimated_tokens - tokens) / refill_per_second)
        _memory_buckets[api_key] = (tokens - estimated_tokens, now)
        return True, 0
