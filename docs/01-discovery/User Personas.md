# User Personas

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | User Personas |
| Version | 1.0 |
| Status | Validated |
| Author | Rafael Hidalgo |
| Date Created | August 8, 2026 |
| Last Updated | August 8, 2026 |

---

## Purpose

This document defines the primary users of the Salon Management System based on the current operations of Yab's Hair and Beauty Studio.

The personas focus on user responsibilities, goals, pain points, behaviors, and product needs that directly influence product decisions.

The system has two primary users:

- Business Owner
- Cashier

Barbers and stylists are stakeholders in the system but are not direct system users in the MVP.

---

# Persona 1 — Business Owner

## Profile

The Business Owner oversees the operations and financial performance of Yab's Hair and Beauty Studio.

The owner currently relies on handwritten logbooks and manually prepared sales information to understand the performance of the business.

The owner is not highly comfortable with technology but is willing to adapt to a more capable digital system if it provides meaningful improvements to business operations.

## Primary Goals

- Know the total sales generated each day.
- Know the Business Share after staff commissions.
- Know how much of the day's sales were received through Cash.
- Know how much of the day's sales were received through GCash.
- Monitor monthly sales performance.
- Review staff commissions.
- Access reliable historical business records.
- Reduce dependence on handwritten logbooks.

## Current Responsibilities

- Review daily sales.
- Review business earnings after staff commissions.
- Monitor Cash and GCash sales.
- Review the physical logbook.
- Monitor monthly business performance.
- Oversee services, products, staff, and commission rules.

## Pain Points

- Handwritten records can be difficult to read because of handwriting and erasures.
- Daily information requires reviewing physical records.
- Monthly sales are difficult and time-consuming to calculate.
- Manual calculations increase the possibility of errors.
- Historical business information is difficult to retrieve and analyze.

## Product Needs

The owner needs a system that:

- Provides an immediate overview of daily business performance.
- Automatically calculates the Business Share.
- Separates Cash and GCash sales.
- Provides daily and monthly reports.
- Provides staff commission breakdowns.
- Maintains organized historical records.
- Allows management of staff, services, products, and commission rules.
- Can be accessed through a web browser.
- Remains understandable without unnecessarily limiting functionality.

## Usage Context

The owner may primarily use the system inside the salon but would benefit from the ability to access business information from other locations when needed.

The owner is expected to interact primarily with reporting and administrative features rather than transaction entry.

## Typical Scenario

At the end of the day, the owner opens the system and reviews the Daily Sales Report.

The owner can immediately see:

- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Business Share
- Commission breakdown by staff member
- Individual transactions

At the end of the month, the owner can review the Monthly Sales Report without manually calculating totals from the physical logbook.

---

# Persona 2 — Cashier

## Profile

The Cashier is responsible for recording completed customer transactions and supporting the daily sales-closing process.

The cashier is comfortable using computers and web applications. The primary challenge is not technology usage but the repetitive manual work involved in recording transactions, calculating commissions, and preparing daily totals.

## Primary Goals

- Record completed transactions quickly.
- Record the correct service or product.
- Record the correct selling price.
- Record whether payment was made through Cash or GCash.
- Record GCash reference numbers when applicable.
- Ensure the correct barber or stylist receives commission.
- Avoid manual commission calculations.
- Reduce mistakes during daily closing.
- View accurate daily sales information.

## Current Responsibilities

When a customer completes payment, the cashier:

1. Receives the customer's payment.
2. Records the transaction manually in the logbook.
3. Records the service and selling price.
4. Records the applicable barber or stylist.
5. Records the payment method.
6. For GCash payments, records the reference number and may keep a picture of the customer's payment receipt.
7. Manually calculates staff commissions.
8. Manually calculates daily sales totals.

## Pain Points

- Manually calculating commissions is time-consuming.
- Manually calculating daily sales creates confusion.
- Calculator-based computation increases the possibility of arithmetic errors.
- Multiple services and product purchases make transactions more difficult to track manually.
- Recording GCash information requires additional manual recordkeeping.
- Handwritten records may contain erasures or become difficult to interpret later.

## Product Needs

The cashier needs a system that:

- Makes transaction entry fast and straightforward.
- Automatically records transaction date and time.
- Supports multiple services and products within a transaction.
- Allows the correct staff member to be assigned to applicable sale items.
- Supports Cash and GCash payments.
- Requires a GCash reference number when applicable.
- Automatically calculates staff commissions.
- Automatically calculates the Business Share.
- Automatically contributes recorded transactions to daily and monthly reports.
- Minimizes unnecessary manual calculations.

## Usage Context

The cashier will primarily use the system during salon operating hours.

Because the cashier is comfortable with computers and web applications, the interface can support efficient digital workflows while still prioritizing speed, clarity, and error prevention.

## Typical Scenario

A customer completes a haircut and purchases hair wax.

The cashier creates a transaction, records the haircut, assigns the barber, adds the hair wax, and selects the customer's payment method.

If the customer pays through GCash, the cashier enters the GCash reference number.

The system automatically:

- Records the transaction date and time.
- Calculates the barber's haircut commission.
- Calculates any applicable product commission.
- Calculates the Business Share.
- Adds the transaction to the Daily Sales Report.

The cashier does not need to manually calculate the commission or daily sales total.

---

# Key Product Implications

The user research produces several implications for product design.

### 1. Reporting is a core owner workflow

The owner requires immediate visibility into:

- Gross Sales
- Cash Sales
- GCash Sales
- Staff Commissions
- Business Share
- Daily performance
- Monthly performance

Reporting should therefore be treated as a core product capability rather than a secondary feature.

### 2. Transaction speed is a core cashier requirement

The cashier performs transaction recording repeatedly throughout the business day.

The sales workflow should minimize unnecessary steps and manual calculations.

### 3. Automation should replace repetitive calculations

Commission calculations, Business Share calculations, and report totals should be automatically generated by the system.

### 4. The system must prioritize clarity

The owner has lower technology comfort than the cashier.

The system should therefore use understandable terminology, clear navigation, and predictable workflows without unnecessarily restricting functionality.

### 5. Payment reconciliation is important

Cash and GCash must remain clearly distinguishable in transaction records and reports.

GCash reference numbers should provide additional traceability for reconciliation.

### 6. Historical information must be easy to retrieve

The difficulty of obtaining monthly information from physical logbooks demonstrates the need for searchable and structured historical records.

---

# Validation

These personas were developed based on the existing workflow and requirements of Yab's Hair and Beauty Studio and represent the two direct users of the MVP.