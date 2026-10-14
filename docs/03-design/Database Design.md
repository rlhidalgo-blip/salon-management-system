# Database Design

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | Database Design |
| Version | 1.1 |
| Status | Development baseline — implementation pending |
| Author | Rafael Hidalgo |
| Date Created | August 19, 2026 |
| Last Updated | August 25, 2026 |

## Purpose

This document defines the database design for the MVP of the Salon Management System.

The database is designed to support the validated business requirements of Yab's Hair and Beauty Studio, including staff and business configuration, transaction recording, commission calculation, Cash and GCash payment tracking, historical record preservation, transaction voiding, and business reporting.

The design establishes the core data entities, relationships, historical data strategy, and integrity rules required to maintain accurate and reliable business records.

This document describes the logical database design before implementation-specific PostgreSQL schema and migration details are finalized.

## Design Principles

### Preserve Historical Truth

Completed transactions must preserve the information that was true at the time of sale.

Changes to current service prices, product prices, commission rules, staff availability, or other business configuration must not alter previously completed transaction records.

### Separate Current Configuration from Historical Records

Configuration entities such as Services, Products, Staff, and Commission Rules represent the current operational state of the business.

Transaction Items preserve historical sale information such as the actual selling price, commission rule applied, Staff Commission, and Business Share.

### Protect Financial Integrity

The database design must support the validated financial relationship:

Staff Commission + Business Share = Selling Price

Invalid financial values, contradictory transaction data, and invalid relationships should be prevented through appropriate application validation and database constraints.

### Preserve Records Instead of Destructive Deletion

Business records referenced by historical transactions should not be permanently removed when they are no longer used.

Staff members, Services, Products, and Commission Rules may instead become inactive while historical transaction relationships remain preserved.

Completed transactions shall not be directly edited or permanently deleted.

### Keep the MVP Data Model Purposeful

The database should support the validated MVP without introducing unnecessary entities or complexity for unvalidated future requirements.

For example, payment information will remain part of the Transaction entity because the MVP supports one payment method per transaction.

A separate Payments entity may be reconsidered if future requirements introduce split payments or more complex payment workflows.

### Derive Report Totals from Transaction Data

Business reporting values such as Gross Sales, Cash Sales, GCash Sales, total Staff Commission, and total Business Share should be derived from the underlying valid transaction records rather than treated as independent sources of financial truth.

Voided transactions must be excluded from active financial totals.

## Data Model Overview

The MVP database is currently designed around seven core entities.

| Entity | Purpose |
|---|---|
| Users | Stores authenticated Owner and Cashier accounts and their system roles. |
| Staff | Stores barbers and stylists who may be associated with sale items. |
| Commission Rules | Stores the current configurable commission rules used by Services and Products. |
| Services | Stores the services currently configured by the business. |
| Products | Stores products currently configured for sale. |
| Transactions | Stores transaction-level information such as date and time, payment method, status, and void information. |
| Transaction Items | Stores the individual Services or Products included within each Transaction together with their historical financial values. |

## High-Level Relationships

The current logical relationships are:

- One Transaction can contain many Transaction Items.
- One Staff member can be associated with many Transaction Items over time.
- One Service can appear in many Transaction Items over time.
- One Product can appear in many Transaction Items over time.
- One Commission Rule can be associated with many Services.
- One Commission Rule can be associated with many Products.
- One User may be associated with multiple voided Transactions as the user who performed the void.

A Transaction Item represents exactly one sold item and therefore references either one Service or one Product, but never both.

Service Transaction Items require an assigned Staff member.

Product Transaction Items may optionally reference a Staff member depending on whether a staff member is credited for the product sale.

Commission Rules
    ├── Services
    └── Products
          │
          ▼
    Transaction Items
       ▲    ▲    ▲
       │    │    │
     Staff  │    │
            │    │
      Transactions
            ▲
            │
          Users
       (voided by)

## Entity Definitions

The following sections define the logical fields and responsibilities of each core entity in the MVP database.

Database-specific data types and implementation details will be defined after the logical data model has been validated.

### Users

The Users entity represents authenticated accounts that are permitted to access the Salon Management System.

