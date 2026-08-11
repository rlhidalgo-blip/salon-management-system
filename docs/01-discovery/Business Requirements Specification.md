# Business Requirements Specification (BRS)

## Document Information

| Field | Value |
|--------|-------|
| Project | Salon Management System |
| Document | Business Requirements Specification |
| Version | 1.1 |
| Status | Validated |
| Author | Rafael Hidalgo |
| Date Created | August 7, 2026 |
| Last Updated | August 11, 2026 |

## Introduction

### Purpose

This Business Requirements Specification (BRS) defines the business needs, operational challenges, and high-level requirements for the proposed Salon Management System.

The document serves as the foundation for understanding how the business currently operates and identifies the problems that the system aims to solve. It will guide future product planning, system design, development, testing, and deployment.

### Scope

This document focuses exclusively on the business requirements of the system.

It describes the current business workflow, identifies operational pain points, defines business rules, and establishes the requirements needed to improve salon operations through software.

Technical implementation details such as programming languages, databases, APIs, and user interface design are intentionally excluded and will be documented separately during later phases of the project.

## Business Overview

### Business Background

Yab's Hair and Beauty Studio is a family-owned barbershop and salon that provides grooming and beauty services for both men and women.

The business offers a variety of services including haircuts, shaving, hair coloring, hair treatments, rebonding, and the sale of salon products such as hair wax.

Daily operations are currently managed through handwritten logbooks and manual commission calculations. The cashier records completed transactions while the owner reviews sales and business performance at the end of each business day.

As the business continues to grow, the existing manual workflow has become increasingly time-consuming, difficult to monitor, and prone to human error. These operational challenges present an opportunity to improve efficiency through a centralized digital management system.

## Business Terminology

The following terms are used throughout this document to maintain consistent definitions across business and product discussions.

| Term | Definition |
|---|---|
| Gross Sales | Total value of all recorded sales before staff commissions are deducted. |
| Staff | A barber or stylist who performs a service or is credited with an eligible product sale. |
| Staff Commission | Amount earned by an eligible barber or stylist from a completed service or credited product sale. |
| Business Share | Portion of a sale retained by Yab's Hair and Beauty Studio after the staff commission is deducted. This does not represent net profit because other business expenses are not included. |
| Cash Sales | Transactions paid using physical cash. |
| GCash Sales | Transactions recorded as paid through GCash. |
| Payment Method | Method used by the customer to pay for a transaction. The MVP supports Cash and GCash. |
| Payment Reference | Reference number recorded for a GCash transaction for reconciliation and recordkeeping. |
| Service | A salon or barbershop service performed for a customer, such as a haircut, hair color, treatment, shave, or rebond. |
| Product | A physical item sold by the business, such as hair wax. |
| Sale Item | An individual service or product included within a transaction. |
| Transaction | A completed customer purchase containing one or more sale items and recorded after payment has been received. |
| Variable Price | A service price that may change depending on factors such as hair length or the final price agreed upon with the customer. |

## Current Business Process

Customer enters salon
        │
        ▼
Customer chooses one or more services
        │
        ▼
Barber or stylist performs the service
        │
        ▼
Cashier receives payment
        │
        ▼
Cashier manually records the sale in the logbook
        │
        ▼
Cashier manually computes commissions
        │
        ▼
Owner reviews daily sales

Yab's Hair and Beauty Studio currently operates using a completely manual workflow.

After a customer completes one or more services and payment has been received, the cashier records each transaction in a handwritten logbook.

At the end of the business day, the cashier manually calculates the commission earned by each barber or stylist using a calculator. Daily sales are then summarized and reviewed by the business owner.

Although this workflow has supported daily operations, it becomes increasingly inefficient as transaction volume grows and introduces a higher risk of calculation and recording errors.

## Business Problems

The current workflow introduces several operational challenges that affect both efficiency and accuracy.

### Manual Sales Recording

Sales are recorded manually in handwritten logbooks, making records difficult to organize, search, and verify.

### Manual Commission Computation

