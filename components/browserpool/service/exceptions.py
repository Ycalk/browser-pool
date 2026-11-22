from browserpool.domain_core import (
    DomainBadRequestException,
    DomainConflictException,
    DomainNotFoundException,
    FatalError,
)


class BrowserNotFound(DomainNotFoundException):
    pass


class InvalidBrowserError(FatalError):
    pass


class InvalidSandboxError(FatalError):
    pass


class BrowserLimitExceeded(DomainConflictException):
    pass


class InvalidIdleTTL(DomainBadRequestException):
    pass