Users are separate from Staff because system users represent people authorized to access the application, while Staff represents barbers and stylists associated with sale items.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a user account | Yes | Primary key |
| `username` | Identifies the account during authentication | Yes | Must uniquely identify a user account |
| `password_hash` | Stores the securely hashed representation of the user's password | Yes | Plaintext passwords shall not be stored |
| `role` | Determines the user's system permissions | Yes | MVP roles are Owner and Cashier |
| `active` | Determines whether the account is currently permitted to access the system | Yes | Inactive accounts cannot authenticate |

### Staff

The Staff entity represents barbers and stylists who may be associated with Service and Product sale items.

Staff records do not represent system login accounts. A Staff member may exist in the database without having access to the Salon Management System.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a staff member | Yes | Primary key |
| `name` | Stores the staff member's display name | Yes | Used for transaction assignment and reporting |
| `role` | Identifies the staff member as a Barber or Stylist | Yes | Represents the staff member's operational role |
| `active` | Determines whether the staff member can be assigned to new sale items | Yes | Inactive Staff remain preserved for historical transaction references |

### Commission Rules

The Commission Rules entity represents the current configurable rules used to determine Staff Commission for Services and Products.

A Commission Rule may be referenced by multiple Services or Products.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a commission rule | Yes | Primary key |
| `name` | Provides a human-readable name for the rule | Yes | Example: Haircut Commission |
| `type` | Determines how the commission value is interpreted | Yes | Supported MVP types are Percentage and Fixed |
| `value` | Stores the staff-side commission percentage or fixed amount | Yes | Meaning depends on `type` |
| `active` | Determines whether the rule is available for current configuration | Yes | Historical transaction commission snapshots remain unchanged |

### Services

The Services entity represents the current services offered by Yab's Hair and Beauty Studio.

Service configuration may change over time without modifying historical transaction records.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a service | Yes | Primary key |
| `name` | Stores the current service name | Yes | Historical transaction items preserve the name used at the time of sale |
| `current_price` | Stores the currently configured service price | Yes | Historical selling prices are stored separately in Transaction Items |
| `allows_variable_price` | Determines whether the Cashier may enter a different final selling price | Yes | Supports services whose final price varies |
| `commission_rule_id` | Identifies the current commission rule applied to the service | Yes | Foreign key referencing Commission Rules |
| `active` | Determines whether the service is available for new transactions | Yes | Inactive Services remain available to historical references |

### Products

The Products entity represents products currently configured for sale by Yab's Hair and Beauty Studio.

Products remain separate from Services because their staff-assignment, pricing, and commission behavior differ.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a product | Yes | Primary key |
| `name` | Stores the current product name | Yes | Historical transaction items preserve the name used at the time of sale |
| `current_price` | Stores the currently configured selling price | Yes | Historical selling prices are preserved in Transaction Items |
| `commission_rule_id` | Identifies the current fixed commission rule applicable to the product | Yes | Foreign key referencing Commission Rules |
| `active` | Determines whether the product is available for new transactions | Yes | Inactive Products remain available to historical references |

### Transactions

The Transactions entity represents a completed customer sale at the transaction level.

Transaction-level information applies to the entire customer transaction rather than to individual Services or Products contained within it.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a transaction | Yes | Primary key |
| `date_time` | Records when the transaction occurred | Yes | Used for daily, monthly, and historical reporting |
| `payment_method` | Records how the transaction was paid | Yes | MVP values are Cash and GCash |
| `gcash_reference` | Stores the GCash payment reference number | Conditional | Required for GCash and absent for Cash |
| `status` | Identifies whether the transaction is active or voided | Yes | MVP statuses are Completed and Voided |
| `void_reason` | Records why the transaction was voided | Conditional | Required only when status is Voided |
| `voided_by_user_id` | Identifies the User who performed the void | Conditional | Foreign key referencing Users; required for voided transactions |
| `voided_at` | Records when the transaction was voided | Conditional | Required only when status is Voided |

### Transaction Items

The Transaction Items entity represents each individual Service or Product sold within a Transaction.

Transaction Items preserve historical financial information so that changes to current Services, Products, prices, Staff availability, or Commission Rules do not alter previously completed sales.

