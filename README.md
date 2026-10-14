# Yab's Salon Management System

> An internal web application for Yab's Hair and Beauty Studio, designed to digitize sales recording, staff commission calculations, and business reporting.

## Why This Project Exists

Yab's Hair and Beauty Studio currently relies on handwritten logbooks and manual calculations to record daily sales and determine staff commissions. These workflows take time, are prone to human error, and make historical reporting and reconciliation difficult.

This project starts from a real business problem. It also serves as a learning journey in product discovery, software engineering, and AI-assisted development: understanding the business first, then building and validating a maintainable product.

## Product Overview

The Salon Management System is an internal, browser-based application for two primary roles:

| Role | Responsibilities |
| --- | --- |
| **Owner** | Manages staff, catalog, commission rules and user accounts; reviews historical sales and reports; authorizes transaction voids and historical back-entry. |
| **Cashier** | Records completed sales and monitors authorized transactions for the current salon business date. |

Barbers and stylists are represented in staff and commission records but do not need individual system logins for the MVP.

## Business Problems and Objectives

The MVP aims to:

- Replace handwritten sales logs for normal online operations.
- Automatically calculate staff commissions and the remaining Business Share.
- Support completed service and product sales, including multiple items in a transaction.
- Reduce manual calculation errors and speed up daily reconciliation.
- Preserve original transaction prices, staff assignments, and commission amounts.
- Provide daily and monthly reports for authorized users.

**Business Share is not net profit.** Expense tracking and payroll are outside the MVP.

## MVP Features

- Secure Owner and Cashier login with role-based access control.
- Staff, service, product, price, and commission-rule management.
- Completed transactions with multiple service and/or product items.
- Required staff assignment for service items; optional assignment for product items.
- Variable service prices.
- Cash and GCash payments, with required reference numbers for GCash.
#NAME?
- Daily and monthly sales reports and staff commission breakdowns.
#NAME?
- Current-day manual sale back-entry by Owner or Cashier; previous-day back-entry and reconciliation by Owner only.

### Important Business Rules

- Haircut commission: **50% staff / 50% Business Share**.
- Services using salon products: **40% staff / 60% Business Share**.
- Product sales may have a fixed staff commission. If no staff member is assigned, no staff commission is earned for that product item.
- **Staff Commission + Business Share = Selling Price** for each sale item.
- **Cash Sales + GCash Sales = Gross Sales** under the approved reporting rules.
- Record sales only after payment has been received.
- A completed sale cannot be edited or deleted. Corrections use a new transaction; only the Owner may void an existing sale.
- Voided sales do not contribute to active sales and commission reports.
- Historical financial values are snapshotted and must not change when catalog prices or commission rules change.
- Money calculations use decimal-safe arithmetic.

## Out of Scope for the MVP

Inventory management, appointments, customer profiles and history, loyalty programs, expense tracking, payroll, multi-branch operations, native mobile apps, offline application synchronization, AI forecasting, and advanced business intelligence.

## Technology Stack

| Layer | Approved Technology |
| --- | --- |
| Frontend | React |
| Backend | Python + FastAPI |
| Database | PostgreSQL |
| ORM | SQLAlchemy 2.x (synchronous) |
| Database migrations | Alembic |
| API | Versioned REST API (`/api/v1`) using JSON |
| Authentication | PostgreSQL-backed server-managed sessions with secure HttpOnly cookies |
| Version control | Git and GitHub |
| Production deployment | Online-only cloud deployment; hosting provider to be selected |

The backend follows a **feature-based modular monolith** design. Financial calculations and authorization are enforced on the backend.

## Repository Structure

The repository currently contains product documentation and an initial backend scaffold. The following is a **conceptual layout**; some folders and files will be created during development rather than existing today.

```text
salon-management-system/
├── README.md
├── backend/                # Initial scaffold; implementation in progress
│   └── app/
│       ├── core/
│       ├── db/
│       └── modules/        # Business modules will be implemented here
├── docs/
│   ├── 01-discovery/
│   ├── 02-planning/
│   ├── 03-design/
│   ├── 04-development/
│   ├── 05-testing/
│   └── 06-retrospective/
└── frontend/               # Planned, not yet implemented
```

Other folders such as tests, migrations, and deployment configuration will be introduced as needed. The actual Git repository is the source of truth for current file locations.

## Documentation

This is a documentation-first project. The key specifications are maintained in `docs/`:

- **Discovery:** Business Requirements Specification and user personas.
- **Planning:** MVP Scope, PRD, roadmap, and user stories.
- **Design:** Database Design, proposed v1.1 revisions, System Architecture, API Design, and wireframes.
- **Development / Testing / Retrospective:** Working records and deliverables to be filled as implementation proceeds.

The approved business rules and current design decisions should guide implementation. Where documents disagree, the inconsistency must be reviewed rather than silently ignored.

## Project Roadmap and Current Status

| Phase | Status |
| --- | --- |
| Business discovery | Documented |
| MVP planning | Documented |
| Database and system architecture | Designed; refinements may continue during implementation |
| API design and wireframes | Detailed implementation work pending |
| Application development | Starting: backend foundation |
| Testing | Not yet implemented |
| Production deployment | Not yet implemented |
| Retrospective / portfolio case study | Planned |

**Current status:** The project is transitioning from planning and design into AI-assisted MVP implementation. The repository includes documentation and an initial backend scaffold; the application is **not yet functional or production-ready**.

### Initial Development Approach

Work in small, testable increments: inspect the relevant specification, plan a focused change, implement, run tests, review the diff, and commit verified work. Early tasks will establish the FastAPI foundation, database access, and automated tests before implementing financial workflows.

## Production and Business Continuity

The MVP is **online-only**. During an internet or service outage, salon staff will use a manual paper sales log. Once service returns, authorized users will encode and reconcile missing transactions while preserving the original business date.

The approved recovery targets are **24-hour RPO and 24-hour RTO**, with daily PostgreSQL backups, 14-day retention, and quarterly restore tests. These are **design objectives**, not proven capabilities; they must be validated before production use.

## Success Measures

The product aims to make transaction entry fast, eliminate manual commission calculation during normal operations, improve daily reconciliation, and provide reliable financial history. The original planning target of recording a sale in under 30 seconds will need validation with real users.

## Future Enhancements

Potential post-MVP improvements include inventory, appointments, customer records, exportable reports, multi-branch support, and advanced analytics. Essential security and financial audit events are already part of the current design and are **not** deferred as a general future enhancement.

## Development Philosophy

This repository documents a real product-development journey: discovering a business problem, defining the MVP, designing the system, implementing it with AI assistance, testing it, and improving it through feedback. AI can assist with implementation, but generated changes must be reviewed and tested before they are accepted.

## Author

Rafael Hidalgo  
Second-Year Computer Science Student — Artificial Intelligence specialization  

Building software with a product-first mindset by combining business analysis, software engineering, and AI-assisted development.