The cashier manually calculates commissions using a calculator, increasing the likelihood of arithmetic errors and inconsistencies.

### Time-Consuming Daily Closing

Preparing end-of-day reports requires manually reviewing every recorded transaction, resulting in unnecessary administrative work.

### Human Error

Mistakes may occur when recording transactions, calculating commissions, or handling customers who purchase multiple services or products during a single visit.

### Limited Business Visibility

The owner has limited access to historical sales information, making it difficult to evaluate business performance or identify trends over time.

### Lack of Centralized Records

Business information is stored in physical logbooks, making long-term recordkeeping and reporting inefficient.

## Business Objectives

The proposed Salon Management System aims to achieve the following business objectives for Yab's Hair and Beauty Studio:

### Primary Objectives

- Digitize the existing manual sales recording process.
- Automate commission computation for barbers and stylists.
- Reduce human errors in sales recording and commission calculations.
- Improve the efficiency of daily business closing.
- Generate accurate daily and monthly sales reports.
- Centralize operational data into a single system.

### Secondary Objectives

- Improve visibility into business performance.
- Preserve historical sales records.
- Standardize the sales recording process.
- Establish a scalable foundation for future business growth.

## Stakeholders

| Stakeholder | Role | Interest |
|-------------|------|----------|
| Business Owner | Project Sponsor | Improve operational efficiency and business visibility |
| Cashier | Primary User | Faster sales recording and commission computation |
| Barbers | Indirect User | Accurate commission tracking |
| Stylists | Indirect User | Accurate commission tracking |
| Customers | Indirect Stakeholder | Faster checkout experience |

## User Roles

### Owner

Responsibilities:

- View daily reports
- View monthly reports
- Manage staff members
- Manage services
- Manage products
- Configure commission rules
- Monitor business performance

---

### Cashier

Responsibilities:

- Log completed sales
- Record product sales
- Select the applicable payment method
- Record GCash reference numbers when applicable
- View automatically calculated commissions
- View generated reports

## Business Rules

The following rules define how Yab's Hair and Beauty Studio currently operates.

### Sales Recording

- Sales shall only be recorded after payment has been received.
- Every transaction shall automatically record its date and time.
- Completed transactions shall not be directly editable or permanently deletable.
- The Cashier shall not be permitted to void completed transactions.
- The Owner may void an incorrect completed transaction.
- A reason shall be required when voiding a transaction.
- Voided transactions shall remain preserved as historical records.
- Voided transactions shall not contribute to active financial totals or commission calculations.
- Corrected information shall be recorded through a new transaction when necessary.

- Each service sale item shall be assigned to exactly one barber or stylist.
- A product sale item may optionally be assigned to one barber or stylist.
- If a product sale is assigned to a staff member, the applicable product commission shall be awarded to that staff member.
- If a product sale is not assigned to a staff member, no staff commission shall be generated, and the full selling price shall be treated as Business Share.
- A customer transaction may contain multiple services and/or products.
- Each transaction shall record the payment method used.
- Supported payment methods for the MVP shall be Cash and GCash.

### Pricing

- Haircuts shall use a fixed selling price.
- Selected salon services may have variable pricing depending on customer requirements, such as hair length.
- The cashier shall be able to enter the final agreed selling price for services with variable pricing.
- Product prices shall use their configured selling price unless otherwise permitted by the business.

### Commission

#### Haircut Services

- Barber share: 50%
- Business share: 50%

#### Services Using Salon-Owned Products

Examples include hair coloring, hair treatment, and rebonding.

- Stylist share: 40%
- Business share: 60%

#### Product Sales

- Products may use a fixed commission amount.
- If a product sale is credited to a staff member, the staff member shall receive the configured fixed commission.
- If no staff member is credited with the product sale, no staff commission shall be generated.
- For product sales without staff commission, the full selling price shall be treated as Business Share.

Example:

Hair Wax
Selling Price: ₱250

If sold by eligible staff:
Staff Commission: ₱50
Business Share: ₱200

If no staff member is credited:
Staff Commission: ₱0
Business Share: ₱250

### Historical Records

