# Business Requirements Specification (BRS)

## Document Information

| Field | Value |
|--------|-------|
| Project | Salon Management System |
| Document | Business Requirements Specification |
| Version | 1.0 |
| Status | Draft |
| Author | Rafael Hidalgo |
| Date Created | August 7, 2026 |
| Last Updated | August 7, 2026 |

## 1. Introduction

### 1.1 Purpose

This Business Requirements Specification (BRS) defines the business needs, operational challenges, and high-level requirements for the proposed Salon Management System.

The document serves as the foundation for understanding how the business currently operates and identifies the problems that the system aims to solve. It will guide future product planning, system design, development, testing, and deployment.

### 1.2 Scope

This document focuses exclusively on the business requirements of the system.

It describes the current business workflow, identifies operational pain points, defines business rules, and establishes the requirements needed to improve salon operations through software.

Technical implementation details such as programming languages, databases, APIs, and user interface design are intentionally excluded and will be documented separately during later phases of the project.

## 2. Business Overview

### 2.1 Business Background

Yab's Hair and Beauty Studio is a family-owned barbershop and salon that provides grooming and beauty services for both men and women.

The business offers a variety of services including haircuts, shaving, hair coloring, hair treatments, rebonding, and the sale of salon products such as hair wax.

Daily operations are currently managed through handwritten logbooks and manual commission calculations. The cashier records completed transactions while the owner reviews sales and business performance at the end of each business day.

As the business continues to grow, the existing manual workflow has become increasingly time-consuming, difficult to monitor, and prone to human error. These operational challenges present an opportunity to improve efficiency through a centralized digital management system.

## 3. Current Business Process

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

## 4. Business Problems

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

## 5. Business Objectives

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

## 6. Stakeholders

| Stakeholder | Role | Interest |
|-------------|------|----------|
| Business Owner | Project Sponsor | Improve operational efficiency and business visibility |
| Cashier | Primary User | Faster sales recording and commission computation |
| Barbers | Indirect User | Accurate commission tracking |
| Stylists | Indirect User | Accurate commission tracking |
| Customers | Indirect Stakeholder | Faster checkout experience |

## 7. User Roles

### Owner

Responsibilities:

- View daily reports
- View monthly reports
- Manage services
- Configure commission rules
- Monitor business performance

---

### Cashier

Responsibilities:

- Log completed sales
- Record product sales
- Calculate commissions automatically
- View generated reports

## 8. Business Rules

The following rules define how Yab's Hair and Beauty Studio currently operates.

### Sales Recording

- Sales shall only be recorded after payment has been received.
- Every transaction shall automatically record its date and time.
- Saved sales shall not be editable or deletable by the cashier.
- Each sale item shall be assigned to only one barber or stylist.
- A customer transaction may contain multiple services and/or products.
- Each transaction shall record the payment method used.
- Supported payment methods for the MVP shall be Cash and GCash.

### Pricing

- Haircuts have fixed pricing.
- Selected services may have variable pricing depending on customer requirements.
- Cashiers may enter the final agreed selling price for applicable services.

### Commission Rules

- Haircuts:
    - Barber: 50%
    - Owner: 50%

- Services using salon-owned products:
    - Stylist: 40%
    - Owner: 60%

- Product Sales:
    - Fixed commission per product.

### Historical Records

Historical sales must preserve:

- Selling price
- Commission percentage
- Commission amount

Changes to commission rules must not affect previous sales.

### Payment

- Every transaction shall have a payment method.
- The supported payment methods for the MVP shall be Cash and GCash.
- Cash transactions shall not require a payment reference number.
- GCash transactions shall require a reference number before the transaction can be saved.
- The GCash reference number shall be stored with the transaction for recordkeeping and reconciliation purposes.
- The GCash reference number shall not by itself be treated as proof that payment was successfully received.

## 9. Functional Requirements

### Authentication

FR-001 The system shall allow authorized users to log in.

FR-002 The system shall restrict access to authorized users only.

---

### Sales Management

FR-003 The system shall record completed sales.

FR-004 The system shall support recording multiple services or products within a customer transaction.

FR-005 The system shall store the assigned barber or stylist for each sale item.

---

### Commission Management

FR-006 The system shall automatically calculate commissions.

FR-007 The system shall preserve historical commission records.

---

### Reporting

FR-008 The system shall generate daily sales reports.

FR-009 The system shall generate monthly sales reports.

---

### Administration

FR-010 The owner shall manage available services.

FR-011 The owner shall configure commission rules.

## 10. Non-Functional Requirements

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

## 11. Assumptions

- Every completed service is recorded by the cashier.
- Every sale item belongs to one barber or stylist.
- Commission rules remain consistent unless updated by the owner.
- Internet access is available during business hours.
- Only the owner and cashier require system access.

## 12. Constraints

- The initial release supports only one salon branch.
- The MVP supports only two user roles.
- Inventory management is outside the scope of the initial release.
- Appointment booking is outside the scope of the initial release.

## 13. Future Considerations

Potential enhancements include:

- Multi-branch support
- Inventory management
- Customer profiles
- Appointment scheduling
- Audit logs
- Analytics dashboard
- AI-powered business insights

## 14. Version History

| Version | Date | Author | Description |
|----------|------|---------|-------------|
| 1.0 | August 7, 2026 | Rafael Hidalgo | Initial Business Requirements Specification |

## 15. Decision Log

| ID | Decision | Rationale |
|----|----------|-----------|
| D-001 | Build the system as a web application | Accessible from any device with a web browser |
| D-002 | Sales become immutable after saving | Protects financial data integrity |
| D-003 | Historical commission values remain unchanged | Ensures accurate financial reporting |
| D-004 | One sale item is assigned to one barber or stylist | Reflects the current business workflow |
| D-005 | The MVP supports only the Owner and Cashier roles | Matches the current operational process |

## Version History

| Version | Date | Author | Description |
|----------|------|---------|-------------|
| 1.0 | August 7, 2026 | Rafael Hidalgo | Initial Business Requirements Specification |