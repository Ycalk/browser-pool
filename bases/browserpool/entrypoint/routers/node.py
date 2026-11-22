from browserpool.entrypoint.security import secret_key_check
from browserpool.service import (
    Browser,
    NodeInfoCommand,
    NodeInfoResponse,
    ReapIdleBrowsersCommand,
    ReconcileBrowsersCommand,
    ReconcileBrowsersResponse,
    ReconcileSandboxesCommand,
    ReconcileSandboxesResponse,
)
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Security, status

router = APIRouter(
    prefix="/node",
    tags=["node"],
    route_class=DishkaRoute,
)


@router.get("", status_code=status.HTTP_200_OK)
async def node_info(
    command: FromDishka[NodeInfoCommand],
    _: None = Security(secret_key_check),
) -> NodeInfoResponse:
    return await command()


@router.post("/reap", status_code=status.HTTP_200_OK)
async def reap_idle_browsers(
    command: FromDishka[ReapIdleBrowsersCommand],
    _: None = Security(secret_key_check),
) -> list[Browser]:
    return await command()


@router.post("/reconcile/browsers", status_code=status.HTTP_200_OK)
async def reconcile_browsers(
    command: FromDishka[ReconcileBrowsersCommand],
    _: None = Security(secret_key_check),
) -> ReconcileBrowsersResponse:
    return await command()


@router.post("/reconcile/sandboxes", status_code=status.HTTP_200_OK)
async def reconcile_sandboxes(
    command: FromDishka[ReconcileSandboxesCommand],
    _: None = Security(secret_key_check),
) -> ReconcileSandboxesResponse:
    return await command()
