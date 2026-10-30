# Single-salon PostgreSQL backup and restore

This is a provider-independent procedure, **not** evidence that production
backups exist. Do not run it against `yabs_salon_dev` or `yabs_salon_test`.
The approved objectives are daily backup after Manila closing, 14 days of
recoverable history, quarterly isolated restore drills, and 24-hour RPO/RTO.
RPO and RTO remain unproven until measured in a successful drill.

## Backup operation

1. Assign a protected, least-privilege backup identity and a separate restore
   verification role with SELECT only. Never use the application's local `.env`
   as backup configuration. Confirm the *connected* database identity and
   current Alembic revision before backup; record these in a protected manifest.
2. After each Asia/Manila closing, produce one complete, consistent database
   backup. Keep a continuous PostgreSQL WAL archive (or verified managed PITR)
   covering the same 14-day recovery window. The archive must include every
   necessary base backup and WAL segment; a daily logical dump alone cannot
   recover commits made after it. Keep an additional custom-format `pg_dump`
   only if useful for portability; it is not the sole recovery mechanism.
3. Encrypt before or during transfer to access-controlled storage outside the
   primary database host/failure domain. Protect keys separately, restrict
   deletion, verify upload completion and integrity, and retain at least 14
   complete recoverable days. Never expire the last known usable recovery set.
4. Alert the named operator on failed/missed backup, incomplete upload,
   encryption/key failure, WAL archive failure or lag, and when the latest
   *usable* restore point approaches 24 hours old. Verify alert delivery,
   escalation, available storage and restore-point age daily. Record only
   non-sensitive status/metadata in monitoring; backups contain credentials,
   payment references, and financial records.

## Quarterly isolated restore drill

1. Choose a fresh, empty, access-restricted database named
   `yabs_salon_restore_<unique_marker>` on an isolated non-production target.
   Do not connect the frontend/API, real users, or payment workflows. Verify
   source backup provenance and destination host/name *before* any restore.
2. Restore the full backup plus contiguous WAL to a declared recovery time.
   Confirm backup and WAL timestamps, missing segments, and actual connected
   database identity. Never point destructive restore flags at an existing
   development or production database. Provider-specific commands require a
   separate approved procedure.
3. Use a SELECT-only role and protected `RESTORE_DB_HOST`, `RESTORE_DB_PORT`,
   `RESTORE_DB_NAME`, `RESTORE_DB_USER`, and `RESTORE_DB_PASSWORD` settings.
   Run `deploy/backup/verify_restore.py` with exact `--expected-db`,
   `--expected-host`, and `--expected-user`. It refuses database names outside
   the isolated restore prefix, opens a read-only repeatable-read transaction,
   and emits only counts/check outcomes. It does not run Alembic or modify data.
   This checker requires revision `20261027_01`; a pre-cutover backup at
   `20261020_01` needs a separate schema-appropriate restore check before the
   migration. Never treat a failed revision check as permission to migrate the
   restored copy silently.
4. Compare the recovered transaction, attempt, idempotency, and audit boundary
   with an independently retained recovery manifest and paper/payment evidence.
   Review Reserved/Committed/Cancelled attempts, Direct and Manual references,
   voids, and report totals. The utility checks *internal* consistency only;
   it cannot detect a whole missing post-backup transaction or fence without
   independent evidence. Restrict and securely retire the restored copy after
   the drill according to the approved data-retention procedure.
   If audit rows have been archived separately, verify their corresponding
   archive before accepting the drill; the checker deliberately flags missing
   Manual-entry, void and cancellation audit events.
5. Record incident/drill start, latest recovered commit time, verified backup
   and WAL coverage, final safe sales-reopening time, failures and corrective
   actions. RPO is incident time minus latest recoverable commit. RTO is from
   incident detection to safe reopening, including verification/reconciliation.

## Permanent fence and reopening rule

`sale_attempts` contains permanent Cancelled UUID, Direct reference and Manual
paper-reference fences. Never delete, reactivate or silently replace these.
After a restore, keep electronic sales **paused** if any WAL gap or missing
attempt/transaction/audit evidence could have removed a fence or committed
sale. A 24-hour RPO target permits some data loss but does not prove that
reusing a lost key or reference is safe. Use the approved paper-log fallback and
Owner investigation; do not issue replacement UUIDs or downgrade to legacy
writers. Reopen only after the recovery boundary and every relevant attempt
are reconciled from reliable independent evidence, or a separately approved
mechanism supplies a stronger guarantee. If that cannot be proven, remain
paused and escalate to the Product Owner.

## Provider decision still required

Select the hosting/PITR implementation, protected off-site storage, encryption
key custody, alert recipient/escalation, and a measured restore procedure.
Provider-independent checks here do not schedule backups or verify WAL delivery.
