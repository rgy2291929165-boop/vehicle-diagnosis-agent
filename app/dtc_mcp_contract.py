"""DTC MCP 服务与适配器共享的数据契约。"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

NonEmptyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, strict=True),
]


class DtcQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: NonEmptyText
    dtc_code: NonEmptyText


class DtcResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    vehicle_id: NonEmptyText
    dtc_code: NonEmptyText
    description: NonEmptyText
    severity: Literal["low", "medium", "high"]
    recommended_check: NonEmptyText
    data_source: Literal["mock"]
