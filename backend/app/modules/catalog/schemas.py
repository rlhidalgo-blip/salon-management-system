"""Strict Owner catalog request and response shapes."""

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, model_validator


CatalogName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Price = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
RuleId = Annotated[int, Field(strict=True, gt=0)]


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CatalogName
    current_price: Price
    allows_variable_price: StrictBool = False
    commission_rule_id: RuleId


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CatalogName
    current_price: Price
    commission_rule_id: RuleId


class _CatalogUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: CatalogName = None
    current_price: Price = None
    commission_rule_id: RuleId = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field")
        return self


class ServiceUpdate(_CatalogUpdate):
    allows_variable_price: StrictBool = None


class ProductUpdate(_CatalogUpdate):
    pass


class CatalogStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: StrictBool


class ServicePublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    current_price: Decimal
    allows_variable_price: bool
    commission_rule_id: int
    active: bool


class ProductPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    current_price: Decimal
    commission_rule_id: int
    active: bool
