from dishka import Provider, Scope, provide, provide_all
from dishka.dependency_source import CompositeDependencySource

from .commands import (
    CreateBrowserCommand,
    ReapIdleBrowsersCommand,
    ReconcileBrowsersCommand,
    ReconcileSandboxesCommand,
)
from .settings import ServiceSettings


class ServiceProvider(Provider):
    commands: CompositeDependencySource = provide_all(
        CreateBrowserCommand,
        ReapIdleBrowsersCommand,
        ReconcileBrowsersCommand,
        ReconcileSandboxesCommand,
        scope=Scope.REQUEST,
    )

    @provide(scope=Scope.APP)
    def settings(self) -> ServiceSettings:
        return ServiceSettings()  # type: ignore # pyright: ignore