| Field | Purpose | Required | Notes |
|---|---|---|---|
| `id` | Uniquely identifies a transaction item | Yes | Primary key |
| `transaction_id` | Identifies the Transaction containing the item | Yes | Foreign key referencing Transactions |
| `service_id` | Identifies the originating Service | Conditional | Used for Service items; mutually exclusive with `product_id` |
| `product_id` | Identifies the originating Product | Conditional | Used for Product items; mutually exclusive with `service_id` |
| `staff_id` | Identifies the Staff member credited for the sale item | Conditional | Required for Services; optional for Products |
| `item_name_snapshot` | Preserves the item name used at the time of sale | Yes | Prevents later name changes from rewriting historical records |
| `selling_price` | Preserves the actual price charged for the item | Yes | Must remain unchanged after transaction completion |
| `commission_type_snapshot` | Preserves how commission was calculated at the time of sale | Conditional | Percentage or Fixed when commission applies |
| `commission_value_snapshot` | Preserves the percentage or fixed value used at the time of sale | Conditional | Represents the rule actually applied |
| `staff_commission` | Preserves the calculated amount awarded to Staff | Yes | Zero when a Product sale has no credited Staff member |
| `business_share` | Preserves the calculated amount attributed to the business | Yes | Selling Price minus Staff Commission |

## Data Integrity and Constraints

The database and application must prevent invalid or contradictory data from being stored.

Some rules may be enforced directly through database constraints, while others require application-level validation or authorization. The implementation strategy will be determined during technical implementation.

### Transaction Item Integrity

- Every Transaction Item shall belong to exactly one Transaction.
- Every Transaction Item shall reference exactly one Service or one Product.
- A Transaction Item shall not reference both a Service and a Product.
- A Transaction Item shall not exist without referencing either a Service or a Product.
- A Service Transaction Item shall require an assigned Staff member.
- A Product Transaction Item may optionally have an assigned Staff member.
- Referenced Staff, Services, and Products must exist.
- Inactive Staff, Services, and Products shall not be available for new Transaction Items.
- Historical Transaction Items may continue referencing records that later become inactive.
- A completed Transaction shall contain at least one Transaction Item.

### Price and Financial Integrity

- Selling Price shall be greater than zero.
- Staff Commission shall not be negative.
- Business Share shall not be negative.
- Staff Commission shall not exceed Selling Price.
- For every Transaction Item:

  `Staff Commission + Business Share = Selling Price`

- Business Share shall be calculated as:

  `Business Share = Selling Price - Staff Commission`

### Commission Integrity

- Percentage-based Commission Rules shall have a value greater than 0 and no greater than 100.
- Fixed Commission Rules shall have a value greater than 0.
- A fixed Staff Commission shall not exceed the Selling Price of the applicable Transaction Item.
- Service Transaction Items shall use the applicable configured percentage-based commission rule.
- Product Transaction Items with an assigned Staff member shall use the applicable configured fixed commission rule.
- Product Transaction Items without an assigned Staff member shall generate zero Staff Commission.
- When a Product Transaction Item has no assigned Staff member, the full Selling Price shall be treated as Business Share.
- When no Staff Commission is applied to a Product Transaction Item, commission snapshot fields shall remain empty.

### Payment Integrity

- Payment Method shall be either Cash or GCash for the MVP.
- GCash Transactions shall require a GCash reference number.
- Cash Transactions shall not contain a GCash reference number.
- The recorded payment information shall remain associated with the completed Transaction.

### Transaction Status and Voiding Integrity

- Transaction Status shall be either Completed or Voided for the MVP.
- A Completed Transaction shall not contain void information.
- A Voided Transaction shall require a Void Reason.
- A Voided Transaction shall identify the User who performed the void.
- A Voided Transaction shall record when the void occurred.
- Only an authenticated User with the Owner role shall be authorized to void a Transaction.
- Voiding shall not delete or modify the original Transaction Items or their historical financial values.
- Voided Transactions shall be excluded from active sales, payment, commission, and Business Share calculations.

### Referential and Historical Integrity

#NAME?
- Historical Transaction Items shall remain preserved when related Staff, Services, Products, or Commission Rules are later changed or made inactive.
- Staff, Services, and Products referenced by historical Transaction Items shall not be destructively removed in a way that breaks historical relationships.
- Destructive cascading deletion shall not be used where it could remove historical financial records.
- Completed Transactions and their Transaction Items shall not be permanently deleted as part of normal application operation.

