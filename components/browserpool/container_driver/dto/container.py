from __future__ import annotations

import shlex
from typing import Annotated, Any, Literal

from pydantic import (
    AliasPath,
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    computed_field,
)


class ContainerConfig(BaseModel):
    image: Annotated[str, Field(serialization_alias="Image")]
    command: Annotated[
        list[str] | str | None,
        Field(serialization_alias="Cmd"),
        PlainSerializer(
            lambda value: shlex.split(value) if isinstance(value, str) else value,
            return_type=list[str] | None,
        ),
    ] = None
    hostname: Annotated[str | None, Field(serialization_alias="Hostname")] = None
    user: Annotated[
        str | None,
        Field(serialization_alias="User"),
    ] = None
    detach: Annotated[bool, Field(exclude=True)] = False
    stdin_open: Annotated[bool, Field(serialization_alias="OpenStdin")] = False
    tty: Annotated[bool, Field(serialization_alias="Tty")] = False
    ports: Annotated[
        list[int | tuple[int, Literal["tcp", "udp"]]] | None,
        Field(serialization_alias="ExposedPorts"),
        PlainSerializer(
            lambda value: (
                {
                    f"{port}/tcp"
                    if isinstance(port, int)
                    else f"{port[0]}/{port[1]}": {}
                    for port in value
                }
                if value is not None
                else None
            ),
            return_type=dict[str, dict[str, Any]] | None,
        ),
    ] = None
    environment: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="Env"),
        PlainSerializer(
            lambda value: (
                [f"{k}={v}" for k, v in value.items()] if value is not None else None
            ),
            return_type=list[str] | None,
        ),
    ] = None
    volumes: Annotated[
        list[str] | None,
        Field(serialization_alias="Volumes"),
        PlainSerializer(
            lambda value: (
                {volume: {} for volume in value} if value is not None else None
            ),
            return_type=dict[str, dict[str, Any]] | None,
        ),
    ] = None
    network_disabled: Annotated[bool, Field(serialization_alias="NetworkDisabled")] = (
        False
    )
    name: Annotated[str | None, Field(exclude=True)] = None
    entrypoint: Annotated[
        list[str] | str | None,
        Field(serialization_alias="Entrypoint"),
        PlainSerializer(
            lambda value: shlex.split(value) if isinstance(value, str) else value,
            return_type=list[str] | None,
        ),
    ] = None
    working_dir: Annotated[str | None, Field(serialization_alias="WorkingDir")] = None
    domainname: Annotated[str | None, Field(serialization_alias="Domainname")] = None
    host_config: Annotated[
        HostConfig | None, Field(serialization_alias="HostConfig")
    ] = None
    mac_address: Annotated[str | None, Field(serialization_alias="MacAddress")] = None
    labels: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="Labels"),
    ] = None
    stop_signal: Annotated[str | None, Field(serialization_alias="StopSignal")] = None
    stop_timeout: Annotated[int | None, Field(serialization_alias="StopTimeout")] = None
    networking_config: Annotated[
        NetworkingConfig | None, Field(serialization_alias="NetworkingConfig")
    ] = None
    healthcheck: Annotated[
        Healthcheck | None, Field(serialization_alias="Healthcheck")
    ] = None
    platform: Annotated[str | None, Field(exclude=True)] = None

    @computed_field(alias="AttachStdout")
    @property
    def attach_stdout(self) -> bool:
        return not self.detach

    @computed_field(alias="AttachStderr")
    @property
    def attach_stderr(self) -> bool:
        return not self.detach

    @computed_field(alias="AttachStdin")
    @property
    def attach_stdin(self) -> bool:
        return not self.detach and self.stdin_open

    @computed_field(alias="StdinOnce")
    @property
    def stdin_once(self) -> bool:
        return not self.detach and self.stdin_open


