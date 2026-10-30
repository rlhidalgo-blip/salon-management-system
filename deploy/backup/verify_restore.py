"""Read-only checks for an isolated, already-restored Yab's PostgreSQL database.

No dump, restore, migration, or application write is performed here. Run with a
dedicated SELECT-only database role. Output contains counts and check names only.
"""

import argparse
import os
import re
import sys
from dataclasses import dataclass


REVISION = "20261027_01"
RESTORE_NAME = re.compile(r"^yabs_salon_restore_[a-z0-9_]+$")
REQUIRED_TABLES = frozenset({
    "users", "staff", "commission_rules", "services", "products", "transactions",
    "transaction_items", "sale_idempotency", "sale_attempts", "audit_events",
    "auth_sessions", "alembic_version",
})
REQUIRED_CONSTRAINTS = frozenset({
    "uq_sale_attempts_user_key", "uq_sale_attempts_direct_reference",
    "uq_sale_attempts_manual_reference", "uq_sale_attempts_transaction_id",
    "ck_sale_attempts_state", "ck_sale_attempts_state_metadata",
    "ck_sale_attempts_reference_source", "ck_transaction_items_financial_total",
})
REQUIRED_INDEXES = frozenset({
    "uq_sale_attempts_one_reserved_user", "uq_transactions_manual_reference",
    "uq_sale_idempotency_user_key",
})


class VerificationError(Exception):
    """A safe, non-sensitive failure code for operators and tests."""


@dataclass(frozen=True)
class Target:
    host: str
    port: int
    database: str
    user: str
    password: str


def target_from_environment(*, expected_db: str, expected_host: str, expected_user: str) -> Target:
    # Validate without connecting. RESTORE_DB_* avoids silently using the app DB.
    if not RESTORE_NAME.fullmatch(expected_db or "") or not expected_host or not expected_user:
        raise VerificationError("unsafe_target")
    settings = {name: os.getenv("RESTORE_DB_" + name, "") for name in
                ("HOST", "PORT", "NAME", "USER", "PASSWORD")}
    if (not all(settings.values()) or settings["NAME"] != expected_db
            or settings["HOST"] != expected_host or settings["USER"] != expected_user):
        raise VerificationError("target_mismatch")
    try:
        port = int(settings["PORT"])
    except ValueError:
        raise VerificationError("invalid_port") from None
    if not 1 <= port <= 65535:
        raise VerificationError("invalid_port")
    return Target(settings["HOST"], port, settings["NAME"], settings["USER"], settings["PASSWORD"])


def _one(connection, sql: str):
    row = connection.execute(sql).fetchone()
    if row is None:
        raise VerificationError("missing_result")
    return row[0]


def _require_zero(connection, code: str, sql: str) -> None:
    if _one(connection, sql) != 0:
        raise VerificationError(code)


