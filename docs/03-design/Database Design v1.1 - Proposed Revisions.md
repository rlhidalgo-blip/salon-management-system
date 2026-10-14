## Proposed Revision: Calendar-Day-Based Cashier Access

### 1. Purpose

This revision defines the data and authorization requirements for calendar-day-based cashier transaction access in Yab's Salon Management System.

The objective is to support shared cashier operations without introducing a separate shift-management module for the MVP.

### 2. Business Day Definition

For the MVP, one salon business day corresponds to one calendar date in the `Asia/Manila` timezone.

The business day begins at 12:00 AM and ends immediately before 12:00 AM on the following calendar date.

All authorized Cashiers share the same business-day transaction visibility.

The MVP will not implement separate shift opening, shift closing, or scheduled cashier assignments.

### 3. Proposed Data Model

The existing Transactions entity will remain the primary record of salon sales.

A dedicated `business_date` field of type `DATE` is proposed to identify the salon business day associated with each transaction.

The system must also preserve the distinction between the original transaction occurrence timestamp and the timestamp when the transaction record was created.

The exact column names and constraints will be reconciled against Database Design v1.0 before implementation.

### 4. Authorization Rules

The FastAPI backend must enforce the following rules:

- Owners may view current and historical transactions.
- Cashiers may view transactions assigned to the current salon business date.
- Cashiers may view transactions recorded by other authorized Cashiers on that same business date.
- Cashiers may not retrieve transactions assigned to previous or future business dates through ordinary transaction-history operations.
- Transaction visibility must be enforced by backend authorization and query filtering.
- Transaction voiding remains restricted to authenticated Owners.

### 5. Historical and Manual Transaction Entry

Transactions entered after an internet outage must preserve their original occurrence timestamp.

The system must distinguish between transaction occurrence time and system entry time.

Manually encoded transactions must include sufficient provenance information to support reconciliation and duplicate-entry prevention.

Historical back-entry must not automatically grant Cashiers unrestricted access to previous-day transaction history.

### 6. Architectural Constraints

The MVP will not introduce a dedicated Shifts entity.

Business-day calculations must use the `Asia/Manila` timezone.

The backend must derive or validate business-date assignments and must not trust arbitrary client-submitted dates.

If the salon later requires separate cashier shifts, overnight operations, or multiple branches, this design must be reviewed.

### 7. Design Decision

**ADR-020: Calendar-Day-Based Cashier Transaction Access**

**Status:** Approved — Database Schema Revision Pending

**Decision:** Define cashier transaction visibility using the current salon calendar date rather than explicit shift entities or cashier schedules.

**Rationale:** This approach reduces implementation complexity while supporting shared cashier operations for the MVP.

**Tradeoff:** The model does not distinguish between separate shifts within the same day. Strict midnight boundaries may also limit late-night transaction reconciliation.

**Implementation Considerations:** The Transactions schema must be reviewed for business-date representation, timestamp consistency, manual back-entry support, and appropriate database indexing.

## Proposed Revision 2: Owner-Only Historical Manual Transaction Entry

### 1. Purpose

This revision defines the data requirements, authorization rules, and reconciliation procedures for manually recorded salon transactions entered into the system after their original business date.

The objective is to preserve accurate historical sales and financial records while restricting sensitive historical data entry to the Owner.

### 2. Business Rule

Only authenticated users with the Owner role may encode and reconcile manual transactions belonging to previous business dates.

Cashiers may continue recording authorized current-day sales but must not submit transactions with an earlier business date through ordinary sales operations.

The FastAPI backend must enforce these restrictions independently of frontend controls.

### 3. Proposed Transaction Metadata

The existing Transactions entity will remain the primary record of sales.

The following logical attributes are proposed for review:

| Attribute | Proposed Type | Description |
|---|---|---|
| Transaction Occurrence Time | TIMESTAMPTZ | Original date and time of the sale |
| Record Creation Time | TIMESTAMPTZ | Date and time the record was persisted |
| Business Date | DATE | Salon business date derived using Asia/Manila |
| Entry Source | VARCHAR / Enum | Direct entry or manual back-entry |
| Manual Reference | VARCHAR, nullable | Identifier of the original paper record |
| Recorded By | Foreign Key to Users | User responsible for encoding the transaction |

These attributes must be reconciled against existing Database Design v1.0 fields to prevent redundant columns and preserve established relationships.