class HostConfig(BaseModel):
    auto_remove: Annotated[bool, Field(serialization_alias="AutoRemove")] = False
    binds: Annotated[
        dict[str, HostBind] | None,
        Field(serialization_alias="Binds"),
        PlainSerializer(
            lambda value: (
                [
                    f"{k}:{v.bind}:{v.mode}"
                    + (f",{v.propagation}" if v.propagation else "")
                    for k, v in value.items()
                ]
                if value is not None
                else None
            ),
            return_type=list[str] | None,
        ),
    ] = None
    cap_add: Annotated[list[str] | None, Field(serialization_alias="CapAdd")] = None
    cap_drop: Annotated[list[str] | None, Field(serialization_alias="CapDrop")] = None
    cpu_period: Annotated[int | None, Field(serialization_alias="CpuPeriod")] = None
    cpu_quota: Annotated[int | None, Field(serialization_alias="CpuQuota")] = None
    cpu_shares: Annotated[int | None, Field(serialization_alias="CpuShares")] = None
    cpuset_cpus: Annotated[str | None, Field(serialization_alias="CpusetCpus")] = None
    cpuset_mems: Annotated[str | None, Field(serialization_alias="CpusetMems")] = None
    device_cgroup_rules: Annotated[
        list[str] | None, Field(serialization_alias="DeviceCgroupRules")
    ] = None
    devices: Annotated[
        list[HostDevice] | None, Field(serialization_alias="Devices")
    ] = None
    device_requests: Annotated[
        list[DeviceRequest] | None, Field(serialization_alias="DeviceRequests")
    ] = None
    dns: Annotated[list[str] | None, Field(serialization_alias="Dns")] = None
    dns_options: Annotated[
        list[str] | None, Field(serialization_alias="DnsOptions")
    ] = None
    dns_search: Annotated[list[str] | None, Field(serialization_alias="DnsSearch")] = (
        None
    )
    extra_hosts: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="ExtraHosts"),
        PlainSerializer(
            lambda value: (
                [f"{k}:{v}" for k, v in value.items()] if value is not None else value
            ),
            return_type=list[str] | None,
        ),
    ] = None
    group_add: Annotated[
        list[str] | None,
        Field(serialization_alias="GroupAdd"),
    ] = None
    init: Annotated[bool | None, Field(serialization_alias="Init")] = None
    ipc_mode: Annotated[str | None, Field(serialization_alias="IpcMode")] = None
    isolation: Annotated[str | None, Field(serialization_alias="Isolation")] = None
    links: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="Links"),
        PlainSerializer(
            lambda value: (
                [f"{k}:{v}" for k, v in value.items()] if value is not None else value
            ),
            return_type=list[str] | None,
        ),
    ] = None
    log_config: Annotated[LogConfig | None, Field(serialization_alias="LogConfig")] = (
        None
    )
    lxc_conf: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="LxcConf"),
        PlainSerializer(
            lambda value: (
                [{"Key": k, "Value": v} for k, v in value.items()]
                if value is not None
                else value
            ),
            return_type=list[dict[str, str]] | None,
        ),
    ] = None
    mem_limit: Annotated[
        tuple[int, Literal["b", "k", "m", "g"]] | None,
        Field(serialization_alias="Memory"),
        PlainSerializer(
            lambda value: (
                value[0]
                * {"b": 1 << 0, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}.get(value[1])
                if value is not None
                else value
            ),
            return_type=int | None,
        ),
    ] = None
    mem_reservation: Annotated[
        tuple[int, Literal["b", "k", "m", "g"]] | None,
        Field(serialization_alias="MemoryReservation"),
        PlainSerializer(
            lambda value: (
                value[0]
                * {"b": 1 << 0, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}.get(value[1])
                if value is not None
                else value
            ),
            return_type=int | None,
        ),
    ] = None
    mem_swappiness: Annotated[
        int | None, Field(serialization_alias="MemorySwappiness")
    ] = None
    memswap_limit: Annotated[
        tuple[int, Literal["b", "k", "m", "g"]] | None,
        Field(serialization_alias="MemorySwap"),
        PlainSerializer(
            lambda value: (
                value[0]
                * {"b": 1 << 0, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}.get(value[1])
                if value is not None
                else value
            ),
            return_type=int | None,
        ),
    ] = None
    mounts: Annotated[list[Mount] | None, Field(serialization_alias="Mounts")] = None
    network_mode: Annotated[str, Field(serialization_alias="NetworkMode")] = "default"
    oom_kill_disable: Annotated[bool, Field(serialization_alias="OomKillDisable")] = (
        False
    )
    oom_score_adj: Annotated[int | None, Field(serialization_alias="OomScoreAdj")] = (
        None
    )
    pid_mode: Annotated[str | None, Field(serialization_alias="PidMode")] = None
    pids_limit: Annotated[int | None, Field(serialization_alias="PidsLimit")] = None
    port_bindings: Annotated[
        dict[int | tuple[int, Literal["tcp", "udp"]], list[tuple[str, int]]] | None,
        Field(serialization_alias="PortBindings"),
        PlainSerializer(
            lambda value: (
                {
                    f"{container_binds}/tcp"
                    if isinstance(container_binds, int)
                    else f"{container_binds[0]}/{container_binds[1]}": [
                        {"HostIp": ip, "HostPort": str(port)} for ip, port in host_binds
                    ]
                    for container_binds, host_binds in value.items()
                }
                if value is not None
                else None
            ),
            return_type=dict[str, list[dict[str, str | int]]] | None,
        ),
    ] = None
    privileged: Annotated[bool, Field(serialization_alias="Privileged")] = False
    publish_all_ports: Annotated[bool, Field(serialization_alias="PublishAllPorts")] = (
        False
    )
    read_only: Annotated[bool | None, Field(serialization_alias="ReadonlyRootfs")] = (
        None
    )
    restart_policy: Annotated[
        Literal["always", "no", "unless-stopped"],
        tuple[Literal["on-failure"], int] | None,
        Field(serialization_alias="RestartPolicy"),
        PlainSerializer(
            lambda value: (
                (
                    {"Name": value[0], "MaximumRetryCount": value[1]}
                    if isinstance(value, tuple)
                    else {"Name": value}
                )
                if value is not None
                else None
            ),
            return_type=dict[str, str | int] | None,
        ),
    ]
    security_opt: Annotated[
        list[str] | None, Field(serialization_alias="SecurityOpt")
    ] = None
    shm_size: Annotated[
        tuple[int, Literal["b", "k", "m", "g"]] | None,
        Field(serialization_alias="ShmSize"),
        PlainSerializer(
            lambda value: (
                value[0]
                * {"b": 1 << 0, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}.get(value[1])
                if value is not None
                else value
            ),
            return_type=int | None,
        ),
    ] = None
    storage_opt: Annotated[
        dict[str, str] | None, Field(serialization_alias="StorageOpt")
    ] = None
    sysctls: Annotated[dict[str, str] | None, Field(serialization_alias="Sysctls")] = (
        None
    )
    tmpfs: Annotated[dict[str, str] | None, Field(serialization_alias="Tmpfs")] = None
    ulimits: Annotated[list[Ulimit] | None, Field(serialization_alias="Ulimits")] = None
    userns_mode: Annotated[
        Literal["host"] | None, Field(serialization_alias="UsernsMode")
    ] = None
    uts_mode: Annotated[
        Literal["host"] | None, Field(serialization_alias="UTSMode")
    ] = None
    volumes_from: Annotated[
        list[str] | None, Field(serialization_alias="VolumesFrom")
    ] = None
    runtime: Annotated[str | None, Field(serialization_alias="Runtime")] = None


