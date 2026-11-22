from dishka import Provider, Scope, provide, provide_all
from dishka.dependency_source import CompositeDependencySource

from .commands import (
    CreateBrowserCommand,
    GetBrowserCommand,
    ListBrowsersCommand,
    NodeInfoCommand,
    ReapIdleBrowsersCommand,
    ReconcileBrowsersCommand,
    ReconcileSandboxesCommand,
    RemoveBrowserCommand,
    TouchBrowserCommand,
)
from .settings import ServiceSettings


class ServiceProvider(Provider):
    commands: CompositeDependencySource = provide_all(
        CreateBrowserCommand,
        GetBrowserCommand,
        ListBrowsersCommand,
        NodeInfoCommand,
        ReapIdleBrowsersCommand,
        ReconcileBrowsersCommand,
        ReconcileSandboxesCommand,
        RemoveBrowserCommand,
        TouchBrowserCommand,
        scope=Scope.REQUEST,
    )

    @provide(scope=Scope.APP)
    def settings(self) -> ServiceSettings:
        return ServiceSettings()  # type: ignore # pyright: ignore
