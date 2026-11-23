from hmac import compare_digest

from dishka.integrations.fastapi import FromDishka, inject
from fastapi import Depends, Request, status
from fastapi.security import APIKeyHeader
from fastapi.security.utils import get_authorization_scheme_param

from .exceptions import CustomHTTPException
from .settings import EntrypointSettings

security = APIKeyHeader(
    name="Authorization",
    scheme_name="Secret key authorization",
    description=(
        "Для использования метода "
        "необходимо передать токен в заголовке "
        "Authorization в формате 'SECRET <токен>'."
    ),
)


@inject
def secret_key_check(
    api_settings: FromDishka[EntrypointSettings], header_value: str = Depends(security)
) -> None:
    try:
        scheme, api_key = get_authorization_scheme_param(header_value)
        if not scheme or scheme.lower() != "secret":
            raise CustomHTTPException(
                error="InvalidScheme",
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Invalid authentication scheme",
                headers={"WWW-Authenticate": "SECRET"},
            )
        if not api_key:
            raise CustomHTTPException(
                error="InvalidCredentials",
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Missing authentication credentials",
                headers={"WWW-Authenticate": "SECRET"},
            )
        if not compare_digest(api_key, api_settings.api_secret_key):
            raise CustomHTTPException(
                error="InvalidCredentials",
                status_code=status.HTTP_401_UNAUTHORIZED,
                message="Invalid authentication credentials",
                headers={"WWW-Authenticate": "SECRET"},
            )
    except CustomHTTPException:
        raise
    except Exception as e:
        raise CustomHTTPException.from_exception(
            e,
            status_code=status.HTTP_401_UNAUTHORIZED,
            message="Invalid authentication credentials",
            headers={"WWW-Authenticate": "SECRET"},
        )


def localhost_only(request: Request) -> None:
    client = request.client
    host = client.host if client is not None else None
    if host not in {"127.0.0.1", "::1"}:
        raise CustomHTTPException(
            error="Forbidden",
            status_code=status.HTTP_403_FORBIDDEN,
            message="Available only from localhost",
        )
