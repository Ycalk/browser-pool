from browserpool.entrypoint.security import localhost_only, secret_key_check
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


@router.post("/reap", status_code=status.HTTP_200_OK, include_in_schema=False)
async def reap_idle_browsers(
    command: FromDishka[ReapIdleBrowsersCommand],
    _localhost: None = Security(localhost_only),
) -> list[Browser]:
    return await command()


@router.post(
    "/reconcile/browsers", status_code=status.HTTP_200_OK, include_in_schema=False
)
async def reconcile_browsers(
    command: FromDishka[ReconcileBrowsersCommand],
    _localhost: None = Security(localhost_only),
) -> ReconcileBrowsersResponse:
    return await command()


@router.post(
    "/reconcile/sandboxes", status_code=status.HTTP_200_OK, include_in_schema=False
)
async def reconcile_sandboxes(
    command: FromDishka[ReconcileSandboxesCommand],
    _localhost: None = Security(localhost_only),
) -> ReconcileSandboxesResponse:
    return await command()