Once a transaction has been recorded, the system shall preserve the transaction information used at the time of sale.

Historical transaction records shall include:

- Transaction date and time
- Items sold
- Final selling price
- Assigned barber or stylist
- Payment method
- Payment reference number, when applicable
- Commission type
- Commission rate or fixed commission value
- Staff commission amount
- Business share
- Transaction status
- Void reason, when applicable
- Voided by, when applicable
- Void date and time, when applicable

Changes to prices, services, products, or commission rules shall not alter previously recorded transactions.transactions.

### Payment

- Every transaction shall have a payment method.
- The supported payment methods for the MVP shall be Cash and GCash.
- Cash transactions shall not require a payment reference number.
- GCash transactions shall require a reference number before the transaction can be saved.
- The GCash reference number shall be stored with the transaction for recordkeeping and reconciliation purposes.
- The GCash reference number shall not by itself be treated as proof that payment was successfully received.

## Functional Requirements

The following functional requirements define the core capabilities required by the Salon Management System.

### Authentication

**FR-001** The system shall allow authorized users to log in.

**FR-002** The system shall restrict access to authorized users only.

---

### Sales Management

**FR-003** The system shall allow the cashier to record completed customer transactions.

**FR-004** The system shall support recording multiple services and/or products within a single customer transaction.

**FR-005** The system shall require each service sale item to be assigned to one barber or stylist. Product sale items may be recorded with or without an assigned staff member.

**FR-006** The system shall allow the cashier to enter the final selling price for services that use variable pricing.

**FR-007** The system shall prevent the cashier from editing or deleting a transaction after it has been saved.

**FR-008** The system shall automatically record the date and time when a completed transaction is saved.

---

### Commission Management

**FR-009** The system shall automatically calculate the staff commission for each applicable sale item based on the commission rule in effect at the time of the transaction.

**FR-010** The system shall support percentage-based commission calculations.

**FR-011** The system shall support fixed-amount commission calculations for applicable product sales.

**FR-012** The system shall calculate the business share for each applicable sale item.

**FR-013** The system shall preserve the commission rate or fixed commission value, commission amount, and business share used at the time of the transaction.

**FR-014** Changes to commission rules shall not modify previously recorded transactions.

---

### Payment Management

**FR-015** The system shall require the cashier to select a payment method when recording a transaction.

**FR-016** The system shall support Cash and GCash as payment methods for the MVP.

**FR-017** The system shall require a GCash reference number when GCash is selected as the payment method.

**FR-018** The system shall not require a payment reference number when Cash is selected as the payment method.

**FR-019** The system shall preserve the payment method and applicable GCash reference number as part of the historical transaction record.

---

### Administration

**FR-020** The system shall allow the owner to manage staff members.

**FR-021** The system shall allow the owner to manage available services.

**FR-022** The system shall allow the owner to manage products.

**FR-023** The system shall allow the owner to configure applicable commission rules.

---

### Reporting

**FR-024** The system shall generate daily sales reports.

**FR-025** The system shall generate monthly sales reports.

**FR-026** The system shall display the total Gross Sales for the selected reporting period.

**FR-027** The system shall display the number of recorded transactions for the selected reporting period.

**FR-028** The system shall provide separate totals for Cash Sales and GCash Sales.

**FR-029** The system shall display the total Staff Commission for the selected reporting period.

**FR-030** The system shall display the total Business Share for the selected reporting period.

**FR-031** The system shall provide a commission breakdown for each barber or stylist.

**FR-032** The system shall display the sales generated by each barber or stylist.

**FR-033** The system shall display individual transaction details including the transaction date and time, sale items, assigned staff member, selling price, payment method, staff commission, and business share.

**FR-034** The system shall display the GCash reference number for applicable GCash transactions.

**FR-035** The system shall ensure that the sum of Cash Sales and GCash Sales equals the Gross Sales recorded for the selected reporting period.

**FR-036** The system shall ensure that the sum of Staff Commission and Business Share equals the Gross Sales recorded for the selected reporting period.