class HostBind(BaseModel):
    bind: str
    mode: str = "rw"
    propagation: (
        Literal["rshared", "shared", "rslave", "slave", "rprivate", "private"] | None
    ) = None


class HostDevice(BaseModel):
    path_on_host: Annotated[str, Field(serialization_alias="PathOnHost")]
    path_in_container: Annotated[str, Field(serialization_alias="PathInContainer")]
    cgroup_permissions: Annotated[
        str, Field(serialization_alias="CgroupPermissions")
    ] = "rwm"


class DeviceRequest(BaseModel):
    driver: Annotated[str | None, Field(serialization_alias="Driver")] = None
    count: Annotated[int | None, Field(serialization_alias="Count")] = None
    device_ids: Annotated[list[str] | None, Field(serialization_alias="DeviceIDs")] = (
        None
    )
    capabilities: Annotated[
        list[list[str]] | None, Field(serialization_alias="Capabilities")
    ] = None
    options: Annotated[dict[str, str] | None, Field(serialization_alias="Options")] = (
        None
    )


class LogConfig(BaseModel):
    type: Annotated[
        Literal[
            "json-file",
            "syslog",
            "journald",
            "gelf",
            "fluentd",
            "none",
            "local",
            "awslogs",
            "splunk",
            "etwlogs",
        ]
        | None,
        Field(serialization_alias="Type"),
    ] = None
    config: Annotated[
        dict[str, str],
        Field(serialization_alias="Config"),
    ] = {}


