"""Opt-in, rollback-only checks of PostgreSQL's approved v1.1 constraints."""

import os
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import Connection, create_engine, func, insert, select, text
from sqlalchemy.exc import IntegrityError

from app.core.config import get_database_url
from app.db.model_registry import get_model_metadata


TABLES = get_model_metadata().tables
TEST_DATABASE = "yabs_salon_test"
ALLOWED_SCHEMAS = (("20261020_01", False), ("20261027_01", True))


class DatabaseCase:
    def __init__(self, connection: Connection, marker: str) -> None:
        self.connection = connection
        self.marker = marker
        self.created_ids: dict[str, set[int]] = defaultdict(set)

    def add(self, table_name: str, **values: object) -> int:
        table = TABLES[table_name]
        row_id = self.connection.execute(insert(table).values(**values).returning(table.c.id)).scalar_one()
        self.created_ids[table_name].add(row_id)
        return row_id

    def rejects(self, table_name: str, constraint_name: str, sqlstate: str, **values: object) -> None:
        with pytest.raises(IntegrityError) as caught:
            with self.connection.begin_nested():
                self.connection.execute(insert(TABLES[table_name]).values(**values))
        assert caught.value.orig.sqlstate == sqlstate
        assert caught.value.orig.diag.constraint_name == constraint_name


@pytest.fixture
def db() -> Iterator[DatabaseCase]:
    # No database URL evaluation or connection during an ordinary pytest run.
    if os.getenv("RUN_DB_INTEGRATION_TESTS") != "1":
        pytest.skip("Set RUN_DB_INTEGRATION_TESTS=1 to run PostgreSQL integration tests")

    url = get_database_url()
    if url.database != TEST_DATABASE:
        pytest.fail("Configured database is not yabs_salon_test; no test writes attempted")

    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            actual_database = connection.scalar(text("SELECT current_database()"))
            if actual_database != TEST_DATABASE:
                pytest.fail("Connected database is not yabs_salon_test; no test writes attempted")
            version_table = connection.scalar(text("SELECT to_regclass('public.alembic_version')"))
            if version_table is None:
                pytest.fail("Alembic version table is absent; no test writes attempted")
            revision = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            has_attempts = connection.scalar(text("SELECT to_regclass('public.sale_attempts')")) is not None
            if (revision, has_attempts) not in ALLOWED_SCHEMAS:
                pytest.fail("Expected Alembic revision is not applied; no test writes attempted")

            # The guard queries start an implicit transaction. End it, then own
            # one explicit outer transaction for every synthetic test write.
            connection.rollback()
            outer = connection.begin()
            case = DatabaseCase(connection, f"integration-{uuid4().hex}")
            try:
                yield case
            finally:
                if not outer.is_active:
                    pytest.fail("Outer test transaction ended unexpectedly; rollback safety lost")
                outer.rollback()

        # Check on a fresh connection that every successful synthetic insert
        # disappeared when the outer transaction rolled back.
        with engine.connect() as verifier:
            if verifier.scalar(text("SELECT current_database()")) != TEST_DATABASE:
                pytest.fail("Rollback verification connected to the wrong database")
            for table_name, ids in case.created_ids.items():
                table = TABLES[table_name]
                remaining = verifier.scalar(select(func.count()).select_from(table).where(table.c.id.in_(ids)))
                assert remaining == 0, f"Synthetic {table_name} records remained after rollback"
    finally:
        engine.dispose()


def user(db: DatabaseCase, role: str = "Owner") -> int:
    return db.add(
        "users", username=f"{db.marker}-{role.lower()}",
        password_hash="synthetic-hash-not-a-real-password", role=role,
    )


def commission_rule(db: DatabaseCase, rule_type: str = "Percentage", value: str = "25.00") -> int:
    return db.add(
        "commission_rules", name=f"{db.marker}-rule", type=rule_type, value=Decimal(value),
    )


def transaction(db: DatabaseCase, recorded_by_user_id: int, **changes: object) -> int:
    values = {
        "business_date": date(2026, 10, 20),
        "recorded_by_user_id": recorded_by_user_id,
        "entry_source": "Direct",
        "payment_method": "Cash",
    }
    values.update(changes)
    return db.add("transactions", **values)


def service_item(db: DatabaseCase, transaction_id: int, service_id: int, staff_id: int, **changes: object) -> dict:
    values = {
        "transaction_id": transaction_id,
        "service_id": service_id,
        "staff_id": staff_id,
        "item_name_snapshot": f"{db.marker}-service-item",
        "selling_price": Decimal("100.00"),
        "commission_type_snapshot": "Percentage",
        "commission_value_snapshot": Decimal("25.00"),
        "staff_commission": Decimal("25.00"),
        "business_share": Decimal("75.00"),
    }
    values.update(changes)
    return values


def test_user_roles(db: DatabaseCase) -> None:
    user(db, "Owner")
    user(db, "Cashier")
    db.rejects(
        "users", "ck_users_role", "23514",
        username=f"{db.marker}-invalid", password_hash="synthetic-hash", role="Manager",
    )


def test_positive_service_and_product_prices(db: DatabaseCase) -> None:
    rule_id = commission_rule(db)
    db.add("services", name=f"{db.marker}-service", current_price=Decimal("100.00"), commission_rule_id=rule_id)
    db.add("products", name=f"{db.marker}-product", current_price=Decimal("50.00"), commission_rule_id=rule_id)
    for table_name in ("services", "products"):
        for price in ("0.00", "-1.00"):
            db.rejects(
                table_name, f"ck_{table_name}_current_price", "23514",
                name=f"{db.marker}-{table_name}-{price}", current_price=Decimal(price), commission_rule_id=rule_id,
            )


