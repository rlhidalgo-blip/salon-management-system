# Operating Calendar and Weekday Sales Analytics Specification — Yab's Salon Management System

| Field | Value |
|---|---|
| Feature | V2 Feature 01 |
| Version | 1.0 |
| Status | Accepted planning baseline; implementation pending |
| Date | November 4, 2026 |

## Purpose and scope

Record the salon's operating status explicitly and show Owner-only sales by weekday, including average gross sales per verified operating day. Yab's normally operates Monday through Sunday but may close for holidays or other reasons. A zero-sales date does not establish that the salon was closed, and a sale does not by itself verify that the salon was open.

This specification covers one salon and the existing Asia/Manila calendar-day business date. It does not introduce shifts, branches, appointments, cached financial totals, or changes to financial snapshots. The Product Owner approved the product and technical rules below as the V2 planning baseline. The schema, routes, and UI described as V2 are proposed and are not implemented yet.

## Existing V1 behavior to preserve

- `transactions.business_date` is the Asia/Manila date used for reporting. Direct sales use trusted database time near insertion; Manual sales derive the date from an offset-aware occurrence timestamp.
- `transaction_items.selling_price`, `staff_commission`, and `business_share` preserve the values used for each completed sale. Voided transactions remain stored but do not contribute to active daily or monthly financial totals.
- The Daily report serves Owner and today's Cashier; the Monthly report is Owner-only. Their existing endpoints, schemas, arithmetic, and authorization remain unchanged.
- Sale creation has transaction-wide atomicity, exact-key idempotency, pending-sale recovery, and an optional, default-disabled `reserved_v1` reservation path. This feature must not activate that path or weaken either writer mode.
- Owner authorization is enforced by FastAPI dependencies. Authenticated writes require Origin and CSRF checks. Audit events already record actor, resource, outcome, time, and JSON metadata.

Relevant code: `backend/app/modules/transactions/{models,service,manual_service,idempotency_lock,attempt_service}.py`, `backend/app/modules/reports/{router,service,schemas}.py`, `backend/app/modules/auth/dependencies.py`, and `backend/app/modules/audit/models.py`.

## Operating status rules

Use one current status per Manila business date:

| Status | Meaning | Historical analytics treatment |
|---|---|---|
| `Open` | Owner verified that the salon operated | Verified operating day; include even when gross sales are zero |
| `Closed` | Owner verified closure and supplied a reason | Verified closure; exclude from the operating-day average |
| `Unknown` | Operating outcome has not been verified | Unverified; exclude from the average and count separately |
| `PlannedClosed` | Owner recorded an intended future closure with a reason | Unconfirmed; never count as verified Closed or Open |

No record also reads as Unknown. Keep an explicit Unknown record when the Owner corrects a prior verification back to Unknown, so its version and audit history remain traceable. No status is inferred from transaction presence or absence.

An Owner may create a future `PlannedClosed` date. A plan remains `PlannedClosed` when the date arrives or passes; there is no automatic promotion to verified Closed. On a past date, label it **Planned closure — outcome unconfirmed** and require an individual Owner correction to Open, Closed, or Unknown. Creating a new plan for today or an earlier date is invalid. Verified Open and Closed may be recorded for today or earlier, subject to the Closed conflict rule. Only dates before today qualify for bulk Open verification.

A new Direct or Manual Sale on verified `Closed` is rejected. A sale on `PlannedClosed` is allowed: the plan is not a verified closure, and checkout must remain possible when actual operations differ from the plan. The sale does not change calendar status automatically. The Owner calendar and analytics flag an unconfirmed past plan with sales for review. No calendar action silently edits or voids a transaction.

## Proposed persistence and audit

Add one `operating_days` table in an additive Alembic revision after `20261027_01`; do not backfill historical dates from sales:

| Column | Type and constraint |
|---|---|
| `business_date` | `DATE PRIMARY KEY` |
| `status` | `TEXT NOT NULL`, check for the four values above |
| `closure_reason` | `TEXT`; nonblank and at most 500 characters for Closed or PlannedClosed, null for Open or Unknown |
| `created_by_user_id`, `updated_by_user_id` | `INTEGER NOT NULL`, `users.id` foreign keys with `ON DELETE RESTRICT` |
| `created_at`, `updated_at` | `TIMESTAMPTZ NOT NULL`, trusted database time |
| `version` | `INTEGER NOT NULL`, check `version > 0` |