### 4. Authorization Requirements

The backend must enforce the following rules:

1. Owners may record current-day transactions.
2. Cashiers may record authorized current-day transactions.
3. Owners may encode manual transactions from previous business dates.
4. Cashiers may not encode previous-day transactions.
5. Owners may review and reconcile historical manual entries.
6. Cashiers may not access unrestricted historical transaction records.
7. All financial operations must comply with the existing transaction integrity and void authorization rules.

### 5. Historical Transaction Processing

For manual back-entry, the Owner must provide the original sale information, including the occurrence date and time, relevant services or products, quantities, staff assignments, and actual amounts.

The backend must validate the supplied information and assign the appropriate business date using the salon's configured timezone.

The backend must independently record the system entry timestamp and authenticated user responsible for encoding the transaction.

Historical transaction values must be preserved as snapshots.

Applicable historical commission calculations must follow the approved commission policy.

### 6. Duplicate Prevention and Reconciliation

Manual back-entry must require a traceable manual reference.

The system must prevent duplicate use of manual references within the approved reference scope.

Historical manual entries must be identifiable for reconciliation.

Reconciliation must compare encoded transactions against the original paper records and available payment information.

Discrepancies must be investigated and resolved through authorized procedures without silently overwriting historical financial records.

### 7. Security and Auditability

Historical back-entry is an Owner-restricted financial operation.

The system must validate the active Owner session and enforce appropriate authorization and CSRF protections.

The system must record sufficient information to identify who performed the back-entry, when it occurred, and which original business date was affected.

Sensitive financial changes must be auditable.

### 8. Architecture Decision

**ADR-021: Owner-Only Historical Manual Transaction Back-Entry**

**Status:** Approved — Database Schema Revision Pending

**Decision:** Restrict the encoding and reconciliation of previous-day manual transactions to authenticated Owners.

**Rationale:** This approach protects historical financial records while maintaining a practical manual fallback process during internet outages.

**Tradeoff:** Previous-day transaction encoding depends on Owner availability and may delay reconciliation.

**Implementation Considerations:** The Transactions schema must support original occurrence timestamps, system entry timestamps, business dates, entry provenance, manual references, and responsible-user attribution.

### 9. Pending Detailed Design Decisions

- Exact mapping to existing Database Design v1.0 columns.
- Same-day manual back-entry authorization.
- Historical commission-rule selection.
- Manual reference uniqueness scope.
- Reconciliation status and completion procedure.

### 4. Authorization Requirements

The system will enforce role-based and business-date-based authorization for manual transaction entry.

The following rules apply:

1. Owners and Cashiers may record current-day transactions.
2. Owners and Cashiers may encode manually recorded transactions whose original business date matches the current salon business date.
3. Only Owners may encode manually recorded transactions belonging to previous business dates.
4. Cashiers must not encode transactions assigned to previous or future business dates.
5. Only Owners may perform historical manual transaction reconciliation.
6. Cashiers may view all transactions assigned to the current salon business date but may not access unrestricted historical transaction records.
7. Transaction voiding remains restricted to authenticated Owners.

The FastAPI backend must enforce these rules independently of frontend controls.

Business-date comparisons must use the `Asia/Manila` timezone and a trusted server-side clock.

The backend must validate the supplied occurrence timestamp and derive the corresponding business date.

The system must preserve the actual transaction occurrence timestamp separately from the timestamp when the transaction was entered into the application.

### 8. Architecture Decision

**ADR-021: Business-Date-Based Manual Transaction Entry Authorization**

**Status:** Approved — Database Schema Revision Pending

**Decision:** Allow authenticated Owners and Cashiers to encode same-day manually recorded transactions. Restrict previous-day manual transaction entry and historical reconciliation to authenticated Owners.

**Rationale:** This approach allows Cashiers to recover from short internet outages without unnecessarily delaying daily operations, while maintaining stronger controls over historical financial records.

**Tradeoff:** Manual transactions not encoded before the salon business date changes will require Owner intervention.

**Implementation Considerations:** The backend must enforce business-date restrictions, preserve transaction occurrence and entry timestamps, record the responsible user, and prevent duplicate manual entries.

### 9. Pending Detailed Design Decisions

- Exact mapping to existing Database Design v1.0 columns.
- Historical commission-rule selection.
- Manual reference uniqueness scope.
- Reconciliation status and completion procedure.