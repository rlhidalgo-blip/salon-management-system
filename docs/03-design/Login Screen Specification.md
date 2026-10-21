# Login Screen Specification — Yab's Salon Management System

## Document Information

| Field | Value |
|---|---|
| Project | Yab's Salon Management System |
| Document | Login Screen Specification |
| Version | 1.1 |
| Status | Approved — Centered Minimalist Layout |
| Last Updated | October 21, 2026 |
| Supersedes | Version 1.0 — Split-Screen Login |

## 1. Purpose

Define the approved appearance, layout, responsive behavior, and interaction states of the Owner/Cashier login interface.

This specification follows the approved `UI Design System.md` and the original Yab's Hair and Beauty Studio branding.

## 2. Visual Direction

The login interface follows a **Centered Minimalist** layout with a Warm Luxury Minimalist visual identity.

The design must feel professional, elegant, welcoming, uncluttered, and suitable for an internal salon management application.

Prioritize readability, simplicity, and usability.

Avoid generic AI-generated dashboard styling, excessive gradients, glassmorphism, large decorative cards, unnecessary imagery, and exaggerated visual effects.

## 3. Layout

### Desktop

- Use a single-column login layout.
- Center the primary login content horizontally and approximately vertically within the viewport.
- Maximum form width: approximately 400–420px.
- Maintain balanced spacing between logo, heading, fields, and actions.
- Use the approved theme background across the entire viewport.
- Do not create a separate image panel or split-screen layout.
- Do not surround the entire form with a large decorative card unless separately approved.

### Tablet and Mobile

- Preserve the same single-column structure.
- Reduce horizontal padding on narrow screens.
- Keep inputs and buttons comfortable for touch interaction.
- Ensure the form remains fully usable with the mobile keyboard open.
- Avoid horizontal scrolling.
- Maintain visible focus indicators and accessible labels.

## 4. Brand Logo

Use the existing manually prepared transparent Yab's logo from the frontend assets.

Requirements:

- Preserve the original gold lettering and details.
- Do not redraw, recolor, distort, or regenerate the logo.
- Display the logo above the welcome heading.
- Use proportional sizing with `object-fit: contain`.
- Keep the logo prominent without overpowering the form.
- Ensure it remains visible in both light and dark themes.

## 5. Typography

- Playfair Display for the welcome heading.
- Inter for form labels, buttons, descriptions, and validation messages.
- Use a clear visual hierarchy.
- Avoid decorative typography for functional UI elements.

## 6. Theme and Colors

Use the approved Light and Dark Mode tokens from `UI Design System.md`.

### Light Mode

- Warm ivory page background.
- Charcoal primary text.
- Cream or white input surfaces.
- Champagne-gold primary action.
- Subtle neutral borders.

### Dark Mode

- Deep charcoal page background.
- Soft ivory primary text.
- Dark brown input surfaces.
- Muted champagne-gold primary action.
- Subtle dark neutral borders.

### Theme Behavior

- Follow system preference initially.
- Provide a visible, accessible theme toggle.
- Persist only the user's explicit theme preference in localStorage.
- Keep the layout consistent across themes.
- Maintain accessible text and control contrast.

## 7. Required UI Elements

1. Original Yab's logo.
2. Welcome back heading.
3. Supporting sign-in text.
4. Username input with visible label.
5. Password input with visible label.
6. Password visibility toggle.
7. Primary Sign In button.
8. Accessible validation and error-message region.
9. Light/Dark Mode toggle.
10. Authorized-staff footer.

Do not add Remember Me, self-registration, social login, or password reset without separate approval.

## 8. Form Interaction States

### Default

The form begins with empty username and password inputs.

### Validation

Required fields must display accessible validation messages when the user attempts an invalid submission.

### Password Visibility

The user can toggle password visibility without changing the entered value.

### Loading

The Sign In button displays a loading indicator and prevents repeated submission while processing.

### Authentication Error

Display a generic error that does not reveal whether the username or password is incorrect.

### Server or Network Error

Display a helpful generic message and allow retrying.

### Successful Authentication

Navigation to the authenticated application shell will be implemented in Sprint 3D.

## 9. Accessibility

- Use semantic HTML.
- Associate visible labels with inputs.
- Support keyboard navigation.
- Provide visible focus indicators.
- Use accessible status and error messages.
- Respect reduced-motion preferences.
- Maintain readable contrast in both themes.

## 10. Security and API Boundary

Sprint 3C implements only the visual interface and local form behavior.

The live FastAPI authentication integration belongs to Sprint 3D.

Do not store passwords, raw session tokens, or CSRF tokens in localStorage.

Preserve the existing HttpOnly cookie authentication architecture.

## 11. Implementation Restrictions

Codex must:

- Remove the previous split-screen layout.
- Remove the unused decorative salon-photo panel and placeholder.
- Reuse the existing React components and theme utilities where appropriate.
- Preserve the original transparent logo.
- Follow the approved UI Design System.
- Avoid adding unapproved visual elements or business features.
- Avoid modifying backend or database code.

## 12. Acceptance Criteria

- Centered single-column login layout on desktop, tablet, and mobile.
- No decorative right-side panel.
- Original gold logo displayed correctly.
- Light and dark themes work.
- Form remains readable and usable across supported screen sizes.
- Accessible validation, password visibility, and loading states work.
- No authentication API calls are introduced in Sprint 3C.
- Frontend build succeeds.