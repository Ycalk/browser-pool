import json
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer


class LabelFilters(BaseModel):
    """Docker filter document shared by the list and prune endpoints."""

    labels: Annotated[
        dict[str, str] | None,
        Field(serialization_alias="label"),
        PlainSerializer(
            lambda value: (
                [f"{key}={item}" for key, item in value.items()]
                if value is not None
                else None
            ),
            return_type=list[str] | None,
        ),
    ] = None

    def as_query(self) -> str:
        return json.dumps(self.model_dump(by_alias=True, exclude_none=True))
