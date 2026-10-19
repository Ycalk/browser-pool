from typing import Self

from browserpool.database import Browser as BrowserPersistence
from browserpool.database import Sandbox as SandboxPersistence
from pydantic import BaseModel


class Sandbox(BaseModel):
    network_id: str
    network_name: str
    index: int
    active: bool

    @classmethod
    def from_persistence(cls, model: SandboxPersistence) -> Self:
        return cls(
            network_id=model.network_id,
            network_name=model.network_name,
            index=model.index,
            active=model.active,
        )


class Browser(BaseModel):
    container_id: str
    variant: str
    sandbox: Sandbox
    host: str
    port: int
    created_at: int
    last_touched_at: int
    idle_ttl_seconds: int
    active: bool

    @classmethod
    def from_persistence(cls, model: BrowserPersistence) -> Self:
        return cls(
            container_id=model.container_id,
            variant=model.variant,
            sandbox=Sandbox.from_persistence(model.sandbox),
            host=model.host,
            port=model.port,
            created_at=int(model.created_at.timestamp()),
            last_touched_at=int(model.last_touched_at.timestamp()),
            idle_ttl_seconds=model.idle_ttl_seconds,
            active=model.active,
        )
