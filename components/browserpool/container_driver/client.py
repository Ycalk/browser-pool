from typing import NewType

from httpx import AsyncClient

DockerClient = NewType("DockerClient", AsyncClient)
