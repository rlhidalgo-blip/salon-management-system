# Product Roadmap

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | Product Roadmap |
| Version | 1.0 |
| Status | Validated |
| Author | Rafael Hidalgo |
| Date Created | August 11, 2026 |
| Last Updated | August 12, 2026 |

## Purpose

This document defines the planned development sequence for the MVP of the Salon Management System.

The roadmap translates the validated MVP scope and user stories into implementation phases based on product value, technical dependencies, risk, and the need to validate core business workflows progressively.

The roadmap defines the intended sequence of development rather than fixed delivery dates. Development timing may change as technical complexity and implementation risks become better understood.

## Roadmap Strategy

Development will follow a dependency-driven approach.

The system will first establish the technical and administrative foundations required by later workflows. Development will then progress toward the primary business value of the product: transaction recording, automated commission calculation, payment tracking, and reporting.

Each phase should produce functionality that can be tested before dependent capabilities are developed.

The planned progression is:

Foundation
↓
Business Configuration
↓
Transaction Workflow
↓
Commission and Payment Logic
↓
Reporting
↓
Transaction Correction
↓
System Validation
↓
Deployment

## Phase 1 — Foundation and Access Control

### Objective

Establish the core application foundation and secure access for authorized users.

### User Stories

- US-020 — Log In to the System
- US-021 — Enforce Role-Based Access

### Key Outcomes

- Owner and Cashier can authenticate.
- Unauthorized users cannot access protected functionality.
- The application recognizes Owner and Cashier roles.
- Role-based access restrictions are established.

### Why This Comes First

Later functionality depends on knowing who is using the system and what capabilities they are authorized to access.

## Phase 2 — Business Configuration

### Objective

Enable the Owner to configure the operational data required for transaction recording and commission calculation.

### User Stories

- US-016 — Manage Staff Members
- US-017 — Manage Services
- US-018 — Manage Products
- US-019 — Manage Commission Rules

### Key Outcomes

The Owner can configure:

- Staff members
- Services
- Products
- Selling prices
- Variable-price services
- Percentage-based commission rules
- Fixed product commissions

Historical integrity must be preserved when configuration changes.

### Why This Comes Before Transactions

Transaction recording depends on existing staff, services, products, prices, and commission rules.

## Phase 3 — Core Transaction Workflow

### Objective

Replace handwritten transaction recording with a structured digital workflow.

### User Stories

- US-001 — Record a Completed Transaction
- US-002 — Add Services to a Transaction
- US-003 — Add Products to a Transaction
- US-004 — Assign Staff to Sale Items

### Key Outcomes

The Cashier can:

- Start a transaction
- Add multiple services
- Add multiple products
- Assign staff where applicable
- Enter variable selling prices
- Submit a completed transaction

The system automatically records the transaction date and time and preserves the completed record.

## Phase 4 — Payment and Commission Processing

### Objective

Automate payment recording and financial distribution for completed transactions.

### User Stories

- US-005 — Record Payment Method
- US-006 — Record GCash Reference Number
- US-007 — Automatically Calculate Percentage-Based Commission
- US-008 — Automatically Calculate Fixed Product Commission
- US-009 — Handle Product Sales Without Staff Commission
- US-010 — Preserve Historical Commission Values

### Key Outcomes

The system can:

- Record Cash payments
- Record GCash payments
- Require GCash reference numbers
- Calculate percentage-based Staff Commission
- Calculate fixed product commissions
- Handle products without staff commission
- Calculate Business Share
- Preserve historical commission values

### Financial Integrity

For applicable active sales:

Cash Sales + GCash Sales = Gross Sales

Staff Commission + Business Share = Gross Sales

### Validation Focus

Commission and payment calculations must be tested against representative business scenarios before reporting functionality relies on them.

## Phase 5 — Reporting and Business Visibility

### Objective

Transform recorded transaction data into useful operational and business information.

### User Stories

- US-011 — View Daily Sales Report
- US-012 — View Monthly Sales Report
- US-013 — View Staff Sales and Commission Breakdown
- US-014 — Review Transactions Behind a Report
- US-015 — View Daily Operational Information

### Key Outcomes

The Owner can access:

- Daily business performance
- Monthly business performance
- Gross Sales
- Cash and GCash totals
- Staff Commission
- Business Share
- Staff-level breakdowns
- Underlying transaction records

The Cashier can access permitted daily operational information without gaining access to restricted monthly business reporting.

### Reporting Principle

Reports should present summary information first while allowing detailed transaction information to be accessed when needed.

## Phase 6 — Transaction Correction and Auditability

### Objective

Allow genuine recording errors to be corrected without destroying historical financial records.

### User Stories

- US-022 — Void an Incorrect Transaction

