# Release Workflow

## Steps

1. **Pre-release checks** — Run `/pre-release` skill (tests, linting, git status)
2. **Commit** — Stage and commit any pending changes with appropriate message
3. **Database migrations** — Run on all 4 databases in sequence:
   - Staging US → Staging EU → Production US → Production EU
   - Connect to each database using your infrastructure's connection method
   - Credentials from environment variables or secret manager
4. **Deploy staging** — Run `./infra/deploy-staging-fresh.sh` (builds + deploys)
5. **Verify staging** — Health check staging URLs, ask user to verify
6. **Release notes approval** — Generate release notes and present to user for review/approval BEFORE tagging
7. **Publish release notes** (ALL THREE — do NOT skip any):
   a. **Content markdown** — Create `{frontend_dir}/content/releases/{date}-v{version}.md` with frontmatter (version, date, title, highlights) + body markdown. This is the SOURCE OF TRUTH — `releases.json` is generated from these during `npm run build`.
   b. **GitHub Release** — `gh release create v{version} --title "..." --notes "..."`
   c. **LLM changelog** — Update `{frontend_dir}/public/llm-content/changelog.md` with the new entry
8. **Rebuild frontend** — `npm run build` in `{frontend_dir}/` (regenerates `releases.json` from content/releases/)
9. **Tag and push** — Create annotated git tag (`vX.Y.Z`), push tag to origin
10. **Deploy frontend** — `npx wrangler pages deploy out --project-name={frontend_project} --branch=main`
11. **Pipeline deploys production** — Pushing the tag triggers Cloud Build pipeline automatically:
    - `cloudbuild.yaml` builds the Docker image
    - Pipeline triggers `{deploy_trigger_name}` deploy trigger
    - Deploy requires **manual approval** in Cloud Console
    - Pipeline deploys to US, then EU, updates backend URLs, runs health checks
12. **Linear milestone + issue cleanup** —
    - List all Linear issues completed since last release: `mcp__linear-server__list_issues(state="Done", updatedAt="-P7D")`
    - Verify all are closed. Close any that were fixed but left open.
    - Update relevant milestone with release version comment: `mcp__linear-server__save_comment` on milestone-linked issues
    - Link release to milestone: `mcp__linear-server__save_milestone(project="{product_platform_project}", id="<milestone>", description="Updated: v{version} released")`
13. **Report** — Provide Cloud Console link for deploy approval + final status
14. **Stripe production health check** (if billing code changed) — After production deploy is approved:
    ```bash
    # Verify Stripe webhook endpoint is active with correct URL
    STRIPE_KEY=$(gcloud secrets versions access latest --secret="STRIPE_API_KEY" --project="{gcp_project_id}")
    curl -s "https://api.stripe.com/v1/webhook_endpoints?limit=10" -u "$STRIPE_KEY:" | \
      python3 -c "import json,sys; [print(f'{e[\"url\"]} status={e[\"status\"]} events={len(e[\"enabled_events\"])}') for e in json.load(sys.stdin).get('data',[])]"

    # Verify production health returns correct version
    curl -s https://{production_api}/v1/health

    # Test subscription status endpoint (production)
    # Use the same auth recipe as pre-release (Firebase → JWT → headers)
    ```
    If webhook endpoint is disabled or version mismatch, investigate before continuing.
15. **Post-release production monitoring** — Start a monitoring loop using `/loop`:
    ```
    /loop 30m Monitor production health after v{version} release. Check:
    1. Cloud Run service status (US: {cloud_run_service_us} in us-central1, EU: {cloud_run_service_eu} in europe-west1)
    2. Cloud Run logs for ERROR/CRITICAL entries (mcp__cloudrun__get_service_log)
    3. Compare error patterns to pre-release baseline
    If errors found: investigate root cause, attempt fix, deploy hotfix if needed.
    If healthy: report "v{version} healthy — no issues detected" and continue.
    After 6 iterations (3 hours): stop loop and report final status.
    --max-iterations 6
    ```
    - Runs every 30 minutes for 3 hours (6 iterations)
    - Each iteration checks both US and EU production services
    - On error detection: investigate logs, identify root cause, fix and deploy hotfix if critical
    - On clean iterations: brief "healthy" confirmation
    - After 3 hours: final summary with error count, response times, any actions taken