## Historical Data Strategy

The database shall distinguish between current business configuration and historical transaction facts.

### Current Configuration

The following entities represent information that may change as the business operates:

#NAME?
#NAME?
#NAME?
- Commission Rules

Changes to these entities affect future business operations but shall not rewrite completed Transactions.

Examples include:

- Changing a Service's current price
- Changing a Product's current price
- Changing a Commission Rule
- Renaming a Service or Product
- Making a Staff member inactive
- Making a Service or Product inactive

### Historical Transaction Snapshots

Transaction Items shall preserve the information required to reconstruct the financial conditions of a completed sale.

Historical values include:

- Item name at the time of sale
- Actual Selling Price
- Applicable Staff assignment
- Commission type applied, when applicable
- Commission percentage or fixed value applied, when applicable
- Calculated Staff Commission
- Calculated Business Share

These values shall not be recalculated from current configuration when historical Transactions are viewed.

### Example

If a Haircut is sold for ₱200 using a 50% Staff Commission:

- Selling Price = ₱200
- Commission Type = Percentage
- Commission Value = 50%
- Staff Commission = ₱100
- Business Share = ₱100

If the current Haircut price later changes to ₱250 or the commission rule changes, the historical Transaction Item shall continue to represent the original ₱200 sale and its original commission calculation.

## Reporting and Derived Data

Financial reports shall be generated from preserved Transaction and Transaction Item data rather than relying on independently maintained report totals.

### Derived Financial Values

The following report values can be derived from active Transactions and their Transaction Items:

- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Total Business Share
#NAME?
#NAME?
- Transaction counts

For example:

`Gross Sales = SUM(Selling Price of applicable active Transaction Items)`

`Total Staff Commission = SUM(Staff Commission of applicable active Transaction Items)`

`Total Business Share = SUM(Business Share of applicable active Transaction Items)`

Payment Method and Transaction date/time may be used to filter and group financial information for Daily and Monthly Reports.

### Voided Transactions

Transactions with a Voided status shall remain stored for historical traceability but shall not contribute to active financial reporting.

### Reporting Consistency

For applicable active report data:

`Cash Sales + GCash Sales = Gross Sales`

and:

`Total Staff Commission + Total Business Share = Gross Sales`

## Entity Relationship Diagram

The Entity Relationship Diagram (ERD) represents the logical relationships between the core entities of the MVP database.

The diagram focuses on entity relationships and cardinality. Implementation-specific PostgreSQL data types and physical schema details will be defined separately.

### Relationship Summary

| Parent Entity | Child Entity | Relationship | Foreign Key | Notes |
|---|---|---|---|---|
| Commission Rules | Services | One-to-Many | `services.commission_rule_id` | Multiple Services may use the same Commission Rule |
| Commission Rules | Products | One-to-Many | `products.commission_rule_id` | Multiple Products may use the same Commission Rule |
| Transactions | Transaction Items | One-to-Many | `transaction_items.transaction_id` | A Transaction contains one or more sale items |
| Staff | Transaction Items | One-to-Many | `transaction_items.staff_id` | Required for Services and optional for Products |
| Services | Transaction Items | One-to-Many | `transaction_items.service_id` | Used only when the Transaction Item represents a Service |
| Products | Transaction Items | One-to-Many | `transaction_items.product_id` | Used only when the Transaction Item represents a Product |
| Users | Transactions | One-to-Many | `transactions.voided_by_user_id` | Optional relationship used when a Transaction is voided |

### Logical ERD

```mermaid
erDiagram

    USERS ||--o{ TRANSACTIONS : "voids"

    COMMISSION_RULES ||--o{ SERVICES : "applies to"
    COMMISSION_RULES ||--o{ PRODUCTS : "applies to"

    TRANSACTIONS ||--|{ TRANSACTION_ITEMS : "contains"

    STAFF ||--o{ TRANSACTION_ITEMS : "credited on"
    SERVICES ||--o{ TRANSACTION_ITEMS : "referenced by"
    PRODUCTS ||--o{ TRANSACTION_ITEMS : "referenced by"
```

