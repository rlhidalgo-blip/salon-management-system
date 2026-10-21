# Yab's Salon Management System — UI Design System

## Document Information

| Field | Value |
|---|---|
| Project | Yab's Salon Management System |
| Document | UI Design System |
| Version | 1.0 |
| Status | Approved — Initial Visual Direction |
| Last Updated | October 21, 2026 |

## 1. Design Philosophy

The interface follows a Warm Luxury Minimalist visual direction inspired by Yab's Hair and Beauty Studio's existing gold-script logo.

The application should feel elegant, professional, welcoming, and efficient for daily salon operations.

Prioritize usability, readability, and consistency over decorative effects.

Avoid generic AI-generated dashboard patterns, excessive gradients, unnecessary illustrations, oversized cards, and ornamental elements without functional purpose.

## 2. Brand Identity

Use the salon's existing logo as the primary brand asset.

The logo must retain its original proportions and must not be stretched, recolored, or redesigned without approval.

Use gold accents sparingly to reinforce brand identity.

## 3. Color Tokens

### Light Theme

| Token | Value |
|---|---|
| Background | `#FAF8F5` |
| Surface | `#EFE8DD` |
| Primary Accent | `#C9A96A` |
| Secondary Accent | `#8E6F3E` |
| Primary Text | `#2B2723` |

### Dark Theme

| Token | Value |
|---|---|
| Background | `#211E1B` |
| Surface | `#302B26` |
| Primary Accent | `#C9A96A` |
| Secondary Text | `#B7A58D` |
| Primary Text | `#F5F0E8` |

Additional semantic colors for errors, success, warnings, borders, and muted text must be selected for accessible contrast and documented before widespread use.

## 4. Typography

- Display headings: Playfair Display.
- Interface text: Inter.
- Use display typography selectively.
- Use readable sans-serif typography for forms, tables, financial values, and navigation.
- Avoid decorative script fonts for functional interface text.

## 5. Layout and Components

- Use consistent spacing and alignment.
- Prefer subtle borders and restrained shadows.
- Use moderate corner radii rather than exaggerated rounding.
- Keep forms compact and clearly labeled.
- Use gold primarily for important interactive elements and selected states.
- Ensure financial tables remain readable and easy to scan.
- Avoid decorative components that distract from salon operations.

## 6. Light and Dark Mode

The application must support both light and dark themes.

Requirements:

1. Follow the operating system theme on first visit.
2. Provide a visible theme toggle.
3. Save the user's explicit preference in localStorage.
4. Preserve the preference across reloads.
5. Apply themes through CSS variables.
6. Keep the same interface structure in both themes.
7. Maintain accessible contrast.
8. Do not store authentication credentials or session tokens in localStorage.

## 7. Accessibility and Responsiveness

- Use semantic HTML.
- Provide visible keyboard focus indicators.
- Label all form fields.
- Support keyboard navigation.
- Maintain readable text and control contrast.
- Adapt layouts to desktop and smaller screens without horizontal overflow.
- Respect reduced-motion preferences.

## 8. Implementation Rules

Codex must follow this document and approved screen references when implementing frontend components.

Do not independently redesign approved layouts, colors, typography, or branding.

Do not add unapproved business features.

When a design decision is missing, propose options and request approval before making major visual changes.

## 9. Initial Screen Priority

1. Owner/Cashier login screen.
2. Authenticated application shell.
3. Owner dashboard.
4. Cashier transaction interface.
5. Staff and catalog management.
6. Reporting interfaces.

Each screen requires design review before implementation.