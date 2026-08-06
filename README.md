# Salon Management System

> An internal web application designed to digitize salon operations by automating sales logging, commission calculation, and business reporting.

---

# Why This Project Exists

This project was inspired by a real operational problem experienced by our family-owned barbershop and salon.

Daily sales were recorded in handwritten logbooks, commissions were computed manually using calculators, and end-of-day reconciliation often took significant time while remaining prone to human error.

Rather than immediately writing code, I wanted to first understand the business, identify its operational challenges, and design a software solution around actual user needs.

This repository documents that entire journey—from business discovery and product planning to implementation and deployment.

---

# Project Overview

The Salon Management System is an internal business management application designed specifically for salon operations.

Its primary objective is to replace manual workflows with a centralized digital system that enables cashiers and business owners to efficiently manage sales, commissions, services, and business reports.

Beyond building functional software, this project demonstrates a complete product development lifecycle, emphasizing business analysis, requirements gathering, software design, implementation, testing, and continuous improvement.

---

# Business Problem

The existing business process relies entirely on manual operations.

Current workflow:

1. Customer receives one or more services.
2. Cashier records every transaction in a handwritten logbook.
3. At the end of the day, commissions are manually computed.
4. Daily sales reports are prepared manually.
5. The owner reviews the records for verification.

This process creates several operational challenges:

- Manual sales logging
- Manual commission computation
- Time-consuming daily closing
- Human errors during calculations
- Difficult reporting and reconciliation
- No historical business analytics
- Limited visibility into business performance

---

# Proposed Solution

Develop a centralized web application that digitizes the entire sales and commission workflow.

The system enables the cashier to quickly record completed transactions while automatically calculating commissions and generating accurate reports for the business owner.

The solution focuses on improving operational efficiency, maintaining data accuracy, and supporting better business decision-making.

---

# Objectives

The MVP aims to:

- Replace handwritten sales logs.
- Automate commission computation.
- Reduce operational errors.
- Support both service and product sales.
- Preserve historical commission records.
- Generate daily and monthly reports.
- Improve business visibility through centralized data.

---

# Target Users

| User | Responsibilities |
|-------|------------------|
| **Owner** | Reviews reports, monitors revenue, manages services, and oversees business performance. |
| **Cashier** | Records completed sales, processes transactions, and performs daily closing. |

---

# Core Features

### Authentication

- Secure login
- Role-based access

### Sales Management

- Record completed services
- Record product sales
- Support multiple items per customer transaction

### Commission Management

- Automatic commission calculation
- Percentage-based commissions
- Fixed commission support
- Historical commission preservation

### Reporting

- Daily Sales Report
- Monthly Sales Report
- Commission Breakdown
- Revenue Summary

### Service Management

- Manage available services
- Flexible pricing
- Product management

---

# Business Rules

The application follows the existing business rules of the salon.

### Haircuts

- 50% Barber
- 50% Owner

### Services Using Salon Products

Examples:

- Hair Color
- Hair Treatment
- Rebond

Commission:

- 40% Stylist
- 60% Owner

### Product Sales

Products such as Hair Wax provide a fixed commission to the employee who sold the item.

Additional rules:

- Prices may be manually adjusted depending on the service.
- Every sale item belongs to only one barber or stylist.
- Sales cannot be modified after being saved.
- Historical commission values must never change after recording.

---

# Business Value

The system is expected to improve both operational efficiency and business decision-making.

Benefits include:

- Faster daily closing
- Automated commission computation
- Reduced human error
- Better financial visibility
- Reliable historical records
- Standardized business processes
- Improved scalability for future expansion

---

# Success Metrics

The MVP will be considered successful if:

- Sales can be recorded in under **30 seconds**.
- Commission calculations are fully automated.
- Daily reports are generated instantly.
- Manual calculator usage is eliminated.
- End-of-day reconciliation is significantly faster than the current manual process.

---

# Technology Stack

| Layer | Technology |
|---------|------------|
| Backend | Python, Flask |
| Frontend | HTML, CSS, JavaScript, Bootstrap |
| Database | PostgreSQL |
| Deployment | Render |
| Version Control | Git & GitHub |

---

# Repository Structure

```
backend/
frontend/
database/
docs/
tests/
assets/
```

---

# Documentation

This repository follows a product-first development process.

Documentation is treated as a core project asset rather than an afterthought.

Included documentation:

- Business Requirements Specification (BRS)
- Product Requirements Document (PRD)
- User Personas
- User Stories
- Database Design
- API Design
- Wireframes
- Sprint Documentation
- Test Cases
- Development Journal
- Portfolio Case Study

---

# Product Development Journey

Unlike a typical academic software project, this repository documents the complete software product lifecycle.

Every major phase is documented to demonstrate how a real business problem is translated into a working software solution.

Development Phases:

1. Discovery
2. Planning
3. Design
4. Development
5. Testing
6. Deployment
7. Retrospective

---

# Project Roadmap

| Phase | Status |
|---------|--------|
| Discovery | ✅ Completed |
| Planning | 🚧 In Progress |
| Design | ⏳ Planned |
| Development | ⏳ Planned |
| Testing | ⏳ Planned |
| Deployment | ⏳ Planned |
| Retrospective | ⏳ Planned |

---

# Current Status

The project is currently focused on understanding the business before implementation.

Current activities include:

- Business analysis
- Requirements gathering
- Product planning
- Documentation
- System design

Development will begin only after the product requirements have been fully defined.

---

# Future Enhancements

Potential improvements after the MVP include:

- Inventory Management
- Appointment Booking
- Customer Profiles
- Customer History
- Analytics Dashboard
- Exportable Reports
- Audit Logs
- Multi-Branch Support
- AI-powered Business Insights

---

# Screenshots

Screenshots will be added as development progresses.

---

# System Architecture

Architecture diagrams will be included during the design phase.

---

# Development Philosophy

This project is intentionally being developed as if it were a real software product.

Instead of immediately writing code, the development process begins with understanding the business, identifying user needs, defining requirements, and validating product decisions.

The objective is not simply to build a working application, but to demonstrate the complete process of turning a real-world business problem into a maintainable software solution.

---

# About This Repository

This repository serves two purposes:

1. Develop an internal business management system for a real barbershop and salon.
2. Document the complete product development lifecycle—from discovery and planning to deployment and retrospective.

The final result is intended to demonstrate both software engineering fundamentals and product management thinking.

---

# Author

**Rafael Hidalgo**

Second-Year Computer Science Student  
Specialization in Artificial Intelligence

Aspiring AI Product Manager

Building software with a product-first mindset by combining business analysis, software engineering, and AI-assisted development.