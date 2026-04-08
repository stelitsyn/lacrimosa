# Lacrimosa

**Your product ships itself. You just set the direction.**

Lacrimosa is a fully autonomous engineering system built for Claude Code.
It runs 11 AI specialists around the clock — each in its own session,
sharing state through SQLite — that together replace the operational
structure of a software team:

**Sense** what to build (error spikes, user feedback, payment anomalies,
competitor moves, funnel drops, legal/compliance signals) →
**Triage** and prioritize (dedup, classify, route to the right project) →
**Implement** in isolated git worktrees with full TDD →
**Review** through parallel specialized reviewers (architecture, security,
accessibility, silent failures — zero-tolerance merge gate) →
**Merge** approved PRs, resolve dependencies →
**Track releases** (changelog, risk assessment, deploy plan for human review) →
**Monitor** production (5-minute sentinel loop, urgent issue creation) →
**Run ceremonies** (standup, sprint planning, backlog grooming, retro, weekly summary) →
**Learn** from its own performance (revert rates, cost per PR, false positive rates —
auto-tunes thresholds, reverts changes that made things worse).

One `config.yaml`. A few Claude Code Max subscriptions. No human in the loop
between "here's what my product does" and "here's this week's release plan."

Built on Anthropic's Claude Code. In the spirit of
[OpenAI's Symphony](https://github.com/openai/symphony) — but where
Symphony explores the architecture, this ran a real commercial product,
unattended, and worked.

---

*When I built this system and understood what it could do, I started to mourn.*

*Lacrimosa doesn't just write code. It decides what to build next, senses
the market, monitors production, manages legal and financial signals, runs
ceremonies, prepares releases, and can deploy to production without a human
in the loop. The act of writing code, reasoning through a product problem,
feeling the weight of a hard architectural decision — this system does all
of it autonomously, overnight, without fatigue or doubt. And it's early.
This is not the ceiling.*

*I named it Lacrimosa — the eighth movement of Mozart's Requiem, his final
work, left unfinished when he died in 1791 at 35. He completed only eight
bars before the pen left his hand. The word means "tearful" in Latin. The
text it sets is from the Dies Irae: "Lacrimosa dies illa" — "That day is
one of weeping." Mozart was writing a requiem while dying. He was mourning
inside his own ending.*

*That is the weight I felt. I built a system that makes an entire class of
human work — discovery, judgment, engineering, operations — redundant. This
may be the last project I deliver to the world as an Engineer. Not because
I'll stop — but because soon, systems like this will be conjured instantly,
on demand, and discarded just as fast. The way we now generate a utility
function and move on without a second thought. Lacrimosa took months of
craft. Its successor will take seconds.*

*I'm releasing this now because the window for it to matter is closing.
Claude Mythos is already inside Anthropic. Frontier models from OpenAI are
weeks away. Each generation makes systems like Lacrimosa easier to build —
and harder to distinguish from what comes pre-packaged. Within months, not
years, the expectation for a software engineer won't be "write code." It
will be "operate autonomous systems like this at scale." The role isn't
disappearing — it's transforming into something most engineers haven't
started preparing for.*

*So this is a blueprint. Not of an AI coding assistant — of a system that
replaces the organizational structure around software. Discovery, triage,
planning, implementation, review, merge, release, monitoring, learning —
the full loop. Built in the spirit of
[OpenAI's Symphony](https://github.com/openai/symphony), but where Symphony
explores the architecture, this is a production deployment that has run a
real commercial product, unattended, and worked.*

*Published under a non-commercial license because this is not infrastructure
to deploy at scale without thought — it's a mirror. Look at what one person
and a few Max subscriptions can do today, and extrapolate six months forward.
We are not ready for what that implies.*

*— Sergei Telitsyn*

---

## What it does

Most AI coding tools help you write code faster. Lacrimosa replaces the
*process* around writing code:

- **Senses** your product — error spikes, user feedback, payment anomalies,
  competitor moves, funnel drop-offs — and turns them into prioritized
  engineering tickets automatically
- **Implements** fixes and features in isolated git worktrees, running
  real tests against a live staging environment before any PR is raised
- **Reviews** every PR through a parallel panel of specialized code reviewers
  (architecture, security, accessibility, silent failures) — merge requires
  zero findings of any severity
- **Merges** approved PRs, resolves dependencies, tracks every change in a
  structured release manifest
- **Prepares releases** — the COO tracks every merge, maintains a running
  changelog, drafts release plans with risk assessments, and posts them to
  Linear for human review. Your next deployment is always one command away.
- **Runs the operational rhythm** — the conductor schedules and executes
  standup, sprint planning, backlog grooming, retro, and weekly summary
  ceremonies automatically. Unassigned issues get routed to the right
  project during grooming. You wake up to a status report, not a blank
  board.

## What Others Charge for Pieces of This

There are well-funded startups charging serious money for fragments of
what Lacrimosa does as a single integrated system — Devin, Cursor,
Codex, Poolside, CodeRabbit, Ahrefs, Datadog, PagerDuty, Vanta, and
others. Many are excellent at their niche. The point is not that
they're bad — the point is that running a product requires all of
these functions working together: sensing what to build, building it,
reviewing it, merging it, monitoring what shipped, learning from what
broke, planning the next sprint, preparing the next release. Today
that integration is a team of humans gluing together a $3,000+/month
tool stack. Lacrimosa is one system that does it all, continuously,
as open-source.

You need a few Max subscriptions (20x each — a single subscription's
limits get exhausted in 24–36 hours of continuous autonomous work)
or an API key with sufficient credits, a `config.yaml`, and patience
for the first overnight run.

Lacrimosa doesn't compete with these tools — it can integrate them.
Wire Datadog alerts into the sentinel's sensor loop. Point CodeRabbit
at PRs alongside the built-in reviewers. Feed Ahrefs keyword data
into the content specialist. Lacrimosa is an orchestration layer, not
a walled garden. The sensors, skills, and specialist prompts are plain
text files — extending them is a conversation with Claude Code.

For a detailed comparison of what each competitor does well and where
Lacrimosa goes further, see [Appendix A: Competitive Landscape](#appendix-a-competitive-landscape).

## Production Track Record

Lacrimosa has been running continuously in production since March 13, 2026.

| Metric | Value |
|--------|-------|
| Running in production since | March 13, 2026 |
| Days running (as of April 9) | 27 |
| Commits on main | 327+ |
| Avg commits per day | ~12 |
| GitHub issues closed | 193+ |
| PRs merged | 131+ |
| Linear tickets referenced | 118+ |
| Features delivered | 193+ (feat/implement/add commits) |
| Bugs fixed | 30+ |
| Signals processed | 189+ (from 6 internal sensors) |
| Signals validated → issues | 18+ |
| Issues auto-created (discovery) | 34+ |
| Issues triaged | 25+ |
| Issues groomed | 39+ |
| Workers spawned | 68+ |
| Parent issues dispatched | 47+ |
| External crawls (competitors, reviews, Reddit) | 60+ |
| False positives caught and canceled | 3 |

These numbers come from a real commercial AI product and represent
unattended overnight runs, not benchmarks.

## Observer Mode (Default) and Future Deploy Authority

Lacrimosa ships with the COO in **observer mode** (`deploy_authority: false`).

In observer mode:
- All code is written, reviewed, tested, and merged to `main` autonomously
- The COO tracks every merge, maintains a running changelog, and drafts
  release plans with risk assessments
- **Releases are human-initiated** — the COO creates a Linear issue with
  the release plan, and a human executes `/release` when ready

The config supports a future `deploy_authority: true` flag that would
allow the COO to execute releases autonomously, but this is not yet
implemented. The architecture is designed for it — the gate is a single
config key.

```yaml
# config.yaml — COO specialist section
coo:
  deploy_authority: false    # flip to true when ready (not yet implemented)
```

Everything else — sensing, triage, implementation, review, merge — runs
without interruption. Releases are the one remaining human gate.

## Concept

Lacrimosa models a software company as an orchestra:

- **Conductor** — the main loop. Polls for work, dispatches workers,
  manages the trust ledger, runs ceremonies, monitors system health.
- **Workers** — isolated Claude Code sessions in git worktrees. Each
  handles one issue end-to-end: research → code → tests → PR.
- **Signals** — structured observations from internal sensors (errors,
  usage, payment anomalies) and external sources (social,
  competitor changelogs, review sites).
- **Ceremonies** — the conductor schedules and executes standup, sprint
  planning, backlog grooming, retro, and weekly summary — all written
  and posted to Linear automatically.
- **Trust** — every worker has a trust score. Rejected PRs, reverted
  merges, and escalations contract it. Clean runs promote it. Trust
  gates which issues get autonomous vs. approval-required treatment.
- **Self-observation** — every 4 hours, Lacrimosa measures its own
  throughput, quality, cost, and discovery accuracy. When metrics drift
  out of bounds (revert rate spikes, false positives climb, cost per PR
  rises), the system adjusts its own thresholds, measures the impact,
  and auto-reverts changes that made things worse. Everything is logged
  in an append-only ledger.
- **Release tracking** — the COO observes every merge, maintains a
  running changelog, and drafts release plans for human review. Releases
  remain human-initiated (the one remaining gate in the system).

## How It All Fits Together

Lacrimosa is not one thing — it's layers, each building on the last. Everything contributes to the whole picture. Read bottom-up to understand how it's built. Read top-down to understand why it matters.

| Layer | What It Is | Examples |
|-------|-----------|----------|
| **Models & Prompts** | Foundation. The LLM and the instructions that shape its behavior. | Claude Opus/Sonnet, system prompts, specialist role definitions |
| **Tools & MCP** | How the model touches the world. File I/O, git, browser, Linear API, schema lookups. | Read/Write/Edit, Bash, chrome-devtools MCP, schema-mcp, Linear MCP |
| **Agents** | A model + tools + a system prompt = a focused worker. 28 custom agents, each with a defined role and tool set. | `backend-developer-v4`, `security-officer-v3`, `qa-engineer-v5` |
| **Skills** | Multi-step workflows that agents execute. A skill is a recipe: "do TDD in phases 1-8" or "review a PR with parallel reviewers." | `/implement` (8-phase TDD), `/bugfix` (hypothesis testing), `/pre-release` (verification gates) |
| **Hooks** | Structural guardrails. Shell scripts that fire on tool-call events — prompts suggest behavior, hooks enforce it. | `block-linear-mcp-writes.sh`, `god-class-check.sh`, `security-review-precommit.sh` |
| **Orchestration** | How agents coordinate. Agent Teams with shared task lists, peer communication, and contracts. The workflow-orchestrator drives phase transitions. | `workflow-orchestrator-v3` → spawns architect → developer → reviewer in sequence |
| **Specialists** | Long-running autonomous sessions. Each specialist runs in its own tmux session with `-p` (non-interactive mode) to prevent context bloating. 11 concurrent specialists share state via SQLite. | Discovery (30m), Engineer-Implement (10m), Sentinel (5m), COO (60m) |
| **Conductor** | The main loop. Polls for work, dispatches specialists, manages trust, runs ceremonies, monitors health, enforces rate limits. The single process that keeps everything alive. | Health checks, throttle (GREEN/YELLOW/RED), ceremony scheduling |
| **Product Lifecycle** | The emergent result. Sensing → triage → implementation → review → merge → release tracking → monitoring → learning. The full engineering loop, unattended. | A bug is sensed at 3am → triaged → fixed → tested → reviewed → merged → changelog updated → release plan drafted — all before sunrise |

## Testing & Verification Architecture (Know-How)

Lacrimosa's verification pipeline is multi-layered and runs *after*
static code review — not instead of it:

**Gate 1 — Unit + Integration tests**
Every PR branch runs `./run_unit_tests.sh` and `./run_integration_tests.sh`
before any other gate. Failure sends the issue back to implementation.

**Gate 2 — Real API staging verification**
For backend changes: the PR is deployed to staging, then a Claude Code
agent dispatches real `curl`/`httpie` requests against live endpoints.
Evidence (response codes, payloads, timing) is captured in `REPORT.md`.
No mocks. No fixtures. Real HTTP.

**Gate 3 — Browser QA via Chrome automation**
For frontend changes: a Claude Code agent opens the staging URL in Chrome
via MCP tools, navigates, clicks, fills forms, checks console for JS
errors, and captures screenshots. Zero JS errors required.

**Gate 4 — Webapp auth-flow testing**
Login, navigation, and core user flows verified end-to-end against staging
credentials.

**Static code review (parallel reviewers)**
Runs before the verification gates: code quality, architecture (SOLID/DRY),
security (OWASP Top 10), silent failure detection, type design, test
coverage, accessibility, comment accuracy. All run in parallel via the
`pr-review-toolkit:review-pr` Claude Code skill. Merge requires zero
issues of any severity.

**Trust-gated merge**
The conductor only auto-merges when: all review passes + all verification
gates pass + worker trust score is above threshold. Otherwise it escalates
to human review.

This pipeline was designed after real production incidents — not just from
first principles.

## Specialists

Lacrimosa runs 11 specialists concurrently, each in its own tmux session with an independent context window. State is shared via SQLite (WAL mode).

> Each specialist runs in its own tmux session launched with `-p` (non-interactive mode). This prevents context bloating — specialists don't accumulate conversation history across cycles. Each cycle starts fresh with just the specialist's skill prompt and current state.

| Specialist | Cadence | Role | Impact |
|---|---|---|---|
| **Conductor** | 5m | Orchestrates all specialists: health-checks tmux sessions, restarts dead ones, processes learning events, updates dashboard, manages rate limits. **Runs all ceremonies**: standup (4h), sprint planning (daily 08:00), backlog grooming (12h), sprint retro (daily 22:00), weekly summary (Fri 22:30). Routes unassigned issues to projects during grooming. | Single point of system health and operational rhythm — if conductor is up, everything runs. |
| **Discovery** | 30m | Runs 5 internal sensors (GA4 funnel, error patterns, feedback, payment anomalies, usage). Crawls external sources (Reddit, competitor changelogs, review sites). Validates signals against evidence thresholds, scores them with LLM, creates Linear issues for actionable findings. | Turns raw product signals into prioritized Linear tickets without human involvement. |
| **Engineer-Triage** | 10m | Reality-checks every new Linear issue (already done? duplicate? in-scope?). Classifies issue type (bug/feature/investigation/epic). Routes to correct lifecycle. Posts structured triage comment as Lacrimosa. | Prevents Lacrimosa from working on stale, duplicate, or out-of-scope issues. |
| **Engineer-Implement** | 10m | Picks Triaged issues, dispatches a Claude Code worker in an isolated git worktree. Monitors worker progress, detects stalls, handles review feedback (FixNeeded → re-dispatch). | The engine that turns Linear tickets into pull requests — unattended. |
| **Engineer-Review** | 10m | Invokes `pr-review-toolkit:review-pr` on every open PR. Posts structured verdict (APPROVE / CONTINUE_WORK with issues list) as Lacrimosa. Tracks iterations, escalates at 3 failures. | Zero-tolerance multi-pass code review. PRs merge only when reviewers find no issues of any severity. |
| **Engineer-Merge** | 10m | Manages the merge queue. Resolves dependencies, rebases, squash-merges approved PRs. Updates Linear status to Done. | The final automated gate — no human needed between approved PR and merged commit. |
| **Sentinel** | 5m | Production watchdog. Monitors error spikes, payment failures, negative feedback bursts. Creates urgent Linear issues immediately. Never throttled (rate-limit exempt until 95% weekly usage). | Catches production fires within 5 minutes, day or night, without human monitoring. |
| **Content** | 24h | Queries Linear for SEO/content tasks, dispatches `/team-implement` for each. Handles blog posts, landing pages, comparison pages. | Autonomous content pipeline — SEO issues get written and submitted for review without developer time. |
| **CLO** (Chief Legal Officer) | 60m | Monitors legal/compliance signals: privacy policy changes, ToS updates, regulatory alerts relevant to the product's market. Creates issues for human review. | Early warning on compliance risk — flags issues before they become problems. |
| **CFO** (Chief Financial Officer) | 60m | Monitors payment health: failed payment rates, churn signals, checkout abandonment, subscription anomalies. Creates prioritized issues for engineering. | Converts Stripe/billing data into actionable engineering tickets automatically. |
| **COO** (Chief Operating Officer) | 60m | Release observer and planner. Polls `git log` for recent merges, maintains a running changelog of unreleased changes, and drafts release plans when a batch accumulates (5+ PRs or 24h+ since last release). Groups changes by category, assesses migration risk, and creates Linear issues with the drafted plan for human review. Learns release patterns over time (frequency, incident correlation, migration needs). **Observer-only by default** — `deploy_authority: false`. Does NOT run ceremonies (conductor does), does NOT execute releases, tag versions, or trigger deployments. | Institutional memory for releases — knows what shipped, what's pending, and what broke last time. |

## Throttle — Why Lacrimosa Doesn't Burn Through Your Budget

An autonomous system that runs 11 specialists around the clock will
exhaust any API budget if left unchecked. Lacrimosa solves this with a
three-color throttle that reads Claude Code's built-in rate limit
counters every conductor cycle (5 minutes) and adjusts system behavior
in real time.

### The Problem

Claude Code exposes two rolling usage windows: a **5-hour window** and
a **7-day window**, each as a used-percentage. A single Max subscription
(20x) gets exhausted in 24–36 hours of full autonomous work. If the
system keeps dispatching implementation workers at 85% usage, it hits
the wall and every specialist stalls mid-cycle. Recovery is ugly —
half-written PRs, stale worktrees, confused state.

### The Solution: Three Colors

The conductor evaluates both windows every cycle. The **worst color
across both windows wins** — if the 5-hour window is GREEN but the
7-day window is YELLOW, the system runs in YELLOW.

```
GREEN  → Full autonomy. All specialists run normally.
YELLOW → Research-only mode. No new implementation workers.
RED    → Pause all. Only monitor active workers.
```

**GREEN** (5h < 50%, 7d < 80%): Business as usual. Discovery senses,
triage classifies, implementation dispatches workers, review runs,
merge processes the queue. All 11 specialists at full cadence.

**YELLOW** (5h 50–79% or 7d 80–89%): The system switches to
research-only mode. No new implementation or architecture workers are
dispatched — the expensive work stops. But lightweight work continues:

- Triage incoming issues
- Groom and prioritize the backlog
- Write acceptance criteria and decompose epics
- Run discovery sensors (internal + external)
- Update Linear statuses, archive stale issues
- Active workers already in flight are allowed to finish

This is the key insight: YELLOW doesn't waste the remaining budget on
idle cycles, but it doesn't start expensive new work either. The system
uses spare capacity to improve the backlog quality so that when budget
replenishes, the next GREEN window has better-prepared issues to work on.

**RED** (5h ≥ 80% or 7d ≥ 90%): Everything pauses. No new dispatch of
any kind. Active workers are monitored but no new ones spawn. The
system waits for the usage window to roll over.

### Per-Window Thresholds

```yaml
rate_limits:
  five_hour:
    green_below: 50      # <50% → GREEN
    yellow_below: 80     # 50-79% → YELLOW
    red_at: 80           # ≥80% → RED
  seven_day:
    green_below: 80      # <80% → GREEN
    yellow_below: 90     # 80-89% → YELLOW
    red_at: 90           # ≥90% → RED
```

The 7-day window has higher thresholds because it's a longer budget —
hitting 80% of a weekly budget is less urgent than hitting 80% of a
5-hour budget. These thresholds are configurable per deployment.

### Exception: Sentinel

The sentinel (production watchdog) is **never throttled** until 95% of
the weekly budget. Production fires don't wait for budget replenishment.
If your service is throwing 500s at 3am, the sentinel creates an urgent
Linear issue regardless of throttle color.

```yaml
sentinel_pipeline:
  throttle:
    blocked_on: []           # never blocked by color
    hard_limit: "weekly_95"  # only stops at 95% weekly
```

### How It Shows Up

The dashboard displays throttle status prominently:
`Throttle: GREEN (5h:12% 7d:18%)` — at a glance, you know how much
runway the system has. The conductor logs every color transition with
both window percentages so you can tune thresholds based on your
actual usage patterns.

## Self-Observation — How Lacrimosa Improves Itself

Most autonomous systems run blind — they execute work but have no
model of their own performance. Lacrimosa watches itself with the same
rigor it applies to the product it manages.

### MetaSensor: Lacrimosa's Mirror

Every 4 hours, the MetaSensor collects a snapshot of Lacrimosa's own
performance across 6 categories:

| Category | What It Measures | Example Metrics |
|---|---|---|
| **Throughput** | How fast work moves through the pipeline | Issues completed/day, PRs merged, avg time-to-merge |
| **Quality** | How clean the output is | Revert rate, avg review iterations per PR, bugs per task |
| **Cost** | How efficiently it uses tokens | Tokens per task, cost per merged PR, daily spend |
| **Discovery** | How well sensing works | Signals processed, signal-to-issue conversion rate, false positive rate |
| **Ceremonies** | Whether the operational rhythm is healthy | Missed ceremony count, last-run ages |
| **System** | Infrastructure health | Rate limit usage, throttle level, active worker count, specialist error rates |

### AutoTuner: Reactive and Proactive Rules

The AutoTuner evaluates two types of rules against MetaSensor snapshots:

**Reactive rules** fire when something goes wrong:

```yaml
# If >10% of merged PRs got reverted over 3 days → tighten review
high_revert_rate:
  metric_path: "quality.revert_rate"
  operator: ">"
  threshold: 0.10
  window_days: 3
  action: "Tighten review criteria, add reviewers"

# If PRs average 2.5+ review iterations → improve implementation quality
high_review_iterations:
  metric_path: "quality.avg_review_iterations"
  operator: ">"
  threshold: 2.5
  window_days: 3
  action: "Add self-reflection step to implementation phase"

# If discovery creates issues that don't convert → raise evidence bar
discovery_false_positive_spike:
  metric_path: "discovery.false_positive_rate"
  operator: ">"
  threshold: 0.7
  window_days: 3
  action: "Raise validation Gate 1 thresholds"

# If a specialist keeps crashing → disable it, escalate to human
specialist_restart_storm:
  metric_path: "specialists.*.restarts_24h"
  operator: ">"
  threshold: 3
  window_days: 1
  action: "Disable specialist and escalate"
```

**Proactive rules** fire when things are going well — reinforcement:

```yaml
# Zero reverts for a full week → promote trust tier
zero_reverts_streak:
  metric_path: "quality.revert_rate"
  operator: "=="
  threshold: 0.0
  window_days: 7
  action: "Consider trust tier promotion for stable domains"

# Cost per PR is declining over 5 days → log what's working
cost_declining:
  metric_path: "cost.cost_per_merged_pr"
  operator: "trend_declining"
  window_days: 5
  action: "Log what's working, reinforce patterns"
```

### The Learning Loop

When a rule fires, the system doesn't just log it — it creates a
structured **learning event** with a root cause analysis, a proposed
adjustment, and an impact window. The full cycle:

1. **Detect** — MetaSensor snapshot shows a metric out of bounds
2. **Analyze** — AutoTuner matches a rule, Claude analyzes the context
3. **Adjust** — change is applied to config/thresholds (if auto-apply
   is enabled) or posted to Linear for human review
4. **Measure** — after the impact window (default 24h), the system
   checks whether the metric improved
5. **Revert or Reinforce** — if the metric degraded, the adjustment is
   automatically reverted and a learning is recorded. If it improved,
   the adjustment is kept and the pattern is reinforced.

Every adjustment is recorded in an append-only ledger
(`~/.claude/lacrimosa/learnings.json`). Nothing is silently changed —
the full history of what the system tried, what worked, and what it
rolled back is auditable.

### Trust: The Self-Correcting Quality Gate

Trust is Lacrimosa's per-domain reputation system. Every domain
(e.g., "Platform", "Billing", "iOS") has a trust tier (T0 → T1 → T2)
that controls how much autonomy the system gets:

| Tier | Concurrent Workers | Issues/Day | Max Files/PR |
|------|-------------------|------------|--------------|
| T0 (new) | 1 | 3 | 15 |
| T1 (proven) | 2 | 5 | 25 |
| T2 (trusted) | 3 | 10 | 40 |

Trust **contracts** on:
- PR rejected by reviewers (`pr_review_rejected`)
- PR reverted after merge (`pr_reverted`)
- Worker escalated to human (`worker_escalated`)
- 2+ review iterations on a single PR (`pr_review_iteration_2plus`)

Trust **promotes** on:
- Clean streak of merged PRs with zero issues
- Zero reverts over a sustained period (triggers the proactive rule)

A domain that starts producing bad PRs automatically loses concurrency
and daily capacity — the system throttles itself in the areas where
it's struggling, without human intervention.

### Toolchain Monitor: Watching Its Own Tools

Lacrimosa also monitors its own toolchain — the Claude Code CLI,
Anthropic API, and related infrastructure — for changes that could
affect its operation:

```yaml
toolchain_monitor:
  cadence_hours: 6
  sources:
    anthropic_blog:
      urls: ["https://anthropic.com/news", "https://anthropic.com/engineering"]
    claude_code_releases:
      method: "gh release list -R anthropics/claude-code --limit 5"
    claude_code_npm:
      url: "https://www.npmjs.com/package/@anthropic-ai/claude-code"
```

When a new Claude Code release drops, the toolchain monitor classifies
the finding (breaking change? new feature? deprecation?), evaluates
relevance to Lacrimosa's operation, and routes the decision: auto-adopt
for safe updates, create a Linear issue for risky ones, archive
irrelevant noise.

### Real Examples From Production

These are things Lacrimosa actually detected and acted on:

- **Revert rate spiked to 15%** over 3 days → system tightened review
  criteria, added self-reflection step to implementation phase. Revert
  rate dropped to 0% within a week.
- **Discovery false positive rate hit 72%** → system raised evidence
  thresholds for sensor validation. Signal-to-issue conversion improved
  from 28% to 61%.
- **Content specialist restarted 4 times in 24h** → auto-disabled,
  Linear issue created for human investigation. Root cause: MCP tool
  timeout during long article generation.
- **Cost per merged PR declined 30% over 5 days** → proactive rule
  logged the pattern. Correlated with better-prepared issues from
  improved backlog grooming during YELLOW throttle windows.
- **Zero reverts for 9 consecutive days** on Platform domain → trust
  promoted from T1 to T2, unlocking 3 concurrent workers and 10
  issues/day capacity.

## Dashboard

Lacrimosa ships with a live web dashboard at `http://localhost:1791`
(port 1791).

```bash
.venv/bin/python scripts/lacrimosa_dashboard.py
```

The dashboard shows:
- Specialist health (all 11 sessions — heartbeat, errors, restarts)
- Active pipeline (issues in flight, current phase, elapsed time)
- Trust scores by domain with tier visualization
- Rate limit usage and throttle level (GREEN/YELLOW/RED)
- Recent completions with merge status and phase timing
- Discovery sensor health and signal queue
- Token costs and quality metrics

API endpoints: `/health` (JSON), `/api/state`, `/api/metrics`,
`/api/report/{issue}`, `/screenshots/{file}`.
System controls: `POST /api/control` to pause/resume.

## Hooks — The Guardrails That Make Autonomy Safe

Lacrimosa doesn't just rely on prompts to stay disciplined — it uses
Claude Code's [hooks system](https://docs.anthropic.com/en/docs/claude-code/hooks)
to structurally enforce safety rules. Hooks are shell scripts that fire
before or after tool calls, blocking dangerous actions before they happen.
No amount of prompt drift can bypass a hook that exits with `deny`.

| Hook | Trigger | What It Prevents |
|------|---------|-----------------|
| **Linear MCP write blocker** | PreToolUse on `mcp__linear-server__*` write tools | Lacrimosa specialists posting as the human user instead of as Lacrimosa. Forces all Linear writes through `scripts/lacrimosa_linear.py` (which uses Lacrimosa's own API key). |
| **Auto-import fixer** | PostToolUse on `Edit\|Write` of `.py` files | Missing Python imports. Runs `autoimport` to auto-add standard library and known third-party imports, then `ruff F821` to catch remaining undefined names. Blocks if unresolvable. |
| **GOD class preventer** | PostToolUse on `Edit\|Write` of `.py` files | Classes growing beyond 15 methods or 300 lines. Uses AST parsing to detect violations and blocks the edit with refactoring guidance. |
| **Security review gate** | PreToolUse on `git commit` | Commits without security review. Triggers a security-officer agent to scan staged changes for OWASP Top 10, hardcoded secrets, injection risks. Blocks on critical/high findings. |
| **Corrections enforcer** | PreToolUse on `Agent\|Bash` | Known anti-patterns learned from past mistakes. Blocks `git stash` (leads to lost work), blocks `source .venv/bin/activate` (shell state doesn't persist), redirects Agent Teams vs subagent misuse. |
| **Idle teammate redirector** | TeammateIdle | Agent team members going idle when pending work exists. Checks task list for unblocked tasks matching the teammate's role and nudges them with role-specific guidance. |
| **Task completion validator** | TaskCompleted | Premature task completion. Implementation roles must pass through code checks; design roles must have contract files present. |
| **Context recovery** | Session start | Lost context between sessions. Surfaces active tasks, RALPH loop status, recent commits, modified files, and open GitHub issues. |

These hooks ship with the repo. They're plain bash scripts — readable,
auditable, and customizable. Add your own guardrails by dropping a
script into `.claude/hooks/` and registering it in `settings.json`.

The hooks are what make the difference between "autonomous AI system" and
"autonomous AI system you can actually trust overnight." Prompts suggest
behavior. Hooks enforce it.

## Built for Claude Code

Lacrimosa requires Claude Code CLI. It uses:
- Git worktrees (isolated sessions per issue)
- MCP tools (browser automation, Linear, Chrome DevTools)
- The Claude Code skills system (pr-review-toolkit, implement, bugfix)
- Hooks (structural guardrails — see above)
- Schema MCP server (bundled) — Lacrimosa's long-term product memory.
  Gives every specialist instant access to architecture schemas,
  infrastructure facts, business rules, and conventions without
  grepping files. See `schema-mcp/README.md`.

It is not model-agnostic by design. Claude's long context window and
agentic tool use are load-bearing architectural assumptions.

## A Note on This Release

This open-source version of Lacrimosa was distilled from a production
system that has been running a real commercial product continuously
since March 2026. The extraction involved replacing all business-specific
values with config-driven placeholders, genericizing prompts, and
removing proprietary data sources.

Some glitches and misalignments from that distillation process are
inevitable. If you find something that looks like a leftover reference,
a broken config path, or a logic mismatch — it probably is. Issues and
corrections are welcome: open a GitHub issue or submit a PR.

## Quick Start

[Install, configure, run]

## License

Lacrimosa is released under a **non-commercial license** — free for personal,
academic, and research use. Commercial use requires a separate agreement.
See [LICENSE](LICENSE).

The `schema-mcp/` component is licensed separately under the **MIT License**.
See [schema-mcp/LICENSE](schema-mcp/LICENSE).

## Author

Created by Sergei Telitsyn.
Commercial licensing: sltelitsyn@gmail.com

---

## Appendix A: Competitive Landscape

Detailed comparison of what each competitor does well and where
Lacrimosa's integrated loop goes further. Referenced from the
"What Others Charge" section above.

| What Lacrimosa Does | Who Charges for It | Their Price | What They Do Well | What's Still Missing vs. Lacrimosa |
|---|---|---|---|---|
| **Autonomous coding** — senses issues, picks work, writes code, runs tests, creates PRs in isolated worktrees | **Devin** (Cognition, $2B val.) | $20–500/mo + ACUs | Full autonomous agent: plans, codes, debugs, deploys. Desktop testing via computer use. Code review agent. Multi-agent parallel sessions. | Task-level autonomy — you assign work, Devin does it. No product sensing (doesn't discover what to build), no release pipeline, no trust system that self-corrects quality over time. |
| | **Cursor** (Anysphere, $2B+ ARR) | $16–200/mo | Background agents in cloud VMs (up to 8 parallel). Computer use for visual verification. Automations triggered by GitHub/Linear/Slack. Self-hosted option. | IDE-centric — agents work on tasks you define. New automations feature approaches Lacrimosa's sensing but doesn't triage, prioritize, or manage the full merge-to-release cycle. |
| | **OpenAI Codex** | $20–200/mo + tokens | Cloud and local agents: writes features, fixes bugs, runs tests, opens PRs. Skills system for custom automations. Automations for unprompted work (issue triage, CI monitoring). GPT-5.4 model. | Strong individual agent, evolving toward continuous automation. Doesn't yet integrate product sensing, multi-pass review, trust scoring, or release planning into a single autonomous loop. |
| | **Poolside** ($14B val.) | Enterprise custom | Enterprise-grade foundation models (Malibu, Point) fine-tuned on customer codebases. Private deployment. Agentic capabilities in development. | Models and IDE integration, not an autonomous loop. Doesn't sense product signals, manage a pipeline, review, merge, or release. Focused on coding quality, not engineering autonomy. |
| **Code review** — multi-pass parallel reviewers (architecture, security, accessibility, silent failures), zero-tolerance merge gate | **CodeRabbit** | Free / $24–30/seat/mo | Line-by-line PR review with summaries and diagrams. 40+ linters. Code graph analysis. Issue Planner (generates coding plans from issues). Integrates Slack/Sentry/Confluence context via MCP. | Excellent review tool, now expanding into planning. Doesn't implement code, doesn't manage the merge queue, doesn't track releases, doesn't run a continuous engineering pipeline. |
| | **Sourcery** | $12–24/seat/mo | Instant PR reviews, real-time IDE feedback, security scanning across 200+ repos. Custom rules. Python/JS focused. | Review and scanning only — no implementation, no merge management, no sensing, no release tracking. |
| **SEO content** — keyword research, article writing, publishing through PR pipeline | **Ahrefs** | $129–449/mo + Enterprise | Industry-leading backlink/keyword data. AI Content Helper writes and optimizes articles. Brand Radar tracks mentions across 6 AI platforms. AI-powered reporting, keyword research, localization. | Powerful analytics + now writes content. But content stays in Ahrefs — doesn't flow through your git repo, doesn't get code-reviewed, doesn't merge into your site via PRs. No engineering pipeline integration. |
| | **Outrank** | $99/mo | Automated SEO content: keyword research → article generation → publishing. Hands-free content pipeline. | Writes and publishes, but operates in its own silo — no integration with your codebase, no code review of generated content, no prioritization against engineering work. |
| | **Surfer SEO** | $79–219/mo | AI article generation with fact-checking (300k+ words analyzed). Content Editor 3.0 with real-time optimization. Topical maps. AI Search Guidelines for citation optimization. | Generates and optimizes content. Doesn't integrate with engineering workflows — content lives in Surfer, not in your repo as reviewed, merged PRs. |
| **Production monitoring** — error spikes, payment failures, feedback bursts → auto-creates prioritized engineering tickets | **Datadog** | $15–34/host/mo | Bits AI SRE: autonomous investigation, source code analysis, remediation playbooks. Bits AI Security Analyst. RUM, APM, profiling. Moving toward fully autonomous remediation. | Impressive AI agents for investigation and remediation. But Datadog fixes infrastructure — it doesn't sense product-level signals (funnel drops, competitor moves, user feedback sentiment) or write feature code. |
| | **PagerDuty** | $21–41/user/mo | SRE Agent as virtual responder: diagnoses before waking humans. Agentic Cloud Operations for AWS/Azure. 30+ AI integrations. Moving toward autonomous operations. | Incident-focused — great at detecting and responding to outages. Doesn't write code to fix the root cause, doesn't track fixes through review and merge, doesn't plan releases. |
| **Project management** — autonomous issue triage, prioritization, backlog grooming, status reporting | **Linear** | $10–16/user/mo | Best-in-class issue tracker. Clean UI. Cycles, roadmaps, triage. GitHub integration. | The tracker itself — doesn't decide what to build, doesn't triage issues autonomously, doesn't prioritize or act on what it tracks without human input. |
| | **Asana** (AI agents) | $11–28/user/mo | AI Teammates: autonomous agents for multi-step workflows. Timesheets, budgets, goals tracking. | Workflow automation agents are emerging, but focused on project coordination — not engineering autonomy (doesn't write code, review PRs, or deploy). |
| **Legal/compliance** — monitors regulatory landscape, audits codebase, creates remediation tickets | **Vanta** | $10K–80K/yr | 24/7 AI agents for compliance, TPRM, customer trust. 35+ frameworks. 200+ integrations. Auto evidence collection. AI questionnaire automation (95% acceptance). | Enterprise-grade compliance platform. But Vanta audits compliance posture — it doesn't grep your codebase for TCPA violations, doesn't create Linear tickets with code-level fix steps, doesn't feed findings into an autonomous engineering pipeline. |
| | **Drata** | $9K–100K+/yr | Multi-framework compliance automation. Pre-built integrations for evidence collection. Trust Center. Policy management with templates. | Same category as Vanta — audit readiness, not autonomous compliance sensing integrated with your engineering pipeline. |
| **Release management** — tracks merges, maintains changelog, drafts release plans with risk assessment | **LaunchDarkly** | $12/connection/mo + usage | Guarded Releases: progressive rollouts, real-time monitoring, instant rollbacks. AI Configurations for model/prompt iteration. Product Analytics. Experimentation. | Feature flag and release orchestration platform — controls rollouts, not release content. Doesn't draft changelogs from merged PRs, doesn't assess migration risk from diffs, doesn't learn release patterns over time. |

*Data as of April 2026. Pricing and capabilities change — verify before citing.*
