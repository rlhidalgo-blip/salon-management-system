from sqlalchemy import Boolean, CheckConstraint, Integer, Numeric, Text, UniqueConstraint, inspect
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.db.model_registry import get_model_metadata
from app.modules.catalog.models import Product, Service
from app.modules.commissions.models import CommissionRule
from app.modules.staff.models import Staff
from app.modules.users.models import User


EXPECTED_COLUMNS = {
    "users": {"id", "username", "password_hash", "role", "active"},
    "staff": {"id", "name", "role", "active"},
    "commission_rules": {"id", "name", "type", "value", "active"},
    "services": {"id", "name", "current_price", "allows_variable_price", "commission_rule_id", "active"},
    "products": {"id", "name", "current_price", "commission_rule_id", "active"},
}


def test_columns_use_approved_types_and_required_fields() -> None:
    metadata = get_model_metadata()

    assert set(EXPECTED_COLUMNS).issubset(metadata.tables)
    for table_name, expected in EXPECTED_COLUMNS.items():
        table = metadata.tables[table_name]
        assert set(table.columns.keys()) == expected
        assert all(not column.nullable for column in table.columns)
        assert isinstance(table.c.id.type, Integer)
        assert table.c.id.primary_key
        assert table.c.id.identity is not None

    for table_name, names in {
        "users": ("username", "password_hash", "role"),
        "staff": ("name", "role"),
        "commission_rules": ("name", "type"),
        "services": ("name",),
        "products": ("name",),
    }.items():
        assert all(isinstance(metadata.tables[table_name].c[name].type, Text) for name in names)

    for table_name, names in {
        "users": ("active",),
        "staff": ("active",),
        "commission_rules": ("active",),
        "services": ("allows_variable_price", "active"),
        "products": ("active",),
    }.items():
        assert all(isinstance(metadata.tables[table_name].c[name].type, Boolean) for name in names)

    for table_name, name in {
        "commission_rules": "value",
        "services": "current_price",
        "products": "current_price",
    }.items():
        column_type = metadata.tables[table_name].c[name].type
        assert isinstance(column_type, Numeric)
        assert (column_type.precision, column_type.scale, column_type.asdecimal) == (12, 2, True)


def test_defaults_and_postgresql_ddl_are_available_without_a_database() -> None:
    metadata = get_model_metadata()

    for table_name in EXPECTED_COLUMNS:
        table = metadata.tables[table_name]
        assert str(table.c.active.server_default.arg) == "true"
        assert "CREATE TABLE" in str(CreateTable(table).compile(dialect=postgresql.dialect()))
    assert str(metadata.tables["services"].c.allows_variable_price.server_default.arg) == "false"


def test_commission_rule_relationships_and_restrictive_foreign_keys() -> None:
    metadata = get_model_metadata()

    for model, collection_name in ((Service, "services"), (Product, "products")):
        relationship = inspect(model).relationships["commission_rule"]
        collection = inspect(CommissionRule).relationships[collection_name]
        foreign_key = next(iter(metadata.tables[model.__tablename__].c.commission_rule_id.foreign_keys))

        assert relationship.mapper.class_ is CommissionRule
        assert relationship.back_populates == collection_name
        assert relationship.uselist is False
        assert collection.mapper.class_ is model
        assert collection.back_populates == "commission_rule"
        assert collection.uselist is True
        assert foreign_key.target_fullname == "commission_rules.id"
        assert foreign_key.ondelete == "RESTRICT"

    assert inspect(User).relationships.keys() == []
    assert inspect(Staff).relationships.keys() == []


def test_uniqueness_and_approved_check_constraints() -> None:
    metadata = get_model_metadata()
    assert any(
        isinstance(constraint, UniqueConstraint) and set(constraint.columns.keys()) == {"username"}
        for constraint in metadata.tables["users"].constraints
    )

    expected_checks = {
        "users": {"ck_users_role": "role IN ('Owner', 'Cashier')"},
        "staff": {"ck_staff_role": "role IN ('Barber', 'Stylist')"},
        "commission_rules": {
            "ck_commission_rules_type": "type IN ('Percentage', 'Fixed')",
            "ck_commission_rules_value": "value > 0 AND (type <> 'Percentage' OR value <= 100)",
        },
        "services": {"ck_services_current_price": "current_price > 0"},
        "products": {"ck_products_current_price": "current_price > 0"},
    }
    for table_name, checks in expected_checks.items():
        actual = {
            constraint.name: str(constraint.sqltext)
            for constraint in metadata.tables[table_name].constraints
            if isinstance(constraint, CheckConstraint)
        }
        assert actual == checks