CHECKS = (
    ("attempt_state_invalid", """SELECT count(*) FROM public.sale_attempts a WHERE
        a.state NOT IN ('Reserved','Committed','Cancelled') OR a.source NOT IN ('Direct','Manual')
        OR a.request_hash !~ '^[0-9a-f]{64}$'
        OR (a.source = 'Direct' AND (a.manual_reference IS NOT NULL OR a.direct_reference IS DISTINCT FROM
            'DS-' || lpad(a.id::text, greatest(12,length(a.id::text)), '0')))
        OR (a.source = 'Manual' AND (a.direct_reference IS NOT NULL OR
            a.manual_reference IS NULL OR a.manual_reference !~ '^PAPER-[0-9]{8}-[0-9]{3}$'))
        OR (a.state = 'Reserved' AND (a.transaction_id IS NOT NULL OR a.committed_at IS NOT NULL
            OR a.cancelled_at IS NOT NULL OR a.cancelled_by_user_id IS NOT NULL OR a.cancellation_reason IS NOT NULL))
        OR (a.state = 'Committed' AND (a.transaction_id IS NULL OR a.committed_at IS NULL
            OR a.cancelled_at IS NOT NULL OR a.cancelled_by_user_id IS NOT NULL OR a.cancellation_reason IS NOT NULL))
        OR (a.state = 'Cancelled' AND (a.transaction_id IS NOT NULL OR a.committed_at IS NOT NULL
            OR a.cancelled_at IS NULL OR a.cancelled_by_user_id IS NULL
            OR nullif(btrim(a.cancellation_reason), '') IS NULL OR length(a.cancellation_reason)>500))"""),
    ("attempt_key_duplicate", """SELECT count(*) FROM (SELECT 1 FROM public.sale_attempts
        GROUP BY user_id,idempotency_key HAVING count(*) > 1) duplicates"""),
    ("open_attempt_duplicate", """SELECT count(*) FROM (SELECT 1 FROM public.sale_attempts
        WHERE state='Reserved' GROUP BY user_id HAVING count(*) > 1) duplicates"""),
    ("direct_reference_duplicate", """SELECT count(*) FROM (SELECT 1 FROM public.sale_attempts
        WHERE direct_reference IS NOT NULL GROUP BY direct_reference HAVING count(*) > 1) duplicates"""),
    ("paper_reference_duplicate", """SELECT count(*) FROM (SELECT 1 FROM public.sale_attempts
        WHERE manual_reference IS NOT NULL GROUP BY manual_reference HAVING count(*) > 1) duplicates"""),
    ("transaction_paper_duplicate", """SELECT count(*) FROM (SELECT 1 FROM public.transactions
        WHERE manual_reference IS NOT NULL GROUP BY manual_reference HAVING count(*) > 1) duplicates"""),
    ("paper_reference_conflict", """SELECT count(*) FROM public.sale_attempts a
        JOIN public.transactions t ON t.manual_reference=a.manual_reference
        WHERE a.manual_reference IS NOT NULL AND (a.state <> 'Committed' OR a.transaction_id <> t.id)"""),
    ("claim_invalid", """SELECT count(*) FROM public.sale_idempotency i
        LEFT JOIN public.transactions t ON t.id=i.transaction_id
        WHERE t.id IS NULL OR t.recorded_by_user_id <> i.user_id OR i.request_hash !~ '^[0-9a-f]{64}$'"""),
    ("claim_duplicate", """SELECT count(*) FROM (SELECT 1 FROM public.sale_idempotency
        GROUP BY user_id,idempotency_key HAVING count(*) > 1) duplicates"""),
    ("transaction_claim_missing", """SELECT count(*) FROM public.transactions t WHERE NOT EXISTS
        (SELECT 1 FROM public.sale_idempotency i WHERE i.transaction_id=t.id
            AND i.user_id=t.recorded_by_user_id)"""),
    ("committed_attempt_claim_missing", """SELECT count(*) FROM public.sale_attempts a
        LEFT JOIN public.sale_idempotency i ON i.user_id=a.user_id
            AND i.idempotency_key=a.idempotency_key::text
        LEFT JOIN public.transactions t ON t.id=a.transaction_id
        WHERE a.state='Committed' AND (i.id IS NULL OR i.transaction_id IS DISTINCT FROM a.transaction_id
            OR i.request_hash IS DISTINCT FROM a.request_hash OR t.id IS NULL
            OR t.entry_source IS DISTINCT FROM a.source OR t.manual_reference IS DISTINCT FROM a.manual_reference
            OR t.recorded_by_user_id IS DISTINCT FROM a.user_id)"""),
    ("cancel_audit_missing", """SELECT count(*) FROM public.sale_attempts a
        WHERE a.state='Cancelled' AND NOT EXISTS (SELECT 1 FROM public.audit_events e
            WHERE e.event_type='SaleAttemptCancellation' AND e.outcome='Success'
            AND e.resource_type='sale_attempt' AND e.resource_id=a.id::text
            AND e.actor_user_id=a.cancelled_by_user_id)"""),
    ("manual_audit_missing", """SELECT count(*) FROM public.transactions t
        WHERE t.entry_source='Manual' AND NOT EXISTS (SELECT 1 FROM public.audit_events e
            WHERE e.event_type='ManualSaleCreated' AND e.outcome='Success'
            AND e.resource_type='transaction' AND e.resource_id=t.id::text
            AND e.actor_user_id=t.recorded_by_user_id)"""),
    ("void_audit_missing", """SELECT count(*) FROM public.transactions t
        WHERE t.status='Voided' AND NOT EXISTS (SELECT 1 FROM public.audit_events e
            WHERE e.event_type='TransactionVoid' AND e.outcome='Success'
            AND e.resource_type='transaction' AND e.resource_id=t.id::text
            AND e.actor_user_id=t.voided_by_user_id)"""),
    ("transaction_items_missing", """SELECT count(*) FROM public.transactions t WHERE NOT EXISTS
        (SELECT 1 FROM public.transaction_items i WHERE i.transaction_id=t.id)"""),
    ("item_snapshot_invalid", """SELECT count(*) FROM public.transaction_items i WHERE
        i.selling_price <= 0 OR i.staff_commission < 0 OR i.business_share < 0
        OR i.staff_commission + i.business_share <> i.selling_price"""),
    ("financial_reconciliation_failed", """SELECT CASE WHEN
        coalesce(sum(i.selling_price),0) = coalesce(sum(i.staff_commission),0)+coalesce(sum(i.business_share),0)
        AND coalesce(sum(i.selling_price),0) =
            coalesce(sum(i.selling_price) FILTER (WHERE t.payment_method='Cash'),0)+
            coalesce(sum(i.selling_price) FILTER (WHERE t.payment_method='GCash'),0)
        THEN 0 ELSE 1 END FROM public.transactions t JOIN public.transaction_items i
        ON i.transaction_id=t.id WHERE t.status='Completed'"""),
)


