# User Stories

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | User Stories |
| Version | 1.0 |
| Status | Validated |
| Author | Rafael Hidalgo |
| Date Created | August 11, 2026 |
| Last Updated | August 11, 2026 |

## Purpose

This document translates the validated business requirements, product requirements, and MVP scope of the Salon Management System into actionable user stories.

Each user story describes a product capability from the perspective of the Owner or Cashier and includes acceptance criteria that define the conditions required for the story to be considered complete.

The stories in this document represent the functional behavior required for the MVP and will guide future design, development, and testing activities.

## Epic 1 — Transaction Management

### US-001 — Record a Completed Transaction

**As a** Cashier,  
**I want to** record a completed customer transaction,  
**so that** the sale is digitally preserved without relying on a handwritten logbook.

#### Acceptance Criteria

- The Cashier can start a new transaction.
- The transaction can contain one or more sale items.
- Required transaction information must be provided before submission.
- The system automatically records the transaction date and time.
- A successfully submitted transaction is preserved in the system.
- An active completed transaction contributes to applicable sales and reporting calculations.
- A voided transaction is excluded from active financial calculations.

---

### US-002 — Add Services to a Transaction

**As a** Cashier,  
**I want to** add one or more services to a customer transaction,  
**so that** all services purchased during the visit are recorded together.

#### Acceptance Criteria

- The Cashier can add a service to the transaction.
- Multiple services can be included in one transaction.
- Each service sale item requires exactly one assigned barber or stylist.
- The selling price for each service is recorded.
- Variable-price services allow the Cashier to enter the final agreed selling price.

---

### US-003 — Add Products to a Transaction

**As a** Cashier,  
**I want to** add products purchased by the customer to the transaction,  
**so that** product sales are included in the same business record.

#### Acceptance Criteria

- The Cashier can add a product to the transaction.
- Multiple products can be included in one transaction.
- Products can be recorded together with services.
- A product sale may be recorded with or without an assigned staff member.
- The product selling price is recorded.

---

### US-004 — Assign Staff to Sale Items

**As a** Cashier,  
**I want to** assign the appropriate barber or stylist to applicable sale items,  
**so that** staff sales and commissions are attributed correctly.

#### Acceptance Criteria

- Every service sale item requires exactly one assigned staff member.
- A product sale item may optionally have an assigned staff member.
- The selected staff assignment is preserved with the completed transaction.
- The assigned staff member is used when determining applicable commission.

---

### US-022 — Void an Incorrect Transaction

**As an** Owner,  
**I want to** void an incorrectly recorded completed transaction,  
**so that** financial records can be corrected without destroying the original transaction history.


#### Acceptance Criteria

- Only the Owner can void a completed transaction.
- The Owner must provide a reason before the transaction can be voided.
- The original transaction remains preserved.
- The transaction is clearly identified as voided.
- The system records who voided the transaction.
- The system records when the transaction was voided.
- A voided transaction does not contribute to active Gross Sales.
- A voided transaction does not contribute to Cash or GCash totals.
- A voided transaction does not contribute to Staff Commission.
- A voided transaction does not contribute to Business Share.
- The original transaction cannot be directly edited.
- Corrected information can be recorded through a new transaction.

---

## Epic 2 — Payment Management

### US-005 — Record Payment Method

**As a** Cashier,  
**I want to** record whether a transaction was paid through Cash or GCash,  
**so that** the business can accurately reconcile its payment channels.

#### Acceptance Criteria

- The Cashier must select a payment method before submitting the transaction.
- The available MVP payment methods are Cash and GCash.
- The selected payment method is preserved with the completed transaction.
- Cash transactions do not require a payment reference number.

### US-006 — Record GCash Reference Number

**As a** Cashier,  
**I want to** record the GCash reference number for a GCash transaction,  
**so that** the payment has a traceable reference for reconciliation and recordkeeping.

#### Acceptance Criteria

- Selecting GCash requires a reference number.
- A GCash transaction cannot be submitted without a reference number.
- The entered reference number is preserved with the transaction.
- Cash transactions do not require a GCash reference number.

