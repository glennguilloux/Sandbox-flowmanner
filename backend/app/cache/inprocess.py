"""In-process TTL caching for frequently-read, rarely-changed data."""

import functools
import hashlib
import logging
from collections.abc import Callable

from cachetools import TTLCache

from app.core.metrics import record_cache_hit, record_cache_miss

logger = logging.getLogger(__name__)

# Caches for different data categories
_feature_flags_cache = TTLCache(maxsize=1, ttl=60)  # 60s — flags change rarely
_agent_templates_cache = TTLCache(maxsize=64, ttl=300)  # 5min — static templates
_config_cache = TTLCache(maxsize=1, ttl=300)  # 5min — app config
_generic_cache = TTLCache(maxsize=256, ttl=120)  # 2min — misc


def cached_feature_flags(func: Callable) -> Callable:
    """Cache feature flag queries (60s TTL)."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        key = "feature_flags_all"
        result = _feature_flags_cache.get(key)
        if result is not None:
            record_cache_hit("feature_flags")
            return result
        record_cache_miss("feature_flags")
        result = await func(*args, **kwargs)
        _feature_flags_cache[key] = result
        return result

    return wrapper


def cached_agent_templates(func: Callable) -> Callable:
    """Cache agent template lookups (5min TTL)."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Build cache key from function name + args
        cache_key = f"{func.__name__}:{hashlib.md5(str((args, kwargs)).encode()).hexdigest()}"
        result = _agent_templates_cache.get(cache_key)
        if result is not None:
            record_cache_hit("agent_templates")
            return result
        record_cache_miss("agent_templates")
        result = func(*args, **kwargs)
        _agent_templates_cache[cache_key] = result
        return result

    return wrapper


def cached_config(func: Callable) -> Callable:
    """Cache config/settings lookups (5min TTL)."""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        key = f"config:{func.__name__}"
        result = _config_cache.get(key)
        if result is not None:
            record_cache_hit("config")
            return result
        record_cache_miss("config")
        result = await func(*args, **kwargs)
        _config_cache[key] = result
        return result

    return wrapper


def cached(ttl: int = 120, maxsize: int = 64, cache_name: str = "generic") -> Callable:
    """Generic cache decorator with configurable TTL."""
    _cache = TTLCache(maxsize=maxsize, ttl=ttl)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{hashlib.md5(str((args, kwargs)).encode()).hexdigest()}"
            result = _cache.get(cache_key)
            if result is not None:
                record_cache_hit(cache_name)
                return result
            record_cache_miss(cache_name)
            result = await func(*args, **kwargs)
            _cache[cache_key] = result
            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache_key = f"{func.__name__}:{hashlib.md5(str((args, kwargs)).encode()).hexdigest()}"
            result = _cache.get(cache_key)
            if result is not None:
                record_cache_hit(cache_name)
                return result
            record_cache_miss(cache_name)
            result = func(*args, **kwargs)
            _cache[cache_key] = result
            return result

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def invalidate_feature_flags():
    """Clear feature flags cache (call after mutations)."""
    _feature_flags_cache.clear()
    logger.debug("Feature flags cache invalidated")


def invalidate_agent_templates():
    """Clear agent templates cache."""
    _agent_templates_cache.clear()
    logger.debug("Agent templates cache invalidated")


def invalidate_all():
    """Clear all in-process caches."""
    _feature_flags_cache.clear()
    _agent_templates_cache.clear()
    _config_cache.clear()
    _generic_cache.clear()
    logger.info("All in-process caches invalidated")
