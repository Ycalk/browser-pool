import asyncio

import httpx
import structlog
from dishka import make_async_container

from .core import EntrypointSettingsProvider
from .settings import EntrypointSettings

logger = structlog.get_logger(__name__)

_ENDPOINTS = (
    "/node/reconcile/sandboxes",
    "/node/reconcile/browsers",
    "/node/reap",
)


async def _wait_for_api(client: httpx.AsyncClient, base_url: str) -> None:
    while True:
        try:
            response = await client.get(f"{base_url}/ping")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        await asyncio.sleep(1)


async def _run_worker() -> None:
    container = make_async_container(EntrypointSettingsProvider())

    settings = await container.get(EntrypointSettings)
    base_url = f"http://127.0.0.1:{settings.api_port}"
    interval = settings.worker_interval_seconds

    async with httpx.AsyncClient(timeout=60) as client:
        await _wait_for_api(client, base_url)
        logger.info("worker_started", base_url=base_url, interval=interval)
        while True:
            for endpoint in _ENDPOINTS:
                try:
                    response = await client.post(
                        f"{base_url}{settings.methods_prefix}{endpoint}"
                    )
                    logger.info(
                        "worker_call",
                        endpoint=endpoint,
                        status_code=response.status_code,
                    )
                except httpx.HTTPError as exc:
                    logger.warning(
                        "worker_call_failed",
                        endpoint=endpoint,
                        error=str(exc),
                    )
            await asyncio.sleep(interval)


def run_worker() -> None:
    asyncio.run(_run_worker())


if __name__ == "__main__":
    run_worker()