---

## Epic 3 — Commission Management

### US-007 — Automatically Calculate Percentage-Based Commission


**As a** Cashier,  
**I want** staff commissions to be calculated automatically for percentage-based services,  
**so that** I do not need to manually calculate commissions using a calculator.

#### Acceptance Criteria

- The system automatically calculates the applicable staff commission when a percentage-based service is recorded.
- Haircut services use the configured 50% Staff Commission and 50% Business Share.
- Applicable services using salon-owned products use the configured 40% Staff Commission and 60% Business Share.
- The Cashier is not required to manually calculate the commission amount.
- The calculated Staff Commission and Business Share are stored with the completed transaction.
- Staff Commission plus Business Share equals the selling price of the applicable sale item.

---

### US-008 — Automatically Calculate Fixed Product Commission

**As a** Cashier,  
**I want** fixed product commissions to be calculated automatically when a product sale is credited to a staff member,  
**so that** product commissions do not need to be calculated manually.

#### Acceptance Criteria

- A product sale may use a configured fixed commission amount.
- When a product sale is credited to a staff member, the configured fixed commission is awarded to that staff member.
- The Business Share is automatically calculated as the selling price minus the fixed Staff Commission.
- The Cashier is not required to manually calculate the product commission.
- The calculated Staff Commission and Business Share are preserved with the completed transaction.

---

### US-009 — Handle Product Sales Without Staff Commission

**As a** Cashier,  
**I want to** record a product sale without assigning a staff member when no staff member is responsible for the sale,  
**so that** the transaction accurately reflects how the product was sold.

#### Acceptance Criteria

- A product sale can be recorded without an assigned staff member.
- No Staff Commission is generated when no staff member is credited.
- The Staff Commission for the sale item is ₱0.
- The full selling price is treated as Business Share.
- The transaction remains included in applicable sales and payment totals.

---

### US-010 — Preserve Historical Commission Values

**As an** Owner,  
**I want** completed transactions to retain the commission rules used at the time of sale,  
**so that** historical financial records remain accurate when commission rules change.

#### Acceptance Criteria

- Completed transactions preserve the commission type used at the time of sale.
- Completed transactions preserve the percentage or fixed commission value used at the time of sale.
- Completed transactions preserve the calculated Staff Commission.
- Completed transactions preserve the calculated Business Share.
- Changing a commission rule does not recalculate previously completed transactions.

## Epic 4 — Reporting

### US-011 — View Daily Sales Report

**As an** Owner,  
**I want to** view a daily sales report,  
**so that** I can understand the business's performance for a selected day without manually calculating transactions.

#### Acceptance Criteria

- The Owner can access a Daily Sales Report.
- The report displays Gross Sales for the selected day.
- The report displays total Cash Sales.
- The report displays total GCash Sales.
- The report displays total Staff Commission.
- The report displays total Business Share.
- The report displays the number of active recorded transactions.
- Voided transactions do not contribute to active financial totals.
- Cash Sales plus GCash Sales equals Gross Sales.
- Staff Commission plus Business Share equals Gross Sales.

---

### US-012 — View Monthly Sales Report

**As an** Owner,  
**I want to** view a monthly sales report,  
**so that** I can understand monthly business performance without manually calculating daily records.

#### Acceptance Criteria

- The Owner can access a Monthly Sales Report.
- The Owner can view Gross Sales for the selected month.
- The report displays total Cash Sales.
- The report displays total GCash Sales.
- The report displays total Staff Commission.
- The report displays total Business Share.
- The report is generated from recorded transaction data.
- Voided transactions do not contribute to active monthly financial totals.
- The Cashier cannot access the Monthly Sales Report.
- Cash Sales plus GCash Sales equals Gross Sales.
- Staff Commission plus Business Share equals Gross Sales.

---

### US-013 — View Staff Sales and Commission Breakdown

**As an** Owner,  
**I want to** view sales and commission information for each barber or stylist,  
**so that** I can understand how much each staff member generated and earned.

