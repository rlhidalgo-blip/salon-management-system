# MVP Scope

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | Minimum Viable Product Scope |
| Version | 1.0 |
| Status | Validated |
| Author | Rafael Hidalgo |
| Date Created | August 11, 2026 |
| Last Updated | August 11, 2026 |

## Purpose

This document defines the scope of the Minimum Viable Product (MVP) for the Salon Management System.

The MVP represents the smallest complete version of the product that can address the validated core operational problems of Yab's Hair and Beauty Studio and be tested in actual business operations.

This document establishes which capabilities are included in the initial release, which capabilities are intentionally excluded, and the conditions required for the MVP to be considered complete.

## MVP Objective

Deliver a functional internal web application that enables Yab's Hair and Beauty Studio to digitally record completed transactions, automatically calculate staff commissions and Business Share, track Cash and GCash payments, and generate accurate daily and monthly business reports.

The MVP should replace the core manual workflow currently performed using handwritten logbooks and calculator-based computations.

## In Scope

The following capabilities are included in the MVP.

### Authentication and Access Control

The MVP will support two authenticated user roles: Owner and Cashier.

#### Owner

The Owner will have access to:

- Daily reports
- Monthly reports
- Historical transactions
- Cash and GCash breakdowns
- Staff commission information
- Business Share information
- Staff management
- Service management
- Product management
- Price management
- Commission rule configuration
- Owner-controlled transaction voiding

#### Cashier

The Cashier will have access to:

- Transaction recording
- Today's recorded transactions
- Today's Cash and GCash totals
- Today's staff commission information
- Daily operational reporting

The Cashier will not have access to:

- Monthly business reports
- Monthly Business Share information
- Staff management
- Service management
- Product management
- Price configuration
- Commission rule configuration
- Transaction voiding

### Business Administration

The Owner will be able to manage:

- Staff members
- Services
- Products
- Prices
- Commission rules

Administrative changes shall apply to future transactions and shall not modify historical transaction records.

### Transaction Management

The MVP will allow the Cashier to:

- Record completed customer transactions
- Add multiple services and/or products to a transaction
- Assign exactly one barber or stylist to each service sale item
- Optionally assign a staff member to a product sale item
- Enter the final selling price for variable-price services
- Select Cash or GCash as the payment method
- Enter a GCash reference number when applicable

The system will:

- Automatically record transaction date and time
- Preserve completed transaction records
- Prevent direct editing or permanent deletion of completed transactions
- Allow the Owner to void incorrect completed transactions
- Require a reason when a transaction is voided
- Preserve the original voided transaction
- Clearly mark voided transactions as voided
- Record who voided the transaction and when
- Exclude voided transactions from active financial calculations
- Allow corrected information to be recorded through a new transaction

### Commission Management

The MVP will support:

- 50% staff / 50% Business Share for applicable haircut services
- 40% staff / 60% Business Share for applicable services using salon-owned products
- Fixed commission amounts for applicable product sales
- Product sales with no staff commission when no staff member is credited
- Automatic Staff Commission calculation
- Automatic Business Share calculation
- Preservation of historical commission values

### Payment Management

The MVP will support:

- Cash payments
- GCash payments
- Required GCash reference numbers for GCash transactions
- Preservation of payment information
- Cash and GCash totals for reporting and reconciliation

### Reporting

#### Owner Reporting

The Owner will have access to:

- Daily Sales Reports
- Monthly Sales Reports
- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Total Business Share
- Staff-level sales breakdowns
- Staff-level commission breakdowns
- Individual transaction details
- Historical transaction information

#### Cashier Reporting

The Cashier will have access to daily operational information including:

- Today's recorded transactions
- Today's Gross Sales
- Today's Cash Sales
- Today's GCash Sales
- Today's staff commission information

The Cashier will not have access to monthly business reports or monthly Business Share information.

## Out of Scope

The following capabilities will not be included in the MVP:

- Inventory management
- Appointment booking
- Customer accounts or profiles
- Customer loyalty or rewards programs
- Expense tracking
- Full payroll management
- Multi-branch management
- Native Android application
- Native iOS application
- AI-powered analytics
- Sales forecasting
- Advanced business intelligence
- Offline-first operation

These capabilities may be evaluated for future releases after the MVP has been deployed and validated in actual business operations.

## MVP Boundary

The MVP is considered focused on the following operational flow:

Customer completes service or product purchase
↓
Cashier receives payment
↓
Cashier records the completed transaction
↓
System records payment information
↓
System calculates applicable commissions
↓
System calculates Business Share
↓
Transaction contributes to daily and monthly reports
↓
Owner reviews business performance

## MVP Acceptance Summary

The MVP will be considered complete when:

- The Cashier can record the supported transaction scenarios without manual commission calculations.
- Cash and GCash payments are recorded and reconciled correctly.
- Commission and Business Share calculations follow the validated business rules.
- The Owner can access accurate daily and monthly reports.
- The Cashier can access the required daily operational information.
- The Owner can manage the business information required for normal operation.
- Incorrect completed transactions can be voided by the Owner without destroying historical records.
- Historical transactions remain accurate when prices or commission rules change.
- Core workflows have been tested with the Owner and Cashier.
- The application can operate reliably in the intended production environment.

Detailed release requirements are maintained in the Product Requirements Document.

## Scope Change Policy

New feature requests discovered during development will not automatically be added to the MVP.

A proposed scope change should be evaluated based on:

- Whether it is required to solve the validated core business problem
- Whether it is necessary for safe or correct operation
- Its impact on development complexity and delivery time
- Whether it can reasonably be deferred to a future release

If a new requirement materially affects the MVP, the relevant product documentation shall be updated before implementation.

Non-essential feature requests should be recorded as future considerations rather than immediately added to the MVP.

## Version History

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | August 11, 2026 | Rafael Hidalgo | Initial validated MVP Scope |

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| MVP-D-001 | The MVP will focus on transaction recording, commission calculation, payment tracking, business administration, and reporting | These capabilities directly address the validated operational problems of Yab's Hair and Beauty Studio |
| MVP-D-002 | The MVP will support only Owner and Cashier as authenticated user roles | These are the only direct system users required by the current business workflow |
| MVP-D-003 | The Cashier will have access to daily operational information but not monthly business reporting | The Cashier requires daily information to support operations, while broader business performance information is primarily required by the Owner |
| MVP-D-004 | The Owner will have exclusive access to business administration and transaction voiding | These actions can affect financial records and business configuration and therefore require greater control |
| MVP-D-005 | Completed transactions will be corrected through Owner-controlled voiding rather than direct editing or permanent deletion | This allows genuine recording errors to be corrected while preserving historical financial records |
| MVP-D-006 | Inventory, appointment booking, customer management, multi-branch support, native mobile applications, and AI-powered analytics are excluded from the MVP | These capabilities are not necessary to solve the validated core business problems and would increase development scope |
| MVP-D-007 | Offline-first operation is excluded from the MVP | The existing manual process can temporarily serve as a fallback during internet outages while the need for offline functionality is evaluated after deployment |