# MVP Scope

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | Minimum Viable Product Scope |
| Version | 1.0 |
| Status | Draft |
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

### Authentication

- Owner login
- Cashier login
- Role-based access
- Protection of business information

### Business Administration

The Owner can manage:

- Staff members
- Services
- Products
- Prices
- Commission rules

### Transaction Management

The Cashier can:

- Record completed transactions
- Add multiple services and/or products to a transaction
- Assign a barber or stylist to service sale items
- Optionally assign staff to product sale items
- Enter variable service prices when applicable
- Select the payment method
- Record GCash reference numbers when applicable

The system will:

- Automatically record transaction date and time
- Preserve completed transaction records
- Prevent the Cashier from editing or deleting completed transactions

### Transaction Correction

Completed transactions shall remain immutable and cannot be directly edited or deleted.

If an incorrect transaction is recorded:

- The Cashier shall not be allowed to modify or void the transaction.
- The Owner shall be allowed to void an incorrect transaction.
- Voiding a transaction shall require a reason.
- The original transaction shall remain preserved in the system.
- A voided transaction shall be clearly marked as voided.
- Voided transactions shall not contribute to active sales totals, staff commissions, Cash/GCash totals, or Business Share calculations.
- The system shall preserve who voided the transaction and when it was voided.
- If necessary, the correct transaction shall be recorded as a new transaction.

### Commission Management

The system will support:

- Percentage-based commissions
- Fixed product commissions
- Automatic Staff Commission calculation
- Automatic Business Share calculation
- Product sales without staff commission
- Preservation of historical commission values

### Payment Management

The system will support:

- Cash
- GCash
- Required GCash reference numbers
- Payment-method preservation
- Cash and GCash reporting

### Reporting

The system will provide:

- Daily Sales Report
- Monthly Sales Report
- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Total Business Share
- Staff-level sales breakdown
- Staff-level commission breakdown
- Individual transaction details

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

### Authentication and Access Control

The MVP will support two authenticated user roles:

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
- Service and product configuration
- Price configuration
- Commission rule configuration