An absent row has response version 0. Creation starts at 1; every correction increments the version. Do not delete a row to revoke verification. The date primary key serves status lookup, and the existing transaction business-date index serves conflict and sales queries. Cross-table completed-sale checks and temporal transition rules belong in the service under a shared date lock; a row check constraint cannot express them.

Write one `OperatingDayChanged` audit event per changed date in the same transaction as the calendar row. Use the ISO date as the resource ID and include prior/new status, reason, version, and whether the change came from bulk verification. Audit records retain who made each correction and when. A history endpoint reads these events; the analytics query uses current statuses. A destructive downgrade that would erase recorded statuses should be refused.

## Proposed Owner-only API

All endpoints require `require_owner`, use the existing authentication and write protections, set `Cache-Control: no-store`, and return the existing request-ID error envelope. `from` and `through` are inclusive ISO dates. The backend validates dates and uses trusted database time converted to Asia/Manila for today.

| Endpoint | Request and response |
|---|---|
| `GET /api/v1/operating-days?from=YYYY-MM-DD&through=YYYY-MM-DD` | At most 90 dates. Return one entry per date: `business_date`, `status`, `closure_reason`, `version`, completed transaction count, gross sales, and an inconsistency flag. Missing rows return Unknown/version 0. Permit future plans in this view. |
| `PUT /api/v1/operating-days/{business_date}` | Body `{status, closure_reason, expected_version}`. Require an exact version match. Return the updated entry. Setting Closed requires a reason and no completed transactions on that date. |
| `POST /api/v1/operating-days/bulk-verify-open` | Body `{dates: [{business_date, expected_version}, ...]}` with at most 90 distinct historical dates. Only Unknown dates qualify; every date must have been explicitly reviewed and selected. Validate and update all dates atomically, then return changed entries and count. Existing Open or Closed dates require individual correction. |
| `GET /api/v1/operating-days/{business_date}/history` | Bounded, newest-first Owner audit history of status and reason corrections. |
| `GET /api/v1/reports/weekday-sales?from=YYYY-MM-DD&through=YYYY-MM-DD` | At most 366 dates, ending no later than Manila today. Return the range, trusted `as_of`, coverage summary, and seven ordered weekday rows. |

Return distinct HTTP 409 codes for `operating_day_changed`, `completed_sales_on_date`, and `business_date_closed`. Use 422 for invalid dates, ranges, status/reason combinations, duplicate bulk dates, and limits. Preserve existing 401/403 handling. After a 409 calendar edit, refresh the reviewed dates before retrying; do not overwrite a newer Owner correction.

## Financial consistency and lock order

Use a transaction-scoped PostgreSQL advisory lock keyed by a distinct `calendar:YYYY-MM-DD` namespace. Every supported writer that can create a Completed transaction must take it before insertion. Calendar writes take the same lock before checking or changing a status. Read or refresh status only after locking and hold the lock through commit or rollback.

| Operation | Lock and write order |
|---|---|
| New Direct sale | Existing user/key lock, exact replay and reservation checks, existing rule/catalog/staff locks, trusted time and its Manila date lock, refreshed status check, then transaction/items/claim and optional attempt commit. |
| New Manual sale | Existing user/key lock, optional paper-reference lock and reservation, exact replay and validation, existing catalog/staff locks, occurrence-date lock, refreshed status check, then transaction/items/audit/claim and optional attempt commit. |
| Individual correction | Date lock, version and current-status check, Completed-transaction check if setting Closed, row update and audit, one commit. |
| Bulk Open verification | Distinct date locks in ascending order, validate all versions/statuses/dates, write all rows and audits, one commit; any failure rolls back all. |
| Exact committed-key replay | Return the validated prior sale under the existing key rules. Do not treat a later closure/status correction as a new-sale check. |

The final transaction writer enforces Closed even if an optional reservation was confirmed earlier. A rejected new sale rolls back its sale and idempotency claim; an already committed Reserved attempt remains for exact-key retry or its existing Owner resolution flow. The browser keeps the same pending key, checks its status, and never creates a replacement key automatically. Update the sale API client to retain safe error codes so `business_date_closed` can be explained separately from an idempotency conflict.

For Direct sales, re-read trusted time after waiting for the date lock. If that wait crosses Manila midnight, roll back and require exact-key status check/retry; never insert using a different business date from the locked date. Bound lock waits and retain the existing uncertain-outcome response behavior. Calendar writers must not acquire catalog/staff locks after a date lock; ascending bulk dates avoid a bulk-versus-bulk cycle. A concurrent void may conservatively cause a Closed request to fail while its sale still appears Completed; an Owner can retry after the void commits.

This application-level contract covers both Direct and Manual final writers in legacy and reservation-aware modes. Reservation creation, voiding, and Owner acknowledgment do not create new Completed transactions. Direct SQL outside these services can bypass the lock; expose such anomalies instead of changing financial records. Do not enable calendar writes while old sale-writer workers that lack the date lock still serve traffic.

## Weekday analytics contract

Generate all dates in the requested range, including dates with zero transactions. Aggregate `transaction_items.selling_price` by `transactions.business_date` only where transaction status is Completed; then join daily sums to statuses and group Monday through Sunday. Avoid item/calendar join multiplication. One PostgreSQL aggregation statement should give sales and statuses a consistent snapshot. Return decimal strings and perform no money arithmetic in React.

For each weekday return `gross_sales` for all Completed sales in the range, `historical_gross_sales`, `verified_open_gross_sales`, `provisional_today_gross_sales`, `verified_open_days`, `verified_closed_days`, `unknown_days`, `unconfirmed_planned_days`, `closed_dates_with_sales`, and `average_gross_per_verified_open_day`. The average is `verified_open_gross_sales / verified_open_days`, rounded to cents using Decimal `ROUND_HALF_UP`; it is null when the denominator is zero. A verified Open historical zero-sales date contributes one day and zero sales. Today is provisional and never enters status counts or averages, even if marked Open.

Unknown historical dates and past PlannedClosed dates are separately counted, both excluded from averages, and both cause `incomplete_coverage: true`. Return their combined unverified count in the coverage summary. A partial average is allowed but must display the warning and counts. PlannedClosed never inflates verified Closed. Historical Closed dates with Completed sales are reported as anomalies; their sales remain in total gross but not verified-open gross. An empty period still returns seven zero-sales weekday rows with null averages. Existing Daily and Monthly reports remain unchanged.

## Owner interface

Add Calendar and Weekday views within the existing Owner Reports section; Cashiers retain today's Daily report. Pass the in-memory CSRF token to Calendar writes. Follow current report controls, loading/retry and session revalidation, same-origin fetch, accessible tables, themes, and mobile layout.

Calendar shows all four statuses, reasons, Completed-sale counts, history, and conflicts. A bulk workflow previews the exact historical Unknown dates, including zero-sales dates, lets the Owner select them, and confirms the count before one request. Past plans visibly need confirmation. Weekday view separates total gross from the verified-open average, displays its day denominator, unknown and unconfirmed-plan counts, a partial-coverage warning, provisional today, and an unavailable average when the denominator is zero. A stale edit refreshes the affected range without silently discarding the Owner's review context.

## Implementation milestones and acceptance checks

1. **Persistence and Owner calendar API:** add model, migration, registry, router, service, schemas, and audit history. Test constraints, Manila dates, status transitions, version conflicts, 401/403/CSRF, Closed-sale conflicts, and all-or-nothing bulk writes.
2. **Sale consistency:** add the shared date lock to both final writers. Test Closed rejection, PlannedClosed allowance, exact-key replay, claim rollback, reservations, pending-key handling, Manila rollover, lock timeouts, and two-connection sale/closure races. Keep `reserved_v1` disabled.
3. **Analytics:** add the bounded date-series query and Owner endpoint. Test void exclusion, zero-sales Open days, all seven weekdays, partial coverage, past plans, anomalous Closed dates, provisional today, empty periods, and range limits. Re-run existing Daily/Monthly API tests without contract changes.
4. **Owner UI and operational checks:** add Calendar and Weekday views and focused frontend tests for role isolation, bulk preview, correction conflicts, warnings, loading/error states, and exact-key sale recovery. Run the frontend build. Update revision-aware production startup, restore verification, migration/model tests, and guarded PostgreSQL preflights as appropriate for the additive revision; keep older-schema-specific safety checks intentional.

PostgreSQL concurrency and integration suites require their existing isolated-test-database checks and opt-in. A production rollout needs separate readiness and migration review; staging is not assumed to be production-ready. Implementation, migration execution, deployment, and `reserved_v1` activation are outside this documentation contribution.