## CRITICAL RULES

- **NEVER manually deploy to production** — only the pipeline deploys production
  - Do NOT run `gcloud builds submit --config=cloudbuild-deploy.yaml`
  - Do NOT run `gcloud run deploy` directly for production services
  - The ONLY way to deploy production is: push tag → pipeline builds → pipeline deploys
- **Release notes MUST be approved by user** before creating the tag
- **Release notes MUST be published to ALL THREE locations** — content/releases/ markdown, GitHub Release, LLM changelog
- **Frontend MUST be deployed** after release notes are published (changelog page reads from generated releases.json)
- **Staging deploy uses** `./infra/deploy-staging-fresh.sh` (NOT `cloudbuild-deploy-staging.yaml`)
- **Report status after each step** — don't batch silently

## Release Notes — Content Markdown Format

Source of truth: `{frontend_dir}/content/releases/{date}-v{version}.md`

```markdown
---
version: "{version}"
date: "{date}"
title: "{title}"
highlights:
  - "{highlight 1}"
  - "{highlight 2}"
---

### {Section Title}

{Description paragraph}

### Bug Fixes

- {fix 1}
- {fix 2}
```

The build step (`npm run build`) runs `generate-content.ts` which converts these markdown files into `lib/generated/releases.json`. Do NOT edit `releases.json` directly — it will be overwritten on next build.

## Release Notes — Approval Template

Present to user for approval (no GH issue numbers, no Technical Changes section unless requested):

```markdown
## v{version} - {date}

### What's New
- {feature 1}
- {feature 2}

### Bug Fixes
- {fix 1}
```

### What to EXCLUDE from release notes

Release notes are **user-facing**. Only include changes the user would notice in the product. Exclude:

- **Features in soft-launch / beta** — announce separately when ready for spotlight (e.g., new integrations not yet publicly promoted)
- **Internal UX iterations** — onboarding tweaks, A/B test variants, funnel optimizations. Users experience the result, not the process.
- **Marketing infrastructure** — landing pages, ad tracking, CPC pages, SEO content, sitemap regeneration. Serves acquisition, not existing users.
- **Infrastructure / DevOps fixes** — DB connections, logging, middleware, structured logging, request tracing. Invisible to end users unless it was a user-reported outage.
- **i18n/locale updates** — translation syncs, dictionary updates, locale file changes
- **LLM content changes** — blog posts, SEO pages, comparison pages
- **Internal tooling** — removed internal modules, infra config changes
- **Pipeline/service internals** — background job tuning, retry logic tweaks, sync service changes
- **Email/notification content updates** — these are internal content, not features

**Rule of thumb**: If the user wouldn't notice the change in the app, don't list it.

## Post-Release Production Monitoring

After the release is deployed and approved, start a `/loop` to monitor production for 3 hours.

### What to check each iteration

1. **Service health** — Verify both Cloud Run services are Ready:
   ```bash
   gcloud run services describe {cloud_run_service_us} --region=us-central1 --project={gcp_project_id} --format="value(status.conditions[0].status)"
   gcloud run services describe {cloud_run_service_eu} --region=europe-west1 --project={gcp_project_id} --format="value(status.conditions[0].status)"
   ```

