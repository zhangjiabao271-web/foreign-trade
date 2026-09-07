import asyncio
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class DependencyTarget:
    name: str
    host: str
    port: int


async def check_tcp_dependency(target: DependencyTarget, timeout_seconds: float) -> bool:
    """Check reachability without turning a health endpoint into an expensive query."""

    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(target.host, target.port),
            timeout=timeout_seconds,
        )
    except (OSError, TimeoutError):
        return False

    writer.close()
    await writer.wait_closed()
    return True


async def check_dependencies(settings: Settings) -> dict[str, bool]:
    targets = (
        DependencyTarget("postgres", settings.database_host, settings.database_port),
        DependencyTarget("redis", settings.redis_host, settings.redis_port),
        DependencyTarget("minio", settings.minio_host, settings.minio_port),
    )
    results = await asyncio.gather(
        *(check_tcp_dependency(target, settings.dependency_timeout_seconds) for target in targets)
    )
    return {target.name: result for target, result in zip(targets, results, strict=True)}
