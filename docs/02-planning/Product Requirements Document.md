# Product Requirements Document (PRD)

## Document Information

| Field | Value |
|---|---|
| Project | Salon Management System |
| Client | Yab's Hair and Beauty Studio |
| Document | Product Requirements Document |
| Version | 1.1 |
| Status | Validated |
| Author | Rafael Hidalgo |
| Date Created | August 9, 2026 |
| Last Updated | August 12, 2026  |

## Executive Summary

The Salon Management System is an internal web application designed for Yab's Hair and Beauty Studio to digitize its current sales recording, commission calculation, payment tracking, and business reporting processes.

The product will replace handwritten transaction records and calculator-based computations with a centralized system that allows completed transactions to be recorded digitally, automatically calculates staff commissions and Business Share, tracks Cash and GCash payments, and generates daily and monthly business reports.

The initial product will primarily serve two users: the Business Owner and the Cashier.

The MVP will prioritize transaction accuracy, operational efficiency, financial visibility, and ease of use while maintaining the existing business rules of Yab's Hair and Beauty Studio.

## Product Vision

To transform the manual sales and commission workflow of Yab's Hair and Beauty Studio into a reliable digital process that reduces repetitive administrative work, minimizes calculation errors, and provides accurate and accessible visibility into daily and monthly business performance.

The Salon Management System will enable the business to record completed transactions digitally, automate commission and Business Share calculations, track Cash and GCash payments, and generate structured reports without relying on handwritten records and repetitive calculator-based computations.

Ultimately, the product aims to make daily operations faster, more accurate, and easier to manage while providing the owner with reliable information for understanding business performance.

## Problem Statement

Yab's Hair and Beauty Studio currently relies on handwritten records and manual calculations to manage sales, staff commissions, payment information, and business reporting.

This workflow creates unnecessary administrative work, increases the risk of calculation and recording errors, and makes daily and monthly business information difficult to obtain efficiently.

The detailed business problems, current workflow, and operational requirements are documented in the Business Requirements Specification (BRS).

## Product Goals

The Salon Management System aims to achieve the following product outcomes:

### PG-001 — Reduce Manual Computation

Minimize the cashier's reliance on manual calculator-based computation by automatically calculating staff commissions, Business Share, and sales totals.

### PG-002 — Provide Immediate Business Visibility

Enable the owner to access accurate daily and monthly sales information without manually reviewing and calculating records from handwritten logbooks.

### PG-003 — Improve Transaction and Calculation Accuracy

Reduce human errors associated with manually recording transactions, calculating commissions, and preparing sales reports.

### PG-004 — Improve Operational Efficiency

Reduce the time and effort required to record transactions, calculate commissions, reconcile payments, and complete daily business reporting.

### PG-005 — Provide Clear Information for Both Primary Users

Provide the cashier with a clear and efficient transaction-recording workflow while giving the owner understandable and reliable visibility into sales, payment methods, staff commissions, and Business Share.

## Non-Goals

The initial version of the Salon Management System is intentionally focused on solving the current sales recording, commission calculation, payment tracking, and reporting problems of Yab's Hair and Beauty Studio.

The following capabilities are not goals of the MVP:

- Inventory management
- Appointment booking
- Customer accounts and profiles
- Customer loyalty or rewards programs
- Multi-branch management
- Expense tracking
- Full payroll management
- Native Android or iOS applications
- AI-powered analytics or sales forecasting
- Advanced business intelligence and predictive reporting

These capabilities may provide value in future versions but are intentionally excluded from the MVP to maintain a focused scope and reduce unnecessary development complexity.

Future features should only be considered after the core system has been implemented, tested, and validated in actual business operations.

## Target Users

The MVP is designed for two primary users within Yab's Hair and Beauty Studio:

### Business Owner

Uses the system primarily for business monitoring, administration, and reporting.

Key needs include:

- Daily and monthly sales visibility
- Cash and GCash breakdowns
- Staff commission visibility
- Business Share visibility
- Management of staff, services, products, and commission rules

### Cashier

Uses the system primarily for recording completed transactions and supporting daily business operations.

Key needs include:

- Fast transaction recording
- Service and product selection
- Staff assignment
- Cash and GCash recording
- GCash reference number recording
- Automatic commission calculations
- Reduced manual computation

Detailed user behaviors, pain points, usage contexts, and scenarios are documented in the **User Personas** document.

## Product Principles

The following principles will guide product and design decisions throughout the development of the Salon Management System.