#### Acceptance Criteria

- The report identifies each applicable staff member.
- The report displays the sales generated by each staff member.
- The report displays the commission earned by each staff member.
- Staff totals are calculated from active recorded transactions.
- Voided transactions do not contribute to staff sales or commission totals.

---

### US-014 — Review Transactions Behind a Report

**As an** Owner,  
**I want to** access the transactions associated with a report,  
**so that** I can investigate the records behind reported financial totals when necessary.

#### Acceptance Criteria

- The Owner can access the transactions associated with the selected reporting period.
- The transaction list is separate from the primary report summary.
- Each transaction in the list displays enough information to identify the transaction.
- The Owner can access the full details of an individual transaction.
- Individual transaction details include:
  - Transaction date and time
  - Services and/or products
  - Applicable staff assignments
  - Selling prices
  - Payment method
  - GCash reference number, when applicable
  - Staff Commission
  - Business Share
  - Transaction status
- Voided transactions are clearly identified as voided.

---

### US-015 — View Daily Operational Information

**As a** Cashier,  
**I want to** view today's operational sales information,  
**so that** I can monitor the transactions and payment totals recorded during the current business day.

#### Acceptance Criteria

- The Cashier can view today's recorded transactions.
- The Cashier can view today's Gross Sales.
- The Cashier can view today's Cash Sales.
- The Cashier can view today's GCash Sales.
- The Cashier can view today's staff commission information.
- Voided transactions do not contribute to active daily totals.
- The Cashier cannot access monthly business reports.

---

## Epic 5 — Business Administration

### US-016 — Manage Staff Members

**As an** Owner,  
**I want to** manage staff members,  
**so that** the system maintains the barbers and stylists who can be associated with applicable sales.

#### Acceptance Criteria

- The Owner can add a staff member.
- The Owner can view existing staff members.
- Staff records contain the information required for transaction assignment.
- Staff members can be made unavailable for future transaction assignment without altering historical transactions.
- Existing transactions preserve their original staff information.
- The Cashier cannot manage staff members.

---

### US-017 — Manage Services

**As an** Owner,  
**I want to** manage the services offered by the business,  
**so that** the Cashier can select the appropriate service when recording a transaction.

#### Acceptance Criteria

- The Owner can add a service.
- The Owner can view existing services.
- A service can have a configured selling price.
- A service can support variable pricing when applicable.
- Services can be made unavailable for future transactions without affecting historical transactions.
- The Cashier cannot manage service configuration.

---

### US-018 — Manage Products

**As an** Owner,  
**I want to** manage products sold by the business,  
**so that** product sales can be recorded correctly.

#### Acceptance Criteria

- The Owner can add a product.
- The Owner can view existing products.
- A product has a configured selling price.
- Applicable product commission information can be associated with the product.
- Products can be made unavailable for future transactions without affecting historical transactions.
- The Cashier cannot manage product configuration.

---

### US-019 — Manage Commission Rules

**As an** Owner,  
**I want to** manage commission rules,  
**so that** the system calculates Staff Commission and Business Share according to the current business agreement.

#### Acceptance Criteria

- The Owner can configure applicable percentage-based commission rules.
- The Owner can configure applicable fixed-amount product commissions.
- Commission values are validated before they are saved.
- Updated commission rules apply only to future transactions.
- Updating a commission rule does not modify historical transaction calculations.
- The Cashier cannot configure commission rules.

## Epic 6 — Authentication and Access Control

### US-020 — Log In to the System

**As an** authorized user,  
**I want to** securely log in to the Salon Management System,  
**so that** I can access the capabilities available to my role.

#### Acceptance Criteria

- Authorized Owner and Cashier users can log in using valid credentials.
- Invalid credentials do not grant access.
- Unauthenticated users cannot access protected application functionality.
- Successful authentication identifies the user's role.
- The user receives access only to capabilities permitted for that role.

---

### US-021 — Enforce Role-Based Access

**As an** Owner,  
**I want** system capabilities to be restricted according to user role,  
**so that** sensitive business and administrative functionality is only available to authorized users.