class Mount(BaseModel):
    target: Annotated[str, Field(serialization_alias="Target")]
    source: Annotated[str, Field(serialization_alias="Source")]
    type: Annotated[
        Literal["bind", "volume", "tmpfs", "npipe", "cluster", "image"],
        Field(serialization_alias="Type"),
    ] = "volume"
    read_only: Annotated[bool, Field(serialization_alias="ReadOnly")] = False
    consistency: Annotated[
        Literal["default", "consistent", "cached", "delegated"] | None,
        Field(serialization_alias="Consistency"),
    ] = None
    bind_options: Annotated[
        BindOptions | None,
        Field(serialization_alias="BindOptions"),
    ] = None
    volume_options: Annotated[
        VolumeOptions | None,
        Field(serialization_alias="VolumeOptions"),
    ] = None
    subpath: Annotated[
        str | None,
        Field(serialization_alias="ImageOptions"),
        PlainSerializer(
            lambda value: {"Subpath": value},
            return_type=dict[str, str | None],
        ),
    ]
    tmpfs_options: Annotated[
        TmpfsOptions | None,
        Field(serialization_alias="TmpfsOptions"),
    ] = None


class BindOptions(BaseModel):
    propagation: Annotated[
        Literal["private", "rprivate", "shared", "rshared", "slave", "rslave"] | None,
        Field(serialization_alias="Propagation"),
    ] = None
    non_recursive: Annotated[
        bool,
        Field(serialization_alias="NonRecursive"),
    ] = False
    create_mountpoint: Annotated[
        bool,
        Field(serialization_alias="CreateMountpoint"),
    ] = False
    readonly_non_recursive: Annotated[
        bool,
        Field(serialization_alias="ReadOnlyNonRecursive"),
    ] = False
    readonly_force_recursive: Annotated[
        bool,
        Field(serialization_alias="ReadOnlyForceRecursive"),
    ] = False


class VolumeOptions(BaseModel):
    no_copy: Annotated[
        bool,
        Field(serialization_alias="NoCopy"),
    ] = False
    labels: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="Labels"),
    ] = None
    driver_config: Annotated[
        DriverConfig | None,
        Field(serialization_alias="DriverConfig"),
    ] = None
    subpath: Annotated[
        str | None,
        Field(serialization_alias="Subpath"),
    ] = None


class DriverConfig(BaseModel):
    name: Annotated[
        str,
        Field(serialization_alias="Name"),
    ]
    options: Annotated[
        dict[str, str],
        Field(serialization_alias="Options"),
    ]


class TmpfsOptions(BaseModel):
    size: Annotated[
        tuple[int, Literal["b", "k", "m", "g"]] | None,
        Field(serialization_alias="SizeBytes"),
        PlainSerializer(
            lambda value: (
                value[0]
                * {"b": 1 << 0, "k": 1 << 10, "m": 1 << 20, "g": 1 << 30}.get(value[1])
                if value is not None
                else value
            ),
            return_type=int | None,
        ),
    ] = None
    tmpfs_mode: Annotated[
        int | None,
        Field(serialization_alias="Mode"),
    ] = None


class Ulimit(BaseModel):
    name: Annotated[
        str,
        Field(serialization_alias="Name"),
    ]
    soft: Annotated[
        int | None,
        Field(serialization_alias="Soft"),
    ] = None
    hard: Annotated[
        int | None,
        Field(serialization_alias="Hard"),
    ] = None


class NetworkingConfig(BaseModel):
    endpoints_config: Annotated[
        dict[str, EndpointConfig] | None, Field(serialization_alias="EndpointsConfig")
    ] = None


class EndpointConfig(BaseModel):
    aliases: Annotated[list[str] | None, Field(serialization_alias="Aliases")] = None
    links: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="Links"),
        PlainSerializer(
            lambda value: (
                [f"{k}:{v}" for k, v in value.items()] if value is not None else None
            ),
            return_type=list[str] | None,
        ),
    ] = None
    ipam_config: Annotated[
        IPAMConfig | None, Field(serialization_alias="IPAMConfig")
    ] = None
    driver_opt: Annotated[
        dict[str, str] | None, Field(serialization_alias="DriverOpts")
    ] = None


