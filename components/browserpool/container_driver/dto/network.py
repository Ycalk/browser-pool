from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, PlainSerializer

from .container import EndpointConfig


class NetworkOptions(BaseModel):
    """Bridge driver options.

    `enable_icc=False` drops traffic between every endpoint of the network,
    including the pool service talking to the browser, so slot networks keep
    the driver default and rely on one-browser-per-network isolation instead.
    """

    enable_icc: Annotated[
        bool | None,
        Field(serialization_alias="com.docker.network.bridge.enable_icc"),
        PlainSerializer(
            lambda value: None if value is None else str(value).lower(),
            return_type=str | None,
        ),
    ] = None


class NetworkIPAMConfig(BaseModel):
    subnet: Annotated[str | None, Field(serialization_alias="Subnet")] = None
    ip_range: Annotated[str | None, Field(serialization_alias="IPRange")] = None
    gateway: Annotated[str | None, Field(serialization_alias="Gateway")] = None


class NetworkIPAM(BaseModel):
    driver: Annotated[str | None, Field(serialization_alias="Driver")] = None
    config: Annotated[
        list[NetworkIPAMConfig] | None, Field(serialization_alias="Config")
    ] = None
    options: Annotated[dict[str, str] | None, Field(serialization_alias="Options")] = (
        None
    )


class NetworkConfig(BaseModel):
    name: Annotated[str, Field(serialization_alias="Name")]
    driver: Annotated[str | None, Field(serialization_alias="Driver")] = None
    internal: Annotated[bool | None, Field(serialization_alias="Internal")] = None
    enable_ipv4: Annotated[bool | None, Field(serialization_alias="EnableIPv4")] = None
    enable_ipv6: Annotated[bool | None, Field(serialization_alias="EnableIPv6")] = None
    ipam: Annotated[NetworkIPAM | None, Field(serialization_alias="IPAM")] = None
    options: Annotated[NetworkOptions | None, Field(serialization_alias="Options")] = (
        None
    )
    labels: Annotated[dict[str, str] | None, Field(serialization_alias="Labels")] = None


class NetworkConnectConfig(BaseModel):
    """`POST /networks/{id}/connect` body."""

    container: Annotated[str, Field(serialization_alias="Container")]
    endpoint_config: Annotated[
        EndpointConfig | None, Field(serialization_alias="EndpointConfig")
    ] = None


class NetworkSubnet(BaseModel):
    subnet: str = Field(validation_alias="Subnet")
    gateway: str | None = Field(validation_alias="Gateway", default=None)


class NetworkIPAMState(BaseModel):
    driver: str = Field(validation_alias="Driver")
    # Docker answers `Config: null` for networks without allocated subnets.
    config: Annotated[
        list[NetworkSubnet],
        BeforeValidator(lambda value: [] if value is None else value),
        Field(validation_alias="Config"),
    ] = []


class NetworkResponse(BaseModel):
    id: str = Field(validation_alias="Id")
    name: str = Field(validation_alias="Name")
    driver: str = Field(validation_alias="Driver")
    internal: bool = Field(validation_alias="Internal")
    options: dict[str, str] | None = Field(validation_alias="Options", default=None)
    labels: dict[str, str] | None = Field(validation_alias="Labels", default=None)
    ipam: NetworkIPAMState | None = Field(validation_alias="IPAM", default=None)
