from browserpool.domain_core import (
    DomainConflictException,
    DomainException,
    DomainNotFoundException,
    FatalError,
)


class DockerBadRequestException(DomainException):
    pass


class DockerNotFoundException(DomainNotFoundException):
    pass


class DockerConflictException(DomainConflictException):
    pass


class DockerFatalError(FatalError):
    pass
