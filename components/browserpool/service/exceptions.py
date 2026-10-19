from browserpool.domain_core import (
    DomainBadRequestException,
    DomainConflictException,
    FatalError,
)


class InvalidBrowserError(FatalError):
    pass


class InvalidSandboxError(FatalError):
    pass


class BrowserLimitExceeded(DomainConflictException):
    pass


class InvalidIdleTTL(DomainBadRequestException):
    pass
