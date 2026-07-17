from fastapi import HTTPException, status

from app.redis import redis_client


async def enforce_rate_limit(key: str, limit: int) -> None:
    redis_key = f"rate:{key}"
    count = await redis_client.incr(redis_key)
    if count == 1:
        await redis_client.expire(redis_key, 60)
    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )
