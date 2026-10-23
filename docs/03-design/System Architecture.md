# System Architecture — Yab's Salon Management System

## Document Information

| Field | Value |
|---|---|
| Project | Yab's Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Version | 1.0 — Development Baseline |
| Status | Approved for MVP implementation; production readiness not yet verified |
| Updated | 2026-10-14 |

## 1. Purpose and scope

This document is the consolidated implementation blueprint for the internal salon MVP. It follows the validated MVP Scope and Database Design v1.1. The MVP supports Owner and Cashier accounts, catalog and staff management, commission configuration, completed sales with multiple items, Cash/GCash payments, transaction voids, and daily/monthly reporting. Inventory, bookings, customer accounts, native mobile apps, AI features and offline synchronization are out of scope.

**Design philosophy:** Build a maintainable MVP, validate with salon users, and refine from evidence. Do not over-engineer before the first working vertical slice.

## 2. Architectural style and stack

Three-tier, feature-based **modular monolith**:

1. **Presentation:** React browser application for Owner and Cashier.
2. **Application:** Python FastAPI REST API with routers, services, and repositories.
3. **Data:** PostgreSQL accessed using synchronous SQLAlchemy 2.x; Alembic for schema migrations.

Browser → HTTPS JSON `/api/v1` → FastAPI → SQLAlchemy → PostgreSQL. React never connects directly to the database. Business calculations and authorization belong to FastAPI. All tools can be used free for local development; reliable production cloud hosting may incur charges.

## 3. Backend module organization

```text
backend/
├── app/
│   ├── main.py
│   ├── core/                 # config, security, errors
│   ├── db/                   # engine, sessions, model registration
│   └── modules/
│       ├── auth/
│       ├── users/
│       ├── staff/
│       ├── catalog/
│       ├── commissions/
│       ├── transactions/
│       └── reports/
├── migrations/
├── tests/
├── pyproject.toml
└── .env.example
```

Each feature may contain `router.py`, `service.py`, `repository.py`, `schemas.py`, `models.py` as needed, not as empty ceremony. Routers handle HTTP and dependencies; services own rules and coordinate financial transactions; repositories encapsulate queries; Pydantic schemas validate requests/responses; ORM models map approved tables. Modules call internal interfaces rather than HTTP between themselves. Avoid circular imports and commits inside item-level repositories.

## 4. Roles and permissions

| Operation | Owner | Cashier |
|---|---|---|
| Log in/out | Yes | Yes |
| Record current-day direct sales | Yes | Yes |
| Encode same-day paper sales | Yes | Yes |
| Encode previous-day paper sales | Yes | No |
| Reconcile historical paper sales | Yes | No |
| View current Manila-date transactions | Yes | Yes |
| View historical transactions | Yes | No |
| View transaction-level Staff Commission, Business Share, and commission snapshots within authorized dates | Yes | Yes |
| View today's operational totals (gross, Cash, GCash, staff commissions) | Yes | Yes |
| View monthly reports | Yes | No |
| Manage staff, catalog, prices, commissions, accounts | Yes | No |
| Void completed transactions | Yes | No |

One shared salon business day equals a calendar date in `Asia/Manila`; no separate shifts entity. Cashiers see all transactions assigned to **today's business date**, regardless of which cashier recorded them. FastAPI applies authorization and date filtering to list and detail queries. At midnight, prior-day records become Owner-only. Owner voids use the existing valid Owner session; **no manager/admin passcode or repeat password**. A void requires confirmation, reason, backend role/CSRF/state validation, atomic update, and audit event. Frontend button visibility is not a security control.

**Future multi-branch requirement (not implemented in the MVP):** Cashiers need Gross Sales, Staff Commission, Business Share, commission-rule snapshots, credited Staff, payment details, and transaction status within their authorized operational scope. Before supporting multiple branches, explicitly design branch-scoped authorization and review branch ownership for Users, Staff, catalog records, transactions, idempotency recovery, and financial reports. The current schema and shared-business-date checks do **not** provide branch isolation; do not deploy this implementation as multi-branch without that design and migration review.

## 5. Authentication and session security

- Server-managed sessions stored in PostgreSQL `auth_sessions`; multiple active sessions per account allowed.
- Login verifies Argon2id password hash and active account. Generate a high-entropy random token, store only its hash, and send token in an HttpOnly cookie.
- Production cookie: `__Host-salon_session` with `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`, and no Domain. Local HTTP development uses a separate cookie name/configuration.
- Inactivity timeout: 8 hours, checked server-side; logout revokes current session; account deactivation blocks all sessions. Validate current role on protected requests.
- CSRF token and Origin checks protect state-changing operations. Rate-limit login and other sensitive operations. Never log credentials or raw tokens.

## 6. Financial transaction processing

- Transaction may contain multiple service/product items; exactly one of service/product per item. Service staff assignment mandatory; product staff optional.
- Prices, commission type/rate and calculated staff commission/Business Share are captured as immutable sale-item snapshots. Support percentage and fixed commissions per original database rules; use Decimal, not floating-point currency math.
- Cash and GCash are supported; GCash reference required only for GCash. Backend calculates totals and verifies constraints.
- One service-coordinated database transaction saves header, items, and relevant idempotency/audit records. Commit all or roll back all.
- Voids preserve original transactions and items, mark status and void metadata, and exclude voided sales from active reporting totals. Corrections use a new sale.
- Direct sale time is server assigned. Paper-sale back-entry preserves original occurrence time, separately stores creation time, source, manual reference, and recording user. Owner alone may back-enter previous-day transactions; cashier may enter same-day paper sales. Manual references must be checked for duplication.
- Historical commission rules/actual prices must be verified against contemporaneous records rather than silently applying current configuration.

