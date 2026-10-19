from pydantic import BaseModel, Field


class DockerVersionResponse(BaseModel):
    version: str = Field(validation_alias="Version")
    api_version: str = Field(validation_alias="ApiVersion")
    min_api_version: str = Field(validation_alias="MinAPIVersion")
