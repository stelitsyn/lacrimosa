# File → Flow Impact Map

> Map changed files to affected user flows. Use with `git diff --name-only` output.
> **Customize this map for your product's file structure and user flows.**

## Direct Impact

| Changed File Pattern | Affected Flows |
|---------------------|----------------|
| `<auth-components>`, `<auth-hooks>` | Auth (signup, sign-in, password reset) |
| `<auth-api-routes>` | Auth backend |
| `<onboarding-steps>` | Onboarding |
| `<main-feature-components>` | Core product flow |
| `<dashboard-components>` | Dashboard / overview |
| `<settings-components>` | User settings |
| `<billing-components>` | Billing / subscription |
| `<layout-components>` | All pages (global layout) |
| `<i18n-files>` | All flows (translation changes) |
| `<style-config>`, `<global-styles>` | All flows (visual regression) |

## Indirect Impact

| Changed File Pattern | Check Also |
|---------------------|------------|
| `<api-client>` | Any flow that calls the backend |
| `<middleware>` | Auth redirects, locale detection |
| `<package-manifest>` | Build, deps — full regression |

## How to Use

1. Run `git diff --name-only main...HEAD`
2. Match against table above
3. Run verify-flows for all matched flows
4. For "All flows" matches, run full regression

## How to Customize

Replace `<placeholder>` patterns with your actual file paths. Example:

```
| `src/components/Auth/*.tsx` | Auth flows |
| `src/pages/dashboard/**` | Dashboard |
```