2. **Error logs** — Check BOTH severity-tagged AND structured JSON errors. Cloud Run with Python structured logging often tags errors as `severity=DEFAULT`, so `severity>=ERROR` alone misses them. Run ALL THREE queries per region:
   ```bash
   # Query A: Severity-tagged errors (standard)
   gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="{cloud_run_service_us}" AND severity>=ERROR AND timestamp>="DEPLOY_TIMESTAMP"' --project={gcp_project_id} --limit=20 --format="json"

   # Query B: Structured JSON errors (Python logger.error → jsonPayload)
   gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="{cloud_run_service_us}" AND (jsonPayload.message=~"error|Error|failed|Failed|exception|Exception" OR jsonPayload.message=~"connection is closed|Traceback") AND timestamp>="DEPLOY_TIMESTAMP"' --project={gcp_project_id} --limit=20 --format="json"

   # Query C: Text payload errors (unstructured logs)
   gcloud logging read 'resource.type="cloud_run_revision" AND resource.labels.service_name="{cloud_run_service_us}" AND (textPayload=~"error|Error|Traceback|500|connection is closed") AND timestamp>="DEPLOY_TIMESTAMP"' --project={gcp_project_id} --limit=20 --format="json"
   ```
   Run the same 3 queries for `{cloud_run_service_eu}`.

   **Parse results as JSON** — use `--format="json"` and extract with Python:
   ```bash
   ... | .venv/bin/python -c "
   import json,sys
   entries = json.load(sys.stdin)
   for e in entries:
       ts = e.get('timestamp','')
       sev = e.get('severity','')
       msg = e.get('textPayload','') or e.get('jsonPayload',{}).get('message','') or str(e.get('jsonPayload',{}))[:300]
       if msg: print(f'{ts} [{sev}] {msg[:300]}')
   "
   ```

   - Replace `DEPLOY_TIMESTAMP` with the actual deploy time in RFC3339 format
   - Ignore known benign patterns (e.g., cold start warnings, health check 404s, Firestore database-not-found for welcome email tracker)

3. **Error classification** — For each error found:
   | Severity | Pattern | Action |
   |----------|---------|--------|
   | **CRITICAL** | Crash loops, OOM, unhandled exceptions, auth failures | Investigate immediately, attempt hotfix, notify user |
   | **HIGH** | Repeated 5xx on user-facing endpoints, DB connection failures | Investigate root cause, assess if hotfix needed |
   | **MEDIUM** | Intermittent errors, third-party timeouts | Log for next sprint, continue monitoring |
   | **LOW** | Deprecation warnings, non-critical retries | Note in final report only |

### Hotfix protocol (if critical/high errors detected)

1. Diagnose root cause from logs
2. Write fix + test (TDD)
3. Bump patch version (e.g., 2.1.4 → 2.1.5)
4. Deploy staging via `./infra/deploy-staging-fresh.sh`
5. Verify fix on staging
6. Tag + push (triggers production pipeline)
7. Resume monitoring loop

### Loop invocation

```
/loop 30m Monitor production after v{version} release. For each check:
1. gcloud run services describe for US + EU (must be Ready)
2. Search logs with THREE queries per region (severity>=ERROR, jsonPayload.message=~"error|failed|exception|connection is closed", textPayload=~"error|Traceback|500"). Use --format="json" and parse with Python to extract timestamp+severity+message. Do NOT rely on severity>=ERROR alone — Python structured logging often tags errors as DEFAULT.
3. Classify any errors: CRITICAL → fix immediately, HIGH → investigate, MEDIUM/LOW → note
4. Report: "v{version} iteration N/6 — [healthy|N errors found]"
After 6 iterations (3 hours) or if all clean: final summary.
--max-iterations 6
```

## Database Migration Details

Run migrations against each database in order (staging first, then production with backups).
Adapt the connection method to your infrastructure (e.g., direct connection, SSH tunnel, or cloud proxy).

```bash
# Generic pattern — adapt to your database setup:
# 1. Establish connection to database
# 2. Run migrations
POSTGRES_HOST={db_host} POSTGRES_PORT={db_port} \
  POSTGRES_USER={db_user} POSTGRES_PASSWORD='{db_password}' \
  POSTGRES_DB={db_name} \
  python -m alembic upgrade head
# 3. Close connection before moving to next database
```
