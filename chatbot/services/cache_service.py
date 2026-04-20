import asyncio
from django.core.cache import cache
from asgiref.sync import sync_to_async
from typing import Any, Callable, Optional


class CacheService:
    """
    Standardized caching service using the configured Redis backend.
    Hardened for Async environments.
    """

    @staticmethod
    async def get(key: str) -> Any:
        """
        Retrieves a value from cache safely in async.
        """
        return await sync_to_async(cache.get)(key)

    @staticmethod
    async def set(key: str, value: Any, timeout: int = 300):
        """
        Stores a value in cache safely in async.
        """
        await sync_to_async(cache.set)(key, value, timeout)

    @staticmethod
    async def get_or_set(key: str, callback: Callable, timeout: int = 300) -> Any:
        """
        Retrieves a value from cache or executes the callback.
        Supports both Sync and Async callbacks.
        """
        value = await CacheService.get(key)
        
        if value is None:
            if asyncio.iscoroutinefunction(callback):
                value = await callback()
            else:
                value = await sync_to_async(callback, thread_sensitive=False)()
            
            await CacheService.set(key, value, timeout)
            
        return value

    @staticmethod
    async def invalidate(key: str):
        """
        Removes a key from cache.
        """
        await sync_to_async(cache.delete)(key)

    @staticmethod
    async def clear():
        """
        Wipes the entire cache.
        """
        await sync_to_async(cache.clear)()