class IPAMConfig(BaseModel):
    ipv4_address: Annotated[str | None, Field(serialization_alias="IPv4Address")] = None
    ipv6_address: Annotated[str | None, Field(serialization_alias="IPv6Address")] = None
    link_local_ips: Annotated[
        list[str] | None, Field(serialization_alias="LinkLocalIPs")
    ] = None


class Healthcheck(BaseModel):
    test: Annotated[list[str], Field(serialization_alias="Test")]
    interval: Annotated[int, Field(serialization_alias="Interval")]
    timeout: Annotated[int, Field(serialization_alias="Timeout")]
    retries: Annotated[int, Field(serialization_alias="Retries")]
    start_period: Annotated[int, Field(serialization_alias="StartPeriod")]


# Docker reports "not yet" as the zero time instead of omitting the field.
_ZERO_TIME: str = "0001-01-01T00:00:00Z"


def _none_if_zero_time(value: str | None) -> str | None:
    return None if value == _ZERO_TIME else value


def _name(names: list[str]) -> str:
    if not names:
        raise ValueError("container has no names")
    return names[0].removeprefix("/")


def _strip_slash(value: str) -> str:
    return value.removeprefix("/")


def _list_or_empty(value: list[Any] | None) -> list[Any]:
    return value if value is not None else []


def _dict_or_empty(value: dict[str, Any] | None) -> dict[str, Any]:
    return value if value is not None else {}


def _environment(value: list[str]) -> dict[str, str]:
    return {
        key: item for key, _, item in (entry.partition("=") for entry in value) if key
    }


class ContainerNetwork(BaseModel):
    network_id: str = Field(validation_alias="NetworkID", default="")
    ip_address: str = Field(validation_alias="IPAddress", default="")
    gateway: str = Field(validation_alias="Gateway", default="")


class ContainerPort(BaseModel):
    ip: str | None = Field(validation_alias="IP", default=None)
    private_port: int = Field(validation_alias="PrivatePort")
    public_port: int | None = Field(validation_alias="PublicPort", default=None)
    type: str = Field(validation_alias="Type", default="")


class ContainerStateResponse(BaseModel):
    status: str = Field(validation_alias="Status")
    running: bool = Field(validation_alias="Running")
    exit_code: int = Field(validation_alias="ExitCode", default=0)
    started_at: Annotated[
        str | None,
        BeforeValidator(_none_if_zero_time),
        Field(validation_alias="StartedAt"),
    ] = None
    finished_at: Annotated[
        str | None,
        BeforeValidator(_none_if_zero_time),
        Field(validation_alias="FinishedAt"),
    ] = None


class ContainerSummaryResponse(BaseModel):
    """Entry of `GET /containers/json`; names/networks of every network are returned."""

    id: str = Field(validation_alias="Id")
    name: Annotated[str, BeforeValidator(_name), Field(validation_alias="Names")]
    image: str = Field(validation_alias="Image")
    created: int = Field(validation_alias="Created")
    state: str = Field(validation_alias="State")
    status: str = Field(validation_alias="Status")
    labels: dict[str, str] | None = Field(validation_alias="Labels", default=None)
    ports: Annotated[
        list[ContainerPort],
        BeforeValidator(_list_or_empty),
        Field(validation_alias="Ports"),
    ] = []
    networks: Annotated[
        dict[str, ContainerNetwork],
        BeforeValidator(_dict_or_empty),
        Field(validation_alias=AliasPath("NetworkSettings", "Networks")),
    ] = {}


class ContainerDetailResponse(BaseModel):
    """`GET /containers/{id}/json`: lifecycle state, config and attached networks."""

    id: str = Field(validation_alias="Id")
    name: Annotated[str, BeforeValidator(_strip_slash), Field(validation_alias="Name")]
    image: str = Field(validation_alias="Image")
    created: str = Field(validation_alias="Created")
    state: ContainerStateResponse = Field(validation_alias="State")
    environment: Annotated[
        dict[str, str],
        BeforeValidator(_environment),
        Field(validation_alias=AliasPath("Config", "Env")),
    ] = {}
    labels: Annotated[
        dict[str, str],
        BeforeValidator(_dict_or_empty),
        Field(validation_alias=AliasPath("Config", "Labels")),
    ] = {}
    networks: Annotated[
        dict[str, ContainerNetwork],
        BeforeValidator(_dict_or_empty),
        Field(validation_alias=AliasPath("NetworkSettings", "Networks")),
    ] = {}
