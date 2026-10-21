"""Request and public response shapes for Owner-only Staff administration."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints


StaffName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
StaffRole = Literal["Barber", "Stylist"]


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: StaffName
    role: StaffRole


class StaffStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: StrictBool


class StaffPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    role: StaffRole
    active: bool
