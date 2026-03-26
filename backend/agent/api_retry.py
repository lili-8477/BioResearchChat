"""Retry wrapper for Claude API calls — handles transient 500/429/timeout errors."""

import asyncio
import logging

import anthropic

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {429, 500, 502, 503, 529}
MAX_RETRIES = 3
BASE_DELAY = 2  # seconds


async def api_call_with_retry(client: anthropic.AsyncAnthropic, **kwargs) -> anthropic.types.Message:
    """Call client.messages.create with automatic retry on transient errors.

    Retries on: 429 (rate limit), 500/502/503 (server errors), 529 (overloaded).
    Uses exponential backoff: 2s, 4s, 8s.
    """
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            last_error = e
            if e.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Claude API {e.status_code} (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                    f"retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
                continue
            raise
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = BASE_DELAY * (2 ** attempt)
                logger.warning(
                    f"Claude API connection error (attempt {attempt + 1}/{MAX_RETRIES + 1}), "
                    f"retrying in {delay}s: {e}"
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise last_error  # should not reach here
