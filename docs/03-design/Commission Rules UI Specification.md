# Commission Rules UI Specification — Yab's Salon Management System

| Field | Value |
|---|---|
| Version | 1.0 |
| Status | Approved Sprint 5B implementation direction |
| Date | October 23, 2026 |

## Purpose and scope

Provide an Owner-only interface to list, create, activate, and deactivate commission rules. Rule name, type, and value are immutable after creation. Editing, deletion, catalog assignment, commission calculations, and dashboard features are outside this screen.

## Owner application layout

Keep the existing compact authenticated header, original Yab's logo, role, theme toggle, and Logout. Immediately below it, show two section controls: Staff (default) and Commission Rules. Show only one management section at a time. Keep the selection in React memory, without new routes or browser storage. Cashier users retain their existing minimal authenticated view and cannot access either Owner management section.

Follow the approved Warm Luxury Minimalist UI Design System and Staff Management patterns: aligned content width, restrained surface and spacing, light/dark themes, visible focus, and mobile-friendly controls. Do not redesign the approved login interface.

## Commission Rules view

Show a page title, Add Rule action, and a table with Name, Type, Value, Status, and Action. Include active and inactive rules. Display Percentage values with `%` and Fixed values with `₱`. On narrow screens, show compact stacked rows without horizontal overflow. Provide loading, empty, error, and success states.

## Add Rule

Use an accessible dialog with Rule Name, Type (Percentage or Fixed), Value, Save, and Cancel. Name must be nonblank. Value is entered as a decimal string: greater than zero, at most two decimal places, at most ten integer digits, and no more than 100 for Percentage. New rules are active by default. Prevent duplicate submissions; announce validation and server errors. The backend remains authoritative for validation.

## Status changes

Allow direct activation. Require confirmation before deactivation. If deactivation returns HTTP 409, leave the displayed rule active and explain that an active Service or Product still references it. Do not alter historical transaction snapshots.

## Security and integration

Use the existing Owner-only backend API: `GET /api/v1/commission-rules`, `POST /api/v1/commission-rules`, and `PATCH /api/v1/commission-rules/{rule_id}/status`. Send same-origin browser credentials; POST/PATCH include the in-memory CSRF token and rely on browser Origin handling. Never read the HttpOnly session cookie or store authentication tokens in browser storage. Revalidate the session on 401, show 403 as a permission error, and handle 422 and temporary server/network failures without exposing sensitive details.

## Verification

Automated frontend tests cover Owner/Cashier isolation, section switching, list/empty state, decimal validation, create/status actions, confirmation, 409, security headers, error states, and duplicate-submit prevention. Run the frontend tests and production build. Live desktop/mobile, theme, and keyboard behavior still require browser verification.
