import asyncio

from browserpool.container_driver import (
    ContainerConfig,
    ContainerDriverProvider,
    CreateContainerCommand,
    EndpointConfig,
    Healthcheck,
    HostBind,
    HostConfig,
    NetworkingConfig,
    RemoveContainerCommand,
    RemoveContainerParameters,
    StartContainerCommand,
    StartContainerParameters,
    StopContainerCommand,
    StopContainerParameters,
    Ulimit,
)
from browserpool.logging import LoggingSettings, LoggingSettingsProvider, setup_logging
from dishka import make_async_container
from httpx import AsyncClient


async def main():
    container = make_async_container(
        ContainerDriverProvider(), LoggingSettingsProvider()
    )
    logging_settings = await container.get(LoggingSettings)
    setup_logging(logging_settings, "start_container")

    async with container() as request_container:
        create_method = await request_container.get(CreateContainerCommand)
        create_response = await create_method(
            ContainerConfig(
                image="nginx:alpine",
                name="sandbox-validator",
                hostname="sandbox-host",
                command="nginx -g 'daemon off;'",
                environment={
                    "DEBUG_MODE": "true",
                    "SERVICE_NAME": "proxy-validator",
                },
                ports=[80, (443, "tcp")],
                labels={
                    "env": "staging",
                    "managed-by": "python-engine",
                },
                detach=True,
                healthcheck=Healthcheck(
                    test=[
                        "CMD-SHELL",
                        "wget -qO- http://127.0.0.1:80/ > /dev/null || exit 1",
                    ],
                    interval=5_000_000_000,
                    timeout=2_000_000_000,
                    retries=3,
                    start_period=1_000_000_000,
                ),
                networking_config=NetworkingConfig(
                    endpoints_config={
                        "bridge": EndpointConfig(
                            links={"db": "database"},
                        )
                    }
                ),
                host_config=HostConfig(
                    auto_remove=False,
                    mem_limit=(256, "m"),
                    shm_size=(64, "m"),
                    cpu_period=100000,
                    cpu_quota=50000,
                    port_bindings={
                        80: [("127.0.0.1", 8888)],
                    },
                    binds={
                        "/tmp": HostBind(bind="/mnt/shared_tmp", mode="rw"),
                    },
                    tmpfs={"/var/cache/nginx": "size=32m"},
                    ulimits=[
                        Ulimit(name="nofile", soft=1024, hard=2048),
                    ],
                    extra_hosts={"mock.local": "127.0.0.1"},
                    restart_policy="no",
                    network_mode="bridge",
                ),
            )
        )
        print(f"Container created: {create_response.container_id}")
        await (await request_container.get(StartContainerCommand))(
            StartContainerParameters(container_id=create_response.container_id)
        )
        await asyncio.sleep(1)
        async with AsyncClient() as client:
            response = await client.get("http://127.0.0.1:8888", timeout=3)
            assert response.status_code == 200
            assert "Welcome to nginx!" in response.text
            print(f"HTTP Request to container: {response.status_code}")

        await (await request_container.get(StopContainerCommand))(
            StopContainerParameters(id=create_response.container_id)
        )
        print("Container stopped")
        await (await request_container.get(RemoveContainerCommand))(
            RemoveContainerParameters(id=create_response.container_id)
        )
        print("Container removed")


def run():
    asyncio.run(main())