## 7. Database and migrations

PostgreSQL is the authoritative persistence layer. SQLAlchemy 2.x synchronous operations use pooled connections and request-scoped sessions for ordinary requests. Services coordinate commits and rollbacks. Alembic manages reviewed schema migrations; an empty database starts from a coherent v1.1 baseline. Database Design v1.1 defines the original seven business entities plus authentication sessions, scoped audit events and sale idempotency. Enforce PK/FK, uniqueness, check constraints, and appropriate indexes.

## 8. API communication and errors

- Versioned REST JSON API under `/api/v1`, over HTTPS in production.
- GET retrieves, POST creates/initiates, PATCH partially updates. Never hard-delete completed financial records.
- React validation is for UX; FastAPI/Pydantic validates shape; services validate business rules; PostgreSQL enforces integrity.
- Standard error body: `{ "error": { "code": "...", "message": "...", "details": null, "request_id": "..." } }`.
- Use 401 for missing/expired authentication, 403 for insufficient permissions, 404 for missing resources, 409 for state conflicts, 422 for schema validation, 429 for rate limits, and 5xx for server/dependency failures. Do not expose internal tracebacks.
- Sale creation uses server-enforced idempotency keys, unique persistence and concurrent retry safety. Same key + same payload returns prior result; same key + different payload is rejected.
- Restrict CORS to approved origins if cross-origin; prefer same-origin production reverse proxy. FastAPI OpenAPI documents exact endpoints later in `API Design.md`.

## 9. Deployment and environments

**Approved MVP production strategy:** Online-only cloud deployment. No offline application mode or synchronization. Development is local; staging uses isolated non-production data; production hosts React, FastAPI and private PostgreSQL behind an HTTPS entry point. The hosting provider is an implementation-time selection, not a reason to delay coding.

During outages, staff record paper sales; once service returns, authorized users enter them with original timestamps and manual references. Same-day entry allowed for Owner/Cashier; previous-day entry and reconciliation Owner-only.

Keep `.env.example` with placeholders, never commit actual secrets, use protected production configuration, disable production debugging, restrict DB network access, and test migrations before release. Release flow: local tests → staging checks → migration review → backup verification → deployment → smoke test → monitoring.

## 10. Monitoring, backup and recovery

**ADR-019 approved targets:** Automated PostgreSQL backups daily after closing; 14-day retention; encrypted, access-controlled storage separate from primary DB; alert on backup failures; restoration drill at least quarterly. **RPO 24 hours; RTO 24 hours** are targets, not proven guarantees. Daily backups alone cannot meet RPO if backups fail; monitor latest usable restore point. Measure recovery duration and data loss in isolated drills. Use paper records and payment evidence to reconcile missing transactions. Production launch requires successful restore validation.

## 11. Auditability and operational security

Scoped `audit_events` captures login successes/failures, transaction void attempts and successes, commission changes, account/role changes, and historical back-entry. Logs identify actor where available, resource, action, outcome and time; never secrets. Session/permission checks apply to all protected operations. Use least-privilege DB credentials, safe SQLAlchemy queries, HTTPS, CSRF protection and restricted infrastructure access.

## 12. Architecture decisions summary

| ADR | Decision | Status |
|---|---|---|
| 001–006 | Three-tier React + FastAPI + PostgreSQL, backend financial authority | Approved |
| 007–012 | Cookie sessions, RBAC, Argon2id, CSRF, scoped auditability | Approved |
| 013 | Feature-based modular monolith | Approved |
| 014 | Owner/Cashier access, shared business-day visibility | Approved (refined by 020) |
| 015 | Owner-session-only transaction voiding | Approved |
| 016 | SQLAlchemy 2.x synchronous + Alembic | Approved |
| 017 | Versioned REST, validation, errors, sale idempotency | Approved |
| 018 | Online-only cloud production, paper outage fallback | Approved |
| 019 | Daily backups; 24h RPO / 24h RTO | Approved objectives; verify before launch |
| 020 | Calendar-day cashier access | Approved |
| 021 | Same-day manual entry for both roles, previous-day Owner-only | Approved |
| 022 | PostgreSQL-backed multiple sessions per account | Approved |

## 13. Build-ready handoff and non-blocking details

Start with database models/migration and authentication, then a **vertical slice**: login → record one sale → compute commission → save atomically → display daily totals. Expand to multi-item transactions, GCash, owner administration, voids, reports, paper-sale entry, and recovery testing. Add tests for permissions, monetary calculations, rollback, duplicate submission, voids, and date-boundary behavior.

During implementation, decide exact endpoint names, manual reference format, audit/idempotency retention, logging provider, hosting vendor, and UI details. Document the decisions briefly as they arise. Before real salon use, verify backups/restores, RBAC, CSRF, data accuracy, and operational workflow with staff.

**Source-of-truth order:** MVP Scope and approved business rules → Database Design v1.1 → this System Architecture → API Design and Wireframes → application code/tests. If documents conflict, resolve the specific conflict rather than silently choosing an interpretation.
