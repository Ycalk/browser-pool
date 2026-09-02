from typing import Protocol

from pydantic import BaseModel


class Command[TParameters: BaseModel, TResult](Protocol):
    async def __call__(self, parameters: TParameters) -> TResult: ...


class ParameterlessCommand[TResult](Protocol):
    async def __call__(self) -> TResult: ...


class DomainException(Exception):
    def __init__(self, message: str) -> None:
        self.message: str = message
        super().__init__(message)


class DomainUnauthorizedException(DomainException):
    pass


class DomainForbiddenException(DomainException):
    pass


class DomainNotFoundException(DomainException):
    pass


class DomainConflictException(DomainException):
    pass


class FatalError(DomainException):
    pass
