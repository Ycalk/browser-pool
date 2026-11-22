from browserpool.entrypoint.security import secret_key_check
from browserpool.service import (
    Browser,
    CreateBrowserCommand,
    CreateBrowserParameters,
    GetBrowserCommand,
    GetBrowserParameters,
    ListBrowsersCommand,
    RemoveBrowserCommand,
    RemoveBrowserParameters,
    TouchBrowserCommand,
    TouchBrowserParameters,
)
from dishka.integrations.fastapi import DishkaRoute, FromDishka
from fastapi import APIRouter, Request, Response, Security, status

router = APIRouter(
    prefix="/browsers",
    tags=["browsers"],
    route_class=DishkaRoute,
)


@router.get("", status_code=status.HTTP_200_OK)
async def list_browsers(
    command: FromDishka[ListBrowsersCommand],
    _: None = Security(secret_key_check),
) -> list[Browser]:
    return await command()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_browser(
    parameters: CreateBrowserParameters,
    command: FromDishka[CreateBrowserCommand],
    request: Request,
    response: Response,
    _: None = Security(secret_key_check),
) -> Browser:
    browser = await command(parameters)
    response.headers["Location"] = str(
        request.url_for("get_browser", container_id=browser.container_id)
    )
    return browser


@router.get("/{container_id}", status_code=status.HTTP_200_OK)
async def get_browser(
    container_id: str,
    command: FromDishka[GetBrowserCommand],
    _: None = Security(secret_key_check),
) -> Browser:
    return await command(GetBrowserParameters(container_id=container_id))


@router.post("/{container_id}/touch", status_code=status.HTTP_200_OK)
async def touch_browser(
    container_id: str,
    command: FromDishka[TouchBrowserCommand],
    _: None = Security(secret_key_check),
) -> Browser:
    return await command(TouchBrowserParameters(container_id=container_id))


@router.delete("/{container_id}", status_code=status.HTTP_200_OK)
async def remove_browser(
    container_id: str,
    command: FromDishka[RemoveBrowserCommand],
    _: None = Security(secret_key_check),
) -> Browser:
    return await command(RemoveBrowserParameters(container_id=container_id))