def test_commission_types_and_values(db: DatabaseCase) -> None:
    commission_rule(db, "Percentage", "100.00")
    commission_rule(db, "Fixed", "101.00")
    db.rejects(
        "commission_rules", "ck_commission_rules_type", "23514",
        name=f"{db.marker}-invalid-type", type="Other", value=Decimal("10.00"),
    )
    for rule_type, value in (("Percentage", "0.00"), ("Percentage", "100.01"), ("Fixed", "0.00")):
        db.rejects(
            "commission_rules", "ck_commission_rules_value", "23514",
            name=f"{db.marker}-{rule_type}-{value}", type=rule_type, value=Decimal(value),
        )


def test_required_foreign_keys(db: DatabaseCase) -> None:
    owner_id = user(db)
    rule_id = commission_rule(db)
    db.rejects(
        "services", "services_commission_rule_id_fkey", "23503",
        name=f"{db.marker}-missing-rule", current_price=Decimal("10.00"), commission_rule_id=-1,
    )
    db.rejects(
        "products", "products_commission_rule_id_fkey", "23503",
        name=f"{db.marker}-missing-rule", current_price=Decimal("10.00"), commission_rule_id=-1,
    )
    db.rejects(
        "transactions", "transactions_recorded_by_user_id_fkey", "23503",
        business_date=date(2026, 10, 20), recorded_by_user_id=-1,
        entry_source="Direct", payment_method="Cash",
    )
    service_id = db.add(
        "services", name=f"{db.marker}-service", current_price=Decimal("100.00"), commission_rule_id=rule_id,
    )
    staff_id = db.add("staff", name=f"{db.marker}-staff", role="Barber")
    transaction_id = transaction(db, owner_id)
    db.rejects(
        "transaction_items", "transaction_items_transaction_id_fkey", "23503",
        **service_item(db, -1, service_id, staff_id),
    )
    db.rejects(
        "transaction_items", "transaction_items_service_id_fkey", "23503",
        **service_item(db, transaction_id, -1, staff_id),
    )


def test_cash_and_gcash_references(db: DatabaseCase) -> None:
    owner_id = user(db)
    transaction(db, owner_id, payment_method="Cash")
    transaction(db, owner_id, payment_method="GCash", gcash_reference=f"{db.marker}-gcash")
    for payment_method, reference in (("Cash", "unexpected"), ("GCash", None), ("GCash", "   ")):
        db.rejects(
            "transactions", "ck_transactions_gcash_reference", "23514",
            business_date=date(2026, 10, 20), recorded_by_user_id=owner_id,
            entry_source="Direct", payment_method=payment_method, gcash_reference=reference,
        )


def test_financial_snapshots_and_item_assignment(db: DatabaseCase) -> None:
    owner_id = user(db)
    rule_id = commission_rule(db)
    service_id = db.add(
        "services", name=f"{db.marker}-service", current_price=Decimal("100.00"), commission_rule_id=rule_id,
    )
    product_id = db.add(
        "products", name=f"{db.marker}-product", current_price=Decimal("100.00"), commission_rule_id=rule_id,
    )
    staff_id = db.add("staff", name=f"{db.marker}-staff", role="Barber")
    transaction_id = transaction(db, owner_id)
    valid = service_item(db, transaction_id, service_id, staff_id)
    db.add("transaction_items", **valid)
    db.add(
        "transaction_items", transaction_id=transaction_id, product_id=product_id,
        item_name_snapshot=f"{db.marker}-product-item", selling_price=Decimal("100.00"),
        staff_commission=Decimal("0.00"), business_share=Decimal("100.00"),
    )
    db.rejects(
        "transaction_items", "ck_transaction_items_financial_total", "23514",
        **{**valid, "business_share": Decimal("74.99")},
    )
    db.rejects(
        "transaction_items", "ck_transaction_items_service_staff", "23514",
        **{**valid, "staff_id": None},
    )
    db.rejects(
        "transaction_items", "ck_transaction_items_one_item_type", "23514",
        **{**valid, "product_id": product_id},
    )
    db.rejects(
        "transaction_items", "ck_transaction_items_commission_snapshot", "23514",
        **{**valid, "commission_value_snapshot": Decimal("0.00")},
    )


def test_manual_reference_uniqueness(db: DatabaseCase) -> None:
    owner_id = user(db)
    reference = f"{db.marker}-manual-ref"
    transaction(db, owner_id, entry_source="Manual", manual_reference=reference)
    db.rejects(
        "transactions", "uq_transactions_manual_reference", "23505",
        business_date=date(2026, 10, 20), recorded_by_user_id=owner_id,
        entry_source="Manual", manual_reference=reference, payment_method="Cash",
    )
    # The partial unique index permits multiple NULLs for direct sales.
    transaction(db, owner_id)
    transaction(db, owner_id)


def test_idempotency_key_is_unique_per_user(db: DatabaseCase) -> None:
    first_user_id = user(db, "Owner")
    second_user_id = user(db, "Cashier")
    key = f"{db.marker}-key"
    values = {
        "idempotency_key": key,
        "request_hash": "a" * 64,
        "created_at": datetime(2026, 10, 20, tzinfo=timezone.utc),
    }
    db.add("sale_idempotency", user_id=first_user_id, **values)
    db.rejects(
        "sale_idempotency", "uq_sale_idempotency_user_key", "23505",
        user_id=first_user_id, **values,
    )
    db.add("sale_idempotency", user_id=second_user_id, **values)