### 1. Accuracy Before Convenience

Financial records, commission calculations, payment information, and reports must prioritize correctness and data integrity.

When a tradeoff exists between a slightly faster workflow and a more reliable financial record, accuracy should take priority.

### 2. Fast Daily Operations

Common cashier workflows should require minimal unnecessary steps.

Recording completed transactions should be fast enough to support normal salon operations without creating additional delays during customer checkout.

### 3. Automate Repetitive Work

Calculations that can be reliably performed by the system should not require manual computation.

This includes:

- Staff Commission
- Business Share
- Daily Sales totals
- Monthly Sales totals
- Cash and GCash totals

The cashier should primarily provide transaction information while the system performs applicable calculations.

### 4. Make Business Information Visible

The product should transform recorded transaction data into information that the owner can immediately understand and use.

Important business information includes:

- Gross Sales
- Cash Sales
- GCash Sales
- Staff Commissions
- Business Share
- Daily performance
- Monthly performance

### 5. Keep Complexity Purposeful

The system should remain understandable and predictable for both the Owner and Cashier.

Simplicity should not mean removing useful capabilities. Instead, unnecessary steps, information, and features should be avoided unless they provide clear business value.

## Core Product Capabilities

The MVP consists of six core product capabilities. These capabilities work together to replace the existing manual sales, commission, payment-recording, and reporting workflows of Yab's Hair and Beauty Studio.

### 1. Transaction Management

The system will provide a centralized workflow for recording completed customer transactions.

The capability will support:

- Recording completed customer transactions
- Recording multiple services and/or products within a transaction
- Assigning staff members to applicable sale items
- Supporting fixed and variable selling prices
- Automatically recording transaction date and time
- Preserving completed transaction records
- Supporting Owner-controlled voiding of incorrect completed transactions
- Preserving voided transactions for historical traceability
- Excluding voided transactions from active financial calculations

Transaction Management serves as the primary source of operational data used by commission calculation, payment tracking, and reporting.

### 2. Commission Engine

The system will automatically calculate staff commissions and Business Share based on the applicable business rules.

The capability will support:

- Percentage-based commissions
- Fixed-amount product commissions
- Automatic Business Share calculation
- Product sales with or without staff commission
- Preservation of historical commission values

The Commission Engine is intended to eliminate repetitive calculator-based commission computation.

### 3. Reporting

The system will transform recorded transaction data into structured business information.

The capability will provide:

- Daily sales reports
- Monthly sales reports
- Gross Sales
- Cash and GCash breakdowns
- Total Staff Commission
- Total Business Share
- Staff-level sales and commission breakdowns
- Transaction-level reporting details

Reporting will provide the owner with immediate visibility into business performance without requiring manual calculations from physical logbooks.

### 4. Payment Management

The system will record payment information associated with completed transactions.

The capability will support:

- Cash payments
- GCash payments
- Required GCash reference numbers
- Payment-method preservation
- Cash and GCash reconciliation within reports

### 5. Business Administration

The system will allow the owner to maintain the business information required for daily operations.

The capability will support management of:

- Staff members
- Services
- Products
- Prices
- Commission rules

Administrative changes must not modify historical transaction records.

### 6. Authentication

The system will restrict application access to authorized users and provide access based on the user's role.

The MVP will support:

- Owner authentication
- Cashier authentication
- Secure login
- Role-based access restrictions
- Protection of business and financial information

The Owner will have access to administrative capabilities such as managing staff, services, products, prices, and commission rules. Can Void incorrect completed transactions.

The Cashier will primarily have access to transaction-recording and applicable reporting capabilities.
The Cashier shall not be permitted to void, edit, or permanently delete completed transactions.

Authentication protects access to business and financial information but is considered a supporting capability rather than the primary source of product value.

## Success Metrics

The success of the MVP will be evaluated based on improvements to operational speed, accuracy, automation, and business visibility at Yab's Hair and Beauty Studio.

Baseline measurements will be collected from the current manual workflow before full deployment where applicable.

### SM-001 — Faster Transaction Recording

The system should reduce the time required for the cashier to record completed customer transactions compared with the existing handwritten logbook process.

The transaction workflow should minimize repetitive writing and manual computation.

**Measurement:**
Average time required to record a transaction before and after implementation.

---

### SM-002 — Faster Daily Closing

The system should significantly reduce the time required to calculate daily sales, staff commissions, payment totals, and Business Share.

**Measurement:**
Average end-of-day calculation and reconciliation time before and after implementation.