def verify_restore(connection, target: Target) -> dict[str, int]:
    """Use one read-only consistent snapshot; raise safe codes on mismatches."""
    connection.execute("BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    try:
        if (_one(connection, "SELECT current_database()") != target.database
                or _one(connection, "SELECT current_user") != target.user
                or _one(connection, "SELECT current_schema()") != "public"):
            raise VerificationError("connected_target_mismatch")
        tables = {row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()}
        if not REQUIRED_TABLES.issubset(tables):
            raise VerificationError("schema_missing")
        revisions = connection.execute("SELECT version_num FROM public.alembic_version").fetchall()
        if revisions != [(REVISION,)]:
            raise VerificationError("revision_mismatch")
        constraints = {row[0] for row in connection.execute(
            "SELECT conname FROM pg_constraint WHERE connamespace='public'::regnamespace").fetchall()}
        indexes = {row[0] for row in connection.execute(
            "SELECT indexrelid::regclass::text FROM pg_index WHERE indrelid IN "
            "('public.sale_attempts'::regclass,'public.transactions'::regclass,"
            "'public.sale_idempotency'::regclass) AND indisvalid AND indisready AND indisunique"
        ).fetchall()}
        if not REQUIRED_CONSTRAINTS.issubset(constraints) or not REQUIRED_INDEXES.issubset(
                {name.removeprefix("public.") for name in indexes}):
            raise VerificationError("constraints_missing")
        counts = dict(connection.execute(
            "SELECT state,count(*) FROM public.sale_attempts GROUP BY state").fetchall())
        if any(state not in ("Reserved", "Committed", "Cancelled") for state in counts):
            raise VerificationError("attempt_state_invalid")
        for code, sql in CHECKS:
            _require_zero(connection, code, sql)
        return {state: counts.get(state, 0) for state in ("Reserved", "Committed", "Cancelled")}
    finally:
        connection.execute("ROLLBACK")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check an isolated restored Yab's database; never writes")
    parser.add_argument("--expected-db", required=True)
    parser.add_argument("--expected-host", required=True)
    parser.add_argument("--expected-user", required=True)
    args = parser.parse_args(argv)
    try:
        target = target_from_environment(expected_db=args.expected_db,
                                         expected_host=args.expected_host,
                                         expected_user=args.expected_user)
        import psycopg
        with psycopg.connect(host=target.host, port=target.port, dbname=target.database,
                             user=target.user, password=target.password, connect_timeout=5,
                             autocommit=True, options="-c default_transaction_read_only=on "
                             "-c statement_timeout=15000 -c lock_timeout=3000") as connection:
            counts = verify_restore(connection, target)
    except VerificationError as exc:
        print(f"Restore verification FAILED: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # DB errors may contain a connection URL or SQL parameters. Never echo them.
        print("Restore verification FAILED: database_error", file=sys.stderr)
        return 1
    print("Restore verification PASSED; attempt counts: " +
          ", ".join(f"{state}={count}" for state, count in counts.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