#### Acceptance Criteria

- Owner-only functionality cannot be accessed by the Cashier.
- The Owner can access monthly reporting.
- The Owner can access business administration.
- The Owner can void incorrect completed transactions.
- The Cashier can access transaction-recording functionality.
- The Cashier can access permitted daily operational information.
- The Cashier cannot access monthly business reporting.
- The Cashier cannot configure staff, services, products, prices, or commission rules.
- The Cashier cannot void completed transactions.

## Story Priority and Traceability

The following table summarizes the MVP priority of each user story and provides traceability to the validated product capabilities and business requirements.

Priority definitions:

- **Must Have** — Required for the MVP to solve the validated core business problem or operate safely and correctly.
- **Should Have** — Important to the MVP experience but not as critical as the core operational workflow.
- **Could Have** — Valuable but may be deferred without preventing the MVP from solving its primary problem.

| Story ID | User Story | Epic | Priority | Related BRS Requirements |
|---|---|---|---|---|
| US-001 | Record a Completed Transaction | Transaction Management | Must Have | FR-003, FR-004, FR-008 |
| US-002 | Add Services to a Transaction | Transaction Management | Must Have | FR-004, FR-005, FR-006 |
| US-003 | Add Products to a Transaction | Transaction Management | Must Have | FR-004, FR-005 |
| US-004 | Assign Staff to Sale Items | Transaction Management | Must Have | FR-005 |
| US-005 | Record Payment Method | Payment Management | Must Have | FR-015, FR-016, FR-019 |
| US-006 | Record GCash Reference Number | Payment Management | Must Have | FR-017, FR-018, FR-019 |
| US-007 | Automatically Calculate Percentage-Based Commission | Commission Management | Must Have | FR-009, FR-010, FR-012, FR-013 |
| US-008 | Automatically Calculate Fixed Product Commission | Commission Management | Must Have | FR-009, FR-011, FR-012, FR-013 |
| US-009 | Handle Product Sales Without Staff Commission | Commission Management | Must Have | FR-005, FR-012 |
| US-010 | Preserve Historical Commission Values | Commission Management | Must Have | FR-013, FR-014 |
| US-011 | View Daily Sales Report | Reporting | Must Have | FR-024, FR-026–FR-031, FR-035, FR-036 |
| US-012 | View Monthly Sales Report | Reporting | Must Have | FR-025, FR-026, FR-028–FR-032, FR-035, FR-036 |
| US-013 | View Staff Sales and Commission Breakdown | Reporting | Must Have | FR-031, FR-032 |
| US-014 | Review Transactions Behind a Report | Reporting | Must Have | FR-033, FR-034 |
| US-015 | View Daily Operational Information | Reporting | Must Have | FR-024, FR-026–FR-031 |
| US-016 | Manage Staff Members | Business Administration | Must Have | FR-020 |
| US-017 | Manage Services | Business Administration | Must Have | FR-021 |
| US-018 | Manage Products | Business Administration | Must Have | FR-022 |
| US-019 | Manage Commission Rules | Business Administration | Must Have | FR-023 |
| US-020 | Log In to the System | Authentication & Access | Must Have | FR-001, FR-002 |
| US-021 | Enforce Role-Based Access | Authentication & Access | Must Have | FR-001, FR-002 |
| US-022 | Void an Incorrect Transaction | Transaction Management | Must Have | FR-037, FR-038 |

## Version History

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | August 11, 2026 | Rafael Hidalgo | Initial Validated User Stories for the MVP |

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| US-D-001 | User stories are organized around six core product Epics | Aligns the development backlog with the validated core product capabilities |
| US-D-002 | Acceptance criteria define observable product behavior rather than detailed UI implementation | Preserves flexibility for later UX and technical design decisions |
| US-D-003 | Detailed transaction access is required in the MVP | Financial report totals must remain traceable to their underlying transaction records |
| US-D-004 | Completed transaction correction is represented through an Owner-controlled voiding story | Preserves historical financial integrity while supporting correction of recording errors |