---

### SM-003 — Accurate Commission Calculations

The system should correctly calculate staff commissions according to the configured business rules without requiring manual calculator-based computation.

**Measurement:**
System-generated commission calculations should match the validated commission rules for all tested transaction scenarios.

---

### SM-004 — Accurate Sales and Payment Records

The system should reduce errors associated with manually recording prices, calculating sales totals, and identifying payment methods.

Recorded transactions should accurately preserve:

- Final Selling Price
- Payment Method
- GCash Reference Number, when applicable
- Assigned Staff Member, when applicable
- Staff Commission
- Business Share

**Measurement:**

Tested transactions should preserve the entered selling price, selected payment method, applicable GCash reference number, assigned staff member when applicable, calculated Staff Commission, and Business Share without unintended modification.

---

### SM-005 — Eliminate Routine Manual Calculations

The cashier should no longer need to manually calculate:

- Daily Sales
- Monthly Sales
- Staff Commissions
- Business Share
- Cash Sales totals
- GCash Sales totals

These values should be automatically generated from recorded transactions.

---

### SM-006 — Immediate Daily Business Visibility

The owner should be able to access current daily business information without manually reviewing and calculating entries from the physical logbook.

The system should provide:

- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Business Share
- Commission breakdown by barber or stylist

---

### SM-007 — Immediate Monthly Business Visibility

The owner should be able to obtain monthly business information directly from the system without manually calculating transactions from previous daily records.

The monthly report should provide:

- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Business Share
- Staff-level sales and commission breakdowns

**Measurement:**

The Owner can retrieve the required monthly business information without manually calculating totals from individual daily records.

## Requirements Traceability

Detailed business and functional requirements for the Salon Management System are maintained in the validated Business Requirements Specification (BRS).

The PRD translates those validated business requirements into product capabilities, goals, priorities, and success criteria.

Detailed implementation-oriented user requirements and acceptance criteria will be maintained separately in the User Stories document.

This separation is intended to maintain traceability while avoiding unnecessary duplication across product documentation.

## Risks and Mitigations

The following risks may affect the reliability, adoption, or effectiveness of the Salon Management System.

## Risks and Mitigations

The following risks may affect the reliability, adoption, or effectiveness of the Salon Management System.

| ID | Priority | Risk | Potential Impact | Mitigation |
|---|---|---|---|---|
| R-001 | Medium | Internet unavailability | The cashier may be temporarily unable to record transactions or access the system during business operations. | Ensure the existing manual process can temporarily serve as a fallback during outages. Offline capabilities may be evaluated in a future release if outages become a significant operational issue. |
| R-002 | High | Incorrect cashier input | Incorrect prices, staff assignments, payment methods, or GCash reference numbers may produce inaccurate records and reports. | Use clear forms, required fields, input validation, confirmation before submission, and sensible defaults where appropriate. |
| R-003 | High | Low user adoption | The Owner or Cashier may continue relying on the existing logbook if the system feels slower or more difficult than the current process. | Prioritize fast and understandable workflows, involve actual users during testing, and collect feedback before full adoption. |
| R-004 | Critical | Incorrect commission configuration | Incorrect percentage or fixed commission rules may cause incorrect staff commissions and Business Share calculations across multiple transactions. | Restrict commission configuration to the Owner, clearly display configured rules, validate values, and test commission scenarios before deployment. |
| R-005 | Critical | Data loss | Loss of transaction records could affect sales reports, commission records, and historical business information. | Use persistent database storage, implement appropriate backup and recovery practices, and avoid relying on temporary storage for financial records. |

## Release Criteria

The MVP will be considered ready for initial deployment at Yab's Hair and Beauty Studio when the following criteria have been satisfied.

### Core Transaction Workflow

- The Cashier can successfully record a completed customer transaction.
- A transaction can contain one or more services and/or products.
- Each service sale item requires an assigned barber or stylist.
- Product sale items can be recorded with or without an assigned staff member.
- Variable service prices can be entered when applicable.
- The system automatically records the transaction date and time.
- Completed transactions are preserved after submission.
- The Cashier cannot edit or delete a completed transaction after submission.

### Commission Calculation

The system correctly calculates commissions for all supported business scenarios:

- 50% staff / 50% Business Share for applicable haircut services.
- 40% staff / 60% Business Share for applicable services using salon-owned products.
- Fixed commissions for applicable product sales credited to staff.
- No staff commission for product sales without an assigned staff member.
- Business Share is calculated correctly for every applicable sale item.
- Historical transactions retain the commission rules and amounts used at the time of sale.