**FR-037** The system shall allow the Owner to void an incorrect completed transaction while preserving the original transaction record, void reason, responsible user, and void timestamp.

**FR-038** The system shall exclude voided transactions from active sales, payment, commission, and Business Share calculations.

## Reporting Information Requirements

Daily and monthly reports shall provide the business with the following categories of information:

### Sales Overview

- Gross Sales
- Number of Transactions
- Total Staff Commission
- Total Business Share

### Payment Breakdown

- Cash Sales
- GCash Sales
- Total Payments

The sum of Cash and GCash payments shall equal the total Gross Sales for the selected reporting period.

### Staff Commission Breakdown

For each barber or stylist:

- Staff Member
- Sales Generated
- Commission Earned

The report shall also display the total commission earned by all staff members.

### Transaction Details

Each recorded transaction shall display:

- Transaction Date and Time
- Staff Member
- Service or Product
- Selling Price
- Payment Method
- GCash Reference Number, when applicable
- Staff Commission
- Business Share

### Financial Reconciliation

The report shall maintain the following relationships:

Cash Sales + GCash Sales = Gross Sales

Staff Commission + Business Share = Gross Sales

## Non-Functional Requirements

### Performance

- Reports should generate within five seconds.
- Commission calculations should occur immediately after recording a sale.

### Security

- Only authorized users may access the system.
- Passwords shall be securely stored.

### Reliability

- Sales records shall not be lost during normal operation.

### Usability

- The interface should be simple enough for new cashiers to learn quickly.

### Maintainability

- The system should be modular to support future enhancements.

## Assumptions

- Every completed service is recorded by the cashier.
- Every service sale item is assigned to exactly one barber or stylist.
- Product sale items may be recorded with or without an assigned staff member.
- Commission rules remain consistent unless updated by the owner.
- Internet access is available during business hours.
- Only the owner and cashier require system access.

## Constraints

- The initial release supports only one salon branch.
- The MVP supports only two user roles.
- Inventory management is outside the scope of the initial release.
- Appointment booking is outside the scope of the initial release.

## Future Considerations

Potential enhancements include:

- Multi-branch support
- Inventory management
- Customer profiles
- Appointment scheduling
- Audit logs
- Analytics dashboard
- AI-powered business insights

## Version History

| Version | Date           | Author         | Description |
| ------- | -------------- | -------------- | ----------- |
| 1.0     | August 8, 2026 | Rafael Hidalgo | Initial validated Business Requirements Specification |
| 1.1     | August 11, 2026 | Rafael Hidalgo | Added Owner-controlled transaction voiding and historical correction requirements |

## Decision Log

| ID | Decision | Rationale |
|---|---|---|
| D-001 | Build the system as a web application | Allows the system to be accessed through a browser without requiring installation on individual devices |
| D-002 | Completed transactions shall not be directly edited or permanently deleted | Protects financial data integrity and preserves historical transaction records |
| D-003 | Historical commission values shall remain unchanged | Ensures historical financial records remain accurate when commission rules change |
| D-004 | Service sale items require one assigned barber or stylist, while product sale items may have optional staff assignment | Services require staff attribution for commission calculation, while products may be purchased without being sold by a specific staff member |
| D-005 | The MVP shall support Owner and Cashier as system users | These are the only roles that currently require direct system access |
| D-006 | Transactions shall automatically record their date and time | Required for accurate daily and monthly reporting |
| D-007 | Cash and GCash shall be supported in the MVP | Reflects the payment methods currently used by the business |
| D-008 | GCash payments shall require a reference number | Provides traceability for payment reconciliation and recordkeeping |
| D-009 | Reports shall separate Cash and GCash totals | Allows the owner to reconcile recorded sales against actual payment channels |
| D-010 | Reports shall separate staff commissions and business share | Allows the owner to understand how gross sales are distributed |
| D-011 | The term "Business Share" shall be used instead of "Profit" | Commission deductions alone do not account for all business expenses |
| D-012 | Incorrect completed transactions shall be voided rather than edited or permanently deleted | Preserves financial history while allowing the Owner to correct recording errors |


