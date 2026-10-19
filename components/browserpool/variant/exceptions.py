from browserpool.domain_core import (
    FatalError,
)


class BrowserConfigurationError(FatalError):
    pass


class BrowserNotReadyError(FatalError):
    pass
