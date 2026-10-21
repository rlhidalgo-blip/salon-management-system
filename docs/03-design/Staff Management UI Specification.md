# Staff Management UI Specification — Yab's Salon Management System

## Document Information

| Field | Value |
|---|---|
| Project | Yab's Salon Management System |
| Version | 1.0 |
| Status | Approved — Initial UI Direction |
| Date | October 21, 2026 |

## 1. Purpose

Define the visual layout, behavior, accessibility, and responsive requirements of the Owner-only Staff Management interface.

Follow the approved `UI Design System.md` and existing React application architecture.

## 2. Scope

The interface supports:

- Viewing active and inactive staff.
- Adding a Barber or Stylist.
- Activating staff.
- Deactivating staff.

Excluded:

- Editing staff names.
- Changing staff roles after creation.
- Deleting staff records.
- Employee profiles, schedules, payroll, or HR features.

## 3. Desktop Layout

Use a clean, compact table layout.

Page header:

- Title: Staff Management.
- Supporting text: Manage your barbers and stylists.
- Primary action: Add Staff.

Table columns:

1. Name
2. Role
3. Status
4. Action

Rows should have comfortable spacing and subtle separators.

Avoid excessive card borders, gradients, shadows, and unnecessary decorative elements.

## 4. Search and Filtering

Provide:

- Client-side search by staff name.
- Status filter: All, Active, Inactive.
- Default ordering by staff ID ascending.

Filtering must not modify database records.

Provide an appropriate empty state when no records match the selected filters.

## 5. Add Staff

Use an accessible modal dialog or similarly compact form.

Fields:

- Staff Name — required, nonblank.
- Role — required, Barber or Stylist.

New staff members are active by default.

The dialog must support:

- Save and Cancel.
- Required-field validation.
- Loading state.
- Generic server error handling.
- Keyboard navigation and focus management.

Do not introduce additional staff fields.

## 6. Activation and Deactivation

Each staff row provides one status-changing action:

- Active staff: Deactivate.
- Inactive staff: Activate.

Require explicit confirmation before deactivation to prevent accidental changes.

Activation may proceed directly with clear feedback.

Successful changes must update the displayed status.

Historical transaction and commission references must remain unchanged.

## 7. Theme

Follow the approved Warm Luxury Minimalist design system.

Light mode:

- Warm ivory page background.
- Subtle cream or white table surface.
- Charcoal text.
- Champagne-gold primary actions.

Dark mode:

- Deep charcoal background.
- Dark brown table surface.
- Soft ivory text.
- Muted gold primary actions.

Use semantic status colors with accessible contrast.

## 8. Mobile Responsiveness

For narrow screens:

- Display staff as compact stacked rows.
- Show name, role, status, and action.
- Keep Add Staff easily accessible.
- Preserve search and status filtering.
- Avoid horizontal scrolling where practical.
- Ensure controls remain touch-friendly.

## 9. Accessibility

- Use semantic HTML.
- Use proper table headers on desktop.
- Label search and form inputs.
- Provide keyboard-operable actions.
- Manage modal focus appropriately.
- Use visible focus indicators.
- Announce loading, errors, and successful actions accessibly.
- Do not rely on color alone to communicate staff status.

## 10. Security and API Integration

The Staff Management interface is Owner-only.

Use the existing authenticated session and backend RBAC.

Approved endpoints:

- GET `/api/v1/staff`
- POST `/api/v1/staff`
- PATCH `/api/v1/staff/{staff_id}/status`

Use the existing HttpOnly cookie architecture.

State-changing requests must include the approved CSRF header and rely on browser-generated Origin.

Do not store authentication tokens in browser storage.

## 11. UI States

The interface must handle:

- Initial loading.
- Successful staff list retrieval.
- Empty staff list.
- No search/filter matches.
- Adding staff.
- Activation/deactivation.
- Validation errors.
- Network/server errors.
- Unauthorized or expired sessions.
- Forbidden access.

## 12. Implementation Boundaries

Codex must not:

- Redesign the approved login screen.
- Modify backend database schemas.
- Add unapproved staff fields.
- Add name/role editing or deletion.
- Invent dashboard statistics.
- Introduce unnecessary frontend libraries.
- Commit or push without approval.

## 13. Acceptance Criteria

- Clean desktop staff table.
- Responsive mobile staff rows.
- Add Staff form.
- Activate/deactivate actions.
- Client-side search and status filtering.
- Light/dark support.
- Accessible states and interactions.
- Owner-only access.
- Existing authentication preserved.
- Frontend tests and build pass.