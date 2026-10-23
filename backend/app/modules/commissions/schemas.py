"""Public commission-rule shapes; rule terms are immutable after creation."""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator


RuleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RuleValue = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
RuleType = Literal["Percentage", "Fixed"]


class CommissionRuleCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RuleName
    type: RuleType
    value: RuleValue

    @model_validator(mode="after")
    def check_percentage_limit(self):
        if self.type == "Percentage" and self.value > Decimal("100"):
            raise ValueError("Percentage cannot exceed 100")
        return self


class CommissionRuleStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: StrictBool


class CommissionRulePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: RuleType
    value: Decimal
    active: bool