## Physical PostgreSQL Design

This section translates the validated logical data model into PostgreSQL-oriented data types, constraints, defaults, and referential behavior.

The physical database design remains subject to validation before implementation and migration scripts are created.

### Identifier Strategy

All core MVP entities will use automatically generated integer primary keys.

This approach provides simple and stable record identifiers while remaining appropriate for the expected scale and architecture of the Salon Management System.

The identifier strategy applies to:

#NAME?
#NAME?
- Commission Rules
#NAME?
#NAME?
#NAME?
- Transaction Items

### Staff — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `name` | `TEXT` | NOT NULL | — |
| `role` | `TEXT` | NOT NULL | Must be `Barber` or `Stylist` |
| `active` | `BOOLEAN` | NOT NULL | Default `TRUE` |

### Users — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `username` | `TEXT` | NOT NULL | UNIQUE |
| `password_hash` | `TEXT` | NOT NULL | Plaintext passwords are not stored |
| `role` | `TEXT` | NOT NULL | Must be `Owner` or `Cashier` |
| `active` | `BOOLEAN` | NOT NULL | Default `TRUE` |

### Commission Rules — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `name` | `TEXT` | NOT NULL | — |
| `type` | `TEXT` | NOT NULL | Must be `Percentage` or `Fixed` |
| `value` | `NUMERIC(12,2)` | NOT NULL | Must be greater than 0; Percentage values must not exceed 100 |
| `active` | `BOOLEAN` | NOT NULL | Default `TRUE` |

### Services — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `name` | `TEXT` | NOT NULL | — |
| `current_price` | `NUMERIC(12,2)` | NOT NULL | Must be greater than 0 |
| `allows_variable_price` | `BOOLEAN` | NOT NULL | Default `FALSE` |
| `commission_rule_id` | `INTEGER` | NOT NULL | Foreign Key referencing `commission_rules.id` |
| `active` | `BOOLEAN` | NOT NULL | Default `TRUE` |

### Products — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `name` | `TEXT` | NOT NULL | — |
| `current_price` | `NUMERIC(12,2)` | NOT NULL | Must be greater than 0 |
| `commission_rule_id` | `INTEGER` | NOT NULL | Foreign Key referencing `commission_rules.id` |
| `active` | `BOOLEAN` | NOT NULL | Default `TRUE` |

### Transactions — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `date_time` | `TIMESTAMPTZ` | NOT NULL | Default to current transaction timestamp |
| `payment_method` | `TEXT` | NOT NULL | Must be `Cash` or `GCash` |
| `gcash_reference` | `TEXT` | Conditional | Required for GCash; must be empty for Cash |
| `status` | `TEXT` | NOT NULL | Must be `Completed` or `Voided`; default `Completed` |
| `void_reason` | `TEXT` | Conditional | Required only when Voided |
| `voided_by_user_id` | `INTEGER` | Conditional | Foreign Key referencing `users.id`; required only when Voided |
| `voided_at` | `TIMESTAMPTZ` | Conditional | Required only when Voided |

### Transaction Items — Physical Design

| Column | PostgreSQL Type | Nullability | Constraint / Default |
|---|---|---|---|
| `id` | `INTEGER` | NOT NULL | Primary Key, automatically generated |
| `transaction_id` | `INTEGER` | NOT NULL | Foreign Key referencing `transactions.id` |
| `service_id` | `INTEGER` | Conditional | Foreign Key referencing `services.id`; mutually exclusive with `product_id` |
| `product_id` | `INTEGER` | Conditional | Foreign Key referencing `products.id`; mutually exclusive with `service_id` |
| `staff_id` | `INTEGER` | Conditional | Foreign Key referencing `staff.id`; required for Services and optional for Products |
| `item_name_snapshot` | `TEXT` | NOT NULL | Historical item name |
| `selling_price` | `NUMERIC(12,2)` | NOT NULL | Must be greater than 0 |
| `commission_type_snapshot` | `TEXT` | Conditional | Must be `Percentage` or `Fixed` when commission applies |
| `commission_value_snapshot` | `NUMERIC(12,2)` | Conditional | Must be greater than 0 when commission applies |
| `staff_commission` | `NUMERIC(12,2)` | NOT NULL | Must be greater than or equal to 0 |
| `business_share` | `NUMERIC(12,2)` | NOT NULL | Must be greater than or equal to 0 |