### Payment Management

- The Cashier can select Cash or GCash as the payment method.
- Cash transactions can be completed without a payment reference number.
- GCash transactions cannot be completed without a reference number.
- Payment method and applicable reference information are preserved with the transaction.

### Reporting

The Owner can access:

- Daily Sales Reports
- Monthly Sales Reports
- Gross Sales
- Cash Sales
- GCash Sales
- Total Staff Commission
- Total Business Share
- Staff-level sales and commission breakdowns
- Individual transaction details

The following reconciliation rules must hold:

- Cash Sales + GCash Sales = Gross Sales
- Staff Commission + Business Share = Gross Sales

### Administration

The Owner can manage the operational information required by the MVP, including:

- Staff members
- Services
- Products
- Applicable prices
- Commission rules

Changes to administrative configuration must not alter historical transaction records.

### Authentication and Access

- Authorized Owner and Cashier users can access the system.
- Unauthorized users cannot access protected business information.
- User credentials are handled securely.

### Reliability and Data Integrity

- Completed transactions persist correctly after being recorded.
- Historical transactions can be retrieved for reporting.
- Core financial calculations pass defined test cases.
- No known critical defects remain that could cause incorrect sales, payment, commission, or Business Share records.
- Completed transactions cannot be directly edited or permanently deleted.
- The Cashier cannot void completed transactions.
- The Owner can void an incorrect completed transaction.
- A void reason is required.
- The original transaction remains preserved after voiding.
- The system records who voided the transaction and when it was voided.
- Voided transactions do not contribute to active sales, payment totals, Staff Commission, or Business Share.
- Corrected information is recorded through a new transaction when necessary.

### User Validation

Before full operational adoption:

- The Owner successfully completes the core reporting workflow.
- The Cashier successfully completes the core transaction-recording workflow.
- Both users confirm that the core workflows are understandable and usable for normal salon operations.
- Any critical usability issues discovered during validation are resolved before full adoption.

### Deployment

- The production application is accessible through its intended web environment.
- The production database is configured correctly.
- Required environment variables and credentials are securely configured.
- Basic backup and recovery procedures for business data are documented.

## Version History

| Version | Date | Author | Description |
|---|---|---|---|
| 1.0 | August 10, 2026 | Rafael Hidalgo | Initial Validated Product Requirements Document |
| 1.1 | August 11, 2026 | Rafael Hidalgo | Added Owner-controlled transaction voiding and role-based correction workflow |

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| PD-001 | Accuracy shall take priority over speed when the two conflict | The system manages financial records and commission calculations, making correctness essential to product trust. |
| PD-002 | Transaction Management, Commission Management, and Reporting are the primary value-driving capabilities of the MVP | These capabilities directly address the core operational problems identified during Discovery. |
| PD-003 | Authentication is considered a supporting capability rather than a primary source of product value | Authentication protects business information but does not directly solve the existing sales, commission, and reporting problems. |
| PD-004 | The MVP shall remain focused on existing sales, commission, payment, administration, and reporting workflows | Limiting scope reduces development complexity and enables earlier validation of the core product. |
| PD-005 | Inventory management, appointment booking, customer accounts, multi-branch management, native mobile applications, and AI-powered analytics shall not be included in the MVP | These capabilities do not directly address the validated core business problems and may be considered after successful MVP deployment. |
| PD-006 | Success shall be evaluated using observable business outcomes rather than unsupported target percentages | Reliable baseline data does not currently exist for metrics such as transaction time, closing time, and error frequency. |
| PD-007 | Baseline operational measurements should be collected before deployment where practical | Before-and-after measurements will allow the actual impact of the product to be evaluated after adoption. |
| PD-008 | Detailed business and functional requirements shall remain in the BRS rather than being duplicated in the PRD | This reduces documentation duplication while maintaining traceability between business requirements and product decisions. |
| PD-009 | Detailed user-level requirements and acceptance criteria shall be maintained in the User Stories document | Separating user stories from the PRD keeps the PRD focused on product direction, capabilities, priorities, and success criteria. |
| PD-010 | The MVP shall be validated by the actual Owner and Cashier before full operational adoption | The product must be usable in the real business workflow, not merely technically complete. |
| PD-011 | Incorrect completed transactions shall use an Owner-controlled void workflow rather than direct editing or deletion | Preserves financial traceability while allowing genuine recording errors to be corrected |