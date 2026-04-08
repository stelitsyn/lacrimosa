# Regression UI Test Library

> Canonical reference for expected visual state, i18n content, and logic checks across all major {product_name} UI flows.
> Used by QA agents during pre-release, Lacrimosa browser testing, and `/verify-flows`.
>
> **Customize this file for your product's UI flows, components, and i18n content.**

---

## Template: Flow Test Section

For each major UI flow, create a section following this structure:

### Visual Elements

| Selector / Locator | Element | Expected Content |
|---|---|---|
| `.page-header` | Page title | Flow-specific heading |
| `.main-content` | Primary content area | Expected layout description |
| `.action-button` | Primary CTA | Button label |

### i18n Content

| Key Path | EN | ES | DE |
|---|---|---|---|
| `flow.title` | English title | Spanish title | German title |
| `flow.description` | English desc | Spanish desc | German desc |

### Logic Checks

- [ ] Expected elements render correctly
- [ ] Actions trigger expected state changes
- [ ] Loading states display during async operations
- [ ] Error states handle failures gracefully

### Negative Checks

- [ ] No broken layouts at mobile widths
- [ ] No missing translations
- [ ] No stale data after navigation

---

## Example Flows to Cover

1. **Authentication** — login, signup, password reset, email verification
2. **Onboarding** — welcome, feature tour, first action
3. **Main interaction** — core product flow
4. **Dashboard** — overview, stats, recent activity
5. **Settings** — profile, preferences, billing
6. **History** — past interactions, filtering, detail view

---

## How to Add a New Flow

1. Copy the template section above
2. Fill in selectors, expected content, and i18n strings from your components
3. Add logic checks specific to the flow's state management
4. Add negative checks for edge cases
5. Keep i18n tables in sync with your translation files