### Foreign-Key Deletion Strategy

Foreign-key relationships in the MVP shall use restrictive deletion behavior where deletion could break current configuration or historical financial records.

Referenced records should generally be made inactive rather than permanently deleted.

| Foreign Key | Deletion Behavior | Rationale |
|---|---|---|
| `services.commission_rule_id` | `RESTRICT` | Prevent Services from losing their configured Commission Rule |
| `products.commission_rule_id` | `RESTRICT` | Prevent Products from losing their configured Commission Rule |
| `transactions.voided_by_user_id` | `RESTRICT` | Preserve the identity of the User who performed a historical void |
| `transaction_items.transaction_id` | `RESTRICT` | Prevent deletion from breaking historical Transaction records |
| `transaction_items.service_id` | `RESTRICT` | Preserve historical Service relationships |
| `transaction_items.product_id` | `RESTRICT` | Preserve historical Product relationships |
| `transaction_items.staff_id` | `RESTRICT` | Preserve historical Staff relationships |

Destructive cascading deletion shall not be used for historical financial relationships.

Staff, Services, Products, Commission Rules, and User accounts should be made inactive when they are no longer available for current operation rather than deleted when referenced records depend on them.

### Physical Constraint Strategy

PostgreSQL constraints shall provide database-level protection for structural and financial invariants that must remain true regardless of application behavior.

Key physical constraints include:

#### Transaction Items

- Exactly one of `service_id` or `product_id` must contain a value.
- A Service Transaction Item must contain `staff_id`.
- `selling_price` must be greater than zero.
- `staff_commission` must be greater than or equal to zero.
- `business_share` must be greater than or equal to zero.
- `staff_commission + business_share` must equal `selling_price`.

#### Transactions

- `payment_method` must be either `Cash` or `GCash`.
- Cash Transactions must have no GCash reference.
- GCash Transactions must contain a GCash reference.
- `status` must be either `Completed` or `Voided`.
- Completed Transactions must contain no void metadata.
- Voided Transactions must contain a Void Reason, voiding User, and void timestamp.

#### Commission Rules

- `type` must be either `Percentage` or `Fixed`.
- Commission `value` must be greater than zero.
- Percentage commission values must not exceed 100.

#### Users and Staff

- User `role` must be either `Owner` or `Cashier`.
- Staff `role` must be either `Barber` or `Stylist`.

Application-level validation and authorization shall remain responsible for rules requiring additional business context, including:

- Only active Staff may be assigned to new Transactions.
- Only active Services and Products may be sold in new Transactions.
- The appropriate Commission Rule must be applied to the selected Service or Product.
- Product sales without assigned Staff must generate zero Staff Commission.
- Only authenticated Owners may void completed Transactions.

### Index Strategy

Indexes shall be introduced where they support validated query and reporting patterns rather than being added to every database column.

PostgreSQL automatically provides indexes for Primary Key and UNIQUE constraints.

For the initial MVP:

- Primary Key indexes will support record lookup and relationships.
- The UNIQUE constraint on `users.username` will support unique account identification.
- An index on `transactions.date_time` will support Daily, Monthly, and historical date-range reporting.

Additional indexes should be introduced only when actual query patterns or performance testing demonstrate a need.

### Physical Design Notes

The MVP physical design intentionally avoids unnecessary complexity.

The following decisions currently apply:

- UUID identifiers are not required for the current single-business architecture.
- A separate Payments table is not required because each MVP Transaction uses one payment method.
#NAME?
- General `created_at` and `updated_at` metadata is not required for configuration entities under the validated MVP requirements.
#NAME?
- Report totals are derived from Transaction and Transaction Item data rather than independently stored as financial totals.