### Key Outcomes

- Only the Owner can void completed transactions.
- A void reason is required.
- The original transaction remains preserved.
- The system records who performed the void and when.
- Voided transactions are clearly identified.
- Voided transactions are excluded from active financial calculations.
- Corrected information can be recorded through a new transaction.
- After transaction correction is implemented, reporting calculations shall be revalidated to ensure voided transactions are excluded from all applicable daily, monthly, payment, commission, and Business Share totals.

## Phase 7 — System Validation

### Objective

Validate that the complete MVP operates correctly across realistic business scenarios.

### Validation Areas

- Authentication and authorization
- Business configuration
- Service transactions
- Product transactions
- Mixed service and product transactions
- Variable pricing
- Cash payments
- GCash payments
- Percentage commissions
- Fixed commissions
- Product sales without staff commission
- Daily reporting
- Monthly reporting
- Transaction voiding
- Historical data preservation
- Financial reconciliation

### User Validation

The Owner and Cashier should test the workflows they will perform during actual salon operations.

Critical financial, security, or data-integrity defects must be resolved before deployment.

## Phase 8 — Deployment and MVP Launch

### Objective

Prepare and release the validated MVP for actual use at Yab's Hair and Beauty Studio.

### Key Outcomes

- Production application deployed
- Production database configured
- Environment variables and credentials secured
- Backup and recovery procedures documented
- Owner and Cashier accounts prepared
- Core production workflows verified
- Initial real-world usage begins

### Post-Launch Focus

After deployment, the product should be observed in actual business operations.

Feedback and operational measurements should be collected before expanding the product scope.

## Roadmap Overview

| Phase | Focus | Primary Stories |
|---|---|---|
| 1 | Foundation & Access | US-020, US-021 |
| 2 | Business Configuration | US-016–US-019 |
| 3 | Core Transaction Workflow | US-001–US-004 |
| 4 | Payment & Commission Processing | US-005–US-010 |
| 5 | Reporting & Business Visibility | US-011–US-015 |
| 6 | Transaction Correction | US-022 |
| 7 | System Validation | All MVP stories |
| 8 | Deployment & MVP Launch | Validated MVP |

## Roadmap Dependencies

The development phases have dependencies that influence their intended sequence.

- Foundation and Access Control must be established before role-restricted functionality is implemented.
- Business Configuration must provide the staff, services, products, prices, and commission rules required by transaction recording.
- Core Transaction Workflow must be functional before payment and commission processing can be fully validated.
- Payment and commission calculations must be reliable before financial reports are built on top of them.
- Reporting depends on accurate and persistent transaction data.
- Transaction Correction depends on completed transactions and reporting calculations that can correctly exclude voided records.
- System Validation depends on the completion and integration of all MVP capabilities.
- Deployment shall occur only after critical business, financial, security, and data-integrity workflows have been validated.

## Roadmap Risks

The following factors may affect the planned development sequence:

- Unexpected technical complexity
- Changes to validated business requirements
- Database or data-model redesign
- Errors discovered in commission or financial calculations
- Integration issues between transaction, payment, commission, and reporting functionality
- Usability issues identified during Owner or Cashier validation

If a significant issue affects a dependent phase, the affected functionality should be corrected and validated before development continues to rely on it.

Detailed product risks and mitigations are maintained in the Product Requirements Document.

## Roadmap Change Policy

The roadmap may be adjusted as implementation provides new information about technical complexity, dependencies, risks, or validated business requirements.

Changes to development sequence should be based on:

- Technical dependencies
- Product risk
- Business priority
- Validation findings
- Development complexity

Changes to the roadmap do not automatically change the MVP scope.

Any proposed feature that expands the MVP must first be evaluated according to the Scope Change Policy defined in the MVP Scope document.

## Version History

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | August 12, 2026 | Rafael Hidalgo | Initial validated Product Roadmap for the MVP |

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| RM-D-001 | Development will follow a dependency-driven sequence rather than fixed calendar dates | Technical complexity is not yet sufficiently understood to create reliable delivery estimates |
| RM-D-002 | Authentication and business configuration will be established before the primary transaction workflow | Later functionality depends on authorized users and configured operational data |
| RM-D-003 | Payment and commission processing will be validated before reporting | Reports must rely on accurate financial data and calculations |
| RM-D-004 | Transaction correction will be implemented after the primary transaction and reporting workflows | The core successful transaction path should be established before introducing correction behavior |
| RM-D-005 | System validation will occur before production deployment | Critical financial, security, usability, and data-integrity issues must be resolved before real business use |
| RM-D-006 | Fixed development dates will not be assigned during initial planning | Development estimates will become more reliable after technical design clarifies implementation complexity |