## Version History

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | August 24, 2026 | Rafael Hidalgo | Initial Database Design for the MVP |

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| DB-D-001 | Separate Services and Products into distinct entities | Their pricing, staff-assignment, and commission behavior differ |
| DB-D-002 | Preserve historical financial values in Transaction Items | Current prices and commission rules must not rewrite completed sales |
| DB-D-003 | Derive report totals from Transaction data | Prevents independently maintained financial totals from becoming inconsistent |
| DB-D-004 | Keep payment information within Transactions for the MVP | Each MVP Transaction uses one payment method; split payments are outside scope |
| DB-D-005 | Use automatically generated integer primary keys | Appropriate for the expected scale and single-business architecture |
| DB-D-006 | Use `NUMERIC(12,2)` for financial values | Provides exact decimal representation for monetary calculations |
| DB-D-007 | Use restrictive foreign-key deletion behavior for protected relationships | Prevents deletion from damaging historical financial records |
| DB-D-008 | Divide integrity enforcement between PostgreSQL constraints and backend validation | Structural and financial invariants belong in the database while contextual business rules require application logic |
| DB-D-009 | Keep the initial index strategy minimal | Indexes should support validated query patterns and expand based on observed performance needs |
| DB-D-010 | Do not preserve Staff name snapshots in Transaction Items | Stable Staff references are sufficient while historical reporting prioritizes financial values |

---

# Version 1.1 Addendum — Approved Architecture Reconciliation

> **Status:** Development-ready design baseline, not an implemented database. This addendum supersedes conflicting v1.0 descriptions. Existing v1.0 entities and financial invariants remain in force unless explicitly changed here. The physical schema and migrations must reflect the combined design, not the original v1.0 tables alone.

## A. Calendar-day cashier access (ADR-020)

- The salon uses a single shared business date determined in `Asia/Manila`, midnight to midnight. No `shifts` table or clock-in/clock-out workflow is required for the MVP.
- Owner can view historical and current transactions. Cashier can view all transactions with `business_date` equal to the *current* Manila date, including transactions entered by other cashiers. Backend enforces this filter on list and detail endpoints.
- Add `transactions.business_date DATE NOT NULL`, derived from the validated occurrence timestamp in `Asia/Manila`; index it for reporting and cashier lookups.
- A back-entered transaction remains assigned to its original business date, not its system entry date.

## B. Direct and manual sales (ADR-021)

- Owner and Cashier may enter direct sales and paper-recorded **same-day** sales. Only Owner may back-enter **previous-day** sales and reconcile historical paper records. Future-dated sales are prohibited.
- Preserve the original `transactions.date_time TIMESTAMPTZ` as **sale occurrence time**. For direct sales the server sets it; for manual entry an authorized user supplies the original time, validated by FastAPI.
- Add `transactions.created_at TIMESTAMPTZ NOT NULL` (server-recorded entry time), `recorded_by_user_id INTEGER NOT NULL REFERENCES users(id)`, `entry_source TEXT NOT NULL` constrained to `Direct` or `Manual`, and `manual_reference TEXT NULL` (required for `Manual`, absent for `Direct`).
- Manual references are unique across the salon's manual logbook (unique partial index where non-null); staff must use a consistent reference format. This is a practical implementation convention, revisable if multiple independent logbooks are introduced.
- Historical selling prices and commission snapshots must reflect the *actual sale*, not today's catalog. For historical entries, the Owner must verify the applicable commission policy and original price against paper records; if not verifiable, flag for review rather than inventing figures.
- Reconciliation is an Owner-controlled procedure comparing paper logs/payment records to encoded sales. A dedicated reconciliation table/workflow is **deferred**; audit event and manual reference provide traceability. Do not silently alter completed sales; use Owner void plus corrected replacement transaction.

## C. Server-managed sessions (ADR-022)

Add `auth_sessions`:

| Column | PostgreSQL type | Rule |
|---|---|---|
| `id` | UUID | Primary key |
| `user_id` | INTEGER | Required FK → `users.id`, indexed, **not unique** |
| `token_hash` | CHAR(64) | Required, unique SHA-256 digest of high-entropy random cookie token |
| `created_at` | TIMESTAMPTZ | Required |
| `last_activity_at` | TIMESTAMPTZ | Required |
| `expires_at` | TIMESTAMPTZ | Required |
| `revoked_at` | TIMESTAMPTZ | Nullable |

One User has zero or many Sessions; simultaneous devices are allowed. Logout revokes only the current session; account deactivation blocks all sessions. Validate current role/status on protected requests. Eight-hour inactivity expiry, secure HttpOnly production cookie, CSRF defenses and eventual expired-session cleanup apply. The raw token is never persisted or logged. Account-wide logout can be added as a simple administrative action during implementation.

## D. Scoped audit events (MVP implementation of security requirements)

To reconcile the v1.0 exclusion of *general-purpose* audit logging with the approved security architecture, add a **narrow** `audit_events` table, not a comprehensive change-history platform:

| Column | PostgreSQL type | Rule |
|---|---|---|
| `id` | BIGINT GENERATED BY DEFAULT AS IDENTITY | Primary key |
| `actor_user_id` | INTEGER | Nullable FK → users; nullable for failed unknown-user logins |
| `event_type` | TEXT | Required, controlled event names |
| `resource_type` | TEXT | Nullable |
| `resource_id` | TEXT | Nullable |
| `outcome` | TEXT | Required: `Success` or `Failure` |
| `occurred_at` | TIMESTAMPTZ | Required, server assigned |
| `metadata` | JSONB | Nullable, sanitized non-secret details |

Record successful/failed login attempts, Owner voids and rejected void attempts, commission-rule changes, account/role changes, and historical manual back-entry/reconciliation actions. Void details already stored in Transactions remain authoritative. Do not log passwords, raw session tokens, payment secrets, or unnecessary personal data. Restrict edits/deletes and define retention during deployment; event writing must not accidentally commit an incomplete financial workflow.

## E. Sale idempotency (ADR-017)

Add `sale_idempotency` for backend-enforced duplicate prevention:

| Column | PostgreSQL type | Rule |
|---|---|---|
| `id` | BIGINT GENERATED BY DEFAULT AS IDENTITY | Primary key |
| `user_id` | INTEGER | Required FK → users |
| `idempotency_key` | TEXT | Required |
| `request_hash` | CHAR(64) | Required canonical request fingerprint |
| `transaction_id` | INTEGER | Nullable FK → transactions |
| `created_at` | TIMESTAMPTZ | Required |

Unique `(user_id, idempotency_key)`. On retry with identical request, return the original committed transaction; reject same key with different request content. Enforce uniqueness and concurrent-request safety within one coordinated database transaction. A retention/cleanup policy for keys can be set during implementation, but must not permit accidental duplicates from expected retries.

## F. Existing financial model preserved

Keep the original seven entities: `users`, `staff`, `commission_rules`, `services`, `products`, `transactions`, `transaction_items`. Keep their PK/FK, constraints, and commission snapshot strategy. For transaction items: exactly one service/product, service staff required, product staff optional, `business_share = selling_price - staff_commission`, with decimal arithmetic. GCash requires reference; Cash forbids it. Voids require reason, Owner actor, timestamp; do not delete financial history. Reports exclude voids from active totals, and Cashiers retain the daily operational reports already specified in `MVP Scope.md` (including today's Cash/GCash totals and staff commissions), but not Owner-only monthly reports/Business Share.

## G. Indexes and migration readiness

- Preserve original primary-key, username uniqueness, and `transactions.date_time` index.
- Add indexes on `transactions.business_date`, `transactions.recorded_by_user_id`, `auth_sessions.user_id`, `auth_sessions.token_hash` (unique), `audit_events.occurred_at`, and `sale_idempotency(user_id,idempotency_key)` (unique).
- SQLAlchemy 2.x models map to the approved physical schema; Alembic migrations are reviewed before application. For an empty new database, create a coherent initial migration representing v1.1; don't treat v1.0 as a previously deployed production schema.
- Use `NUMERIC` / Python Decimal for money and an explicit rounding policy. Validate all temporal conversions against `Asia/Manila`.

## H. Implementation-time choices (do not block starting development)

Decide exact HTTP endpoint shapes, audit retention, idempotency-key retention, manual logbook reference format, account-wide logout UI, and reconciliation UX during the relevant implementation tasks. Record decisions as they are made. No further architecture workshop is required to begin the MVP.

## Version note

**v1.1 (2026-10-14):** Consolidates ADR-020, ADR-021, ADR-022 and scoped audit/idempotency requirements with original v1.0 financial schema. Ready as the development baseline; constraints and migrations must be tested before real business use.
