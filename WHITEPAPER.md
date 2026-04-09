# Lacrimosa

**Sergei Telitsyn** — April 2026

---

1. [The First Night](#1-the-first-night) — I built a system and watched it replace me
2. [The Fragment Problem](#2-the-fragment-problem) — Why the best AI tools still miss the point
3. [The Full Loop](#3-the-full-loop) — Eleven specialists, one state, zero humans in the loop
4. [What Happened When It Ran](#4-what-happened-when-it-ran) — 27 days of production data from an early prototype
5. [The Self-Correcting Organization](#5-the-self-correcting-organization) — Trust, self-observation, and organizational intelligence
6. [What This Means for Engineers](#6-what-this-means-for-engineers) — The role is transforming. The timeline is months.
7. [What Comes Next](#7-what-comes-next) — The artifact expires. The judgment doesn't.

---

## 1. The First Night

I built a system that runs a software product without me. Not a copilot. Not an assistant. A system that senses what needs to be built, decides what to prioritize, writes the code, tests it, reviews it, merges it, prepares the release, monitors production, and learns from its own mistakes — continuously, overnight, while I sleep.

I watched it work for the first time on a quiet evening in March. I had configured the last specialist, set the conductor loop to five minutes, and sat there — watching. For hours. Tmux panes filling with activity, specialists cycling through their loops, issues appearing in Linear that I had not created. I could not look away. I was trying to understand what I had built. By morning, it had triaged fourteen issues, implemented three features, caught a payment anomaly through its financial sensor, created an urgent ticket for a production error spike, and was in the middle of reviewing its own pull requests through a panel of parallel code reviewers — architecture, security, accessibility, silent failure detection — before merging anything.

Every one of these behaviors was deliberately engineered — the sensors, the priority logic, the review pipeline, the throttle strategy. But once configured, the system ran without a single per-task instruction. It sensed what the product needed, judged the priority, and acted. The code was clean. The tests passed. The review was rigorous.

That was the moment I understood what I had built. Not a faster way to write code — a replacement for the organizational structure around software. Discovery, triage, planning, implementation, review, merge, release, monitoring, learning. The full loop. Running as one integrated system, on one machine, with no human in it.

I named it Lacrimosa.

The name comes from Mozart's Requiem in D minor, K. 626 — his final composition. Mozart was commissioned to write the Requiem in the summer of 1791. He was already ill. He worked on it through the autumn as his health deteriorated, composing movement by movement, knowing he was unlikely to finish. He made it to the eighth movement — the Lacrimosa — and completed eight bars. Then the pen left his hand. He died on December 5th, 1791, at thirty-five.

The word *lacrimosa* means "tearful" in Latin. The text it sets is from the Dies Irae sequence of the Requiem Mass: *"Lacrimosa dies illa"* — "That day is one of weeping, on which shall rise from the ashes the guilty man to be judged." Mozart was writing a requiem while dying. He was mourning inside his own ending.

That is the weight I felt. I had built a system that makes an entire class of human work — discovery, judgment, engineering, operations — not just faster, but redundant. The act of writing code, reasoning through a product problem, feeling the weight of a hard architectural decision — this system does all of it autonomously, without fatigue or doubt. And it is early. This is not the ceiling.

This paper presents the evidence for a claim that I believe is no longer speculative: the full software engineering loop — not just the act of writing code, but the entire organizational process around it — is automatable.

---

## 2. The Fragment Problem

The AI coding tools that dominate the conversation today are, without exception, fragment tools. They automate pieces of the software engineering process — often brilliantly — while leaving the process itself intact.

Cursor and GitHub Copilot have evolved from autocomplete into capable coding agents — multi-file edits, background tasks, terminal access, context-aware reasoning across entire repositories. Devin and OpenAI's Codex go further, writing features end-to-end in sandboxed environments with their own browsers and shells. CodeRabbit and Sourcery review pull requests with increasing sophistication. Datadog and PagerDuty monitor production and page oncall engineers. Linear and Asana track issues. Ahrefs and Surfer SEO research keywords and generate content. Each of these tools is genuinely good at what it does. Some are exceptional — and getting better fast.

But none of them runs the loop.

To understand why this matters, consider what actually happens when software gets built inside a functioning engineering team. The process is not "someone writes code." The process is a cycle with at least nine distinct phases:

**Sense** — detect what needs attention. Error spikes, user feedback, payment anomalies, competitor moves, funnel drop-offs, regulatory changes. This is the product manager reading dashboards, scanning support tickets, and talking to users.

**Triage** — decide what matters. Deduplicate, classify, assess severity, route to the right team. This is the tech lead in Monday morning standup, prioritizing the week's work.

**Plan** — decompose work into actionable units. Write acceptance criteria, identify dependencies, estimate scope. This is the architect or senior engineer breaking an epic into tasks.

**Implement** — write the code. Branch, scaffold, test, iterate. This is what most people picture when they think of software engineering — and it is one phase out of nine.

**Review** — verify quality. Architecture review, security audit, accessibility check, test coverage analysis. This is the senior engineer reading the diff, the security team scanning for OWASP violations, the accessibility specialist checking contrast ratios.

**Merge** — integrate changes. Resolve conflicts, manage the merge queue, update dependencies. This is the release engineer keeping the main branch clean.

**Release** — ship to production. Build, deploy, verify, monitor the rollout. This is the DevOps engineer running the deploy pipeline and watching error rates.

**Monitor** — watch what shipped. Error rates, latency, payment failures, user behavior changes. This is the oncall engineer at three in the morning, staring at Grafana.

**Learn** — improve the process. Retrospectives, post-mortems, threshold adjustments, workflow refinements. This is the engineering manager asking "what went wrong and how do we prevent it?"

Now map today's AI tools onto this cycle. Cursor, Copilot, Devin, and Codex cover **Implement** — phase four of nine. CodeRabbit and Sourcery cover **Review** — phase five. Datadog covers **Monitor** — phase eight. Linear covers **Triage**, but only the tracking part — it holds the tickets, it does not decide which ones matter. Ahrefs covers content research, which feeds **Sense** for one narrow domain, but lives in its own silo disconnected from the engineering pipeline.

The coverage looks like this: four of the nine phases have specialized AI tools. Five phases — Sense, Plan, Merge, Release, and Learn — have essentially no AI automation at all. And even within the covered phases, the tools do not connect to each other. The output of CodeRabbit's review does not feed into a merge queue. Datadog's alerts do not create prioritized engineering tickets. Devin's completed PRs do not trigger a release pipeline. Each tool operates in isolation. A team of humans glues them together — scheduling the standup, reading the alerts, prioritizing the backlog, coordinating the release, running the retrospective.

This is the fragment problem. The industry has optimized individual phases while leaving the integration — the thing that actually makes software ship — entirely to human labor. And this integration is not trivial overhead. It is the job. Ask any engineering manager what they spend their time on, and the answer is not "writing code." It is coordination: making sure the right things get built, reviewed, shipped, and monitored, in the right order, without dropping anything.

The hard problem was never coding. It was the organizational structure around coding — the judgment calls, the prioritization, the quality gates, the handoffs between phases. That is what a software team actually does. And until recently, that is what nobody was trying to automate.

---

## 3. The Full Loop

Lacrimosa is a system that runs the complete engineering loop described above — all nine phases — as one integrated process. It has been operating continuously on a real commercial product since March 2026, unattended, producing working software.

This section describes the architecture. Not as a tutorial — there is documentation for that — but as an engineering argument: the full loop *can* be expressed as a system. The organizational structure of a software team can be modeled, automated, and run.

### Eleven Specialists, One State

Lacrimosa runs eleven AI specialists concurrently, each in its own isolated session with an independent context window. Each specialist maps to a role that would traditionally be filled by a human:

**Discovery** is the product manager. Every thirty minutes, it runs internal sensors — error pattern analysis, user feedback aggregation, payment anomaly detection, usage trend monitoring, funnel drop-off measurement — and crawls external sources: competitor changelogs, review sites, Reddit threads, regulatory news. Raw signals are validated against evidence thresholds, scored for severity and actionability, and converted into prioritized engineering tickets. The product manager who reads dashboards at 9am and decides what to build — that function runs autonomously, around the clock.

**Engineer-Triage** is the tech lead. Every ten minutes, it reality-checks every new ticket: has this already been done? Is it a duplicate? Is it in scope? It classifies each issue — bug, feature, investigation, epic — and routes it to the correct lifecycle. This is the judgment call a senior engineer makes in standup: "this is real, this matters, work on it next."

**Engineer-Implement** is the developer. It picks triaged issues, dispatches a worker into an isolated git worktree — a separate branch, a separate directory, with its own copy of the repository — and monitors progress. The worker follows a structured eight-phase workflow: research, test design (tests first — always), implementation, self-review, security audit, verification against staging, cleanup, and knowledge capture. If the review comes back with issues, the worker is re-dispatched to fix them. The distinction from autocomplete matters: this is a developer working an issue from assignment to pull request, alone, without assistance.

**Engineer-Review** is the senior code reviewer. Every open pull request goes through a panel of parallel specialized reviewers — architecture (SOLID, DRY, file size limits), security (OWASP Top 10, credential handling, injection risks), accessibility, silent failure detection, type design, test coverage, and comment accuracy. A merge requires zero findings of any severity. Not "zero critical findings." Zero findings. This is a higher bar than most human teams enforce.

**Engineer-Merge** is the release engineer. It manages the merge queue, resolves dependency ordering between PRs, rebases branches, squash-merges approved code, and updates issue status. The handoff from "approved PR" to "merged commit" requires no human.

**Sentinel** is the oncall engineer. Every five minutes, it monitors production for error spikes, payment failures, and negative feedback bursts. If something is on fire at three in the morning, the sentinel creates an urgent ticket immediately. It is never throttled — production fires do not wait for budget replenishment.

**COO** (Chief Operating Officer) is the engineering manager. It observes every merge, maintains a running changelog of unreleased changes, and drafts release plans when a batch accumulates — grouping changes by category, assessing migration risk, noting what broke in previous releases. Releases remain human-initiated. The COO prepares the plan; a human pulls the trigger. This is the one remaining gate in the system.

**Conductor** is the VP of Engineering. The main loop. Every five minutes, it health-checks all specialist sessions, restarts dead ones, processes learning events, updates the dashboard, manages rate limits, and runs operational ceremonies — standup, sprint planning, backlog grooming, retrospective, weekly summary — all automatically scheduled and posted. If the conductor is running, everything runs.

**CLO and CFO** — Chief Legal Officer and Chief Financial Officer — monitor compliance and financial health respectively. The CLO watches for privacy policy changes, terms of service updates, and regulatory signals. The CFO tracks payment failure rates, churn, checkout abandonment, and subscription anomalies. Both create tickets for human review. These are advisory functions — early warning systems, not decision makers.

**Content** handles the SEO and marketing engineering pipeline. It picks up content tasks, dispatches implementation teams, and produces blog posts, landing pages, and comparison articles through the same review-and-merge pipeline as code.

### Four Architectural Ideas

The design rests on four ideas that are worth understanding, because they solve problems that anyone building a system like this will encounter.

**Shared state, not shared conversation.** The eleven specialists do not talk to each other. They share a single SQLite database running in WAL mode — write-ahead logging that allows concurrent readers and a single writer without locks. Each specialist reads the current state, does its work, and writes back. There is no message bus, no chat protocol, no coordination overhead. State is the API. This is how the system scales to eleven concurrent processes on a single machine without choking on inter-process communication.

**Isolation through git worktrees.** Every implementation runs in its own git worktree — a separate working directory with its own branch, checked out from the same repository. The worker can edit files, run tests, and create commits without interfering with any other worker or with the main branch. When the PR is approved and merged, the worktree is cleaned up. This is the same isolation guarantee that a developer gets when they work on a feature branch, except the system creates and destroys these workspaces programmatically, on demand.

**Skills as structured workflows.** A skill goes beyond a prompt — it is a multi-phase recipe with explicit gates between phases. The implementation skill, for example, has eight phases: discovery, TDD test design, implementation, review loop, self-reflection, verification, cleanup, and knowledge preservation. Each phase has entry criteria and exit criteria. The system cannot skip from implementation to merge without passing through review. This is process discipline encoded as structure — the kind of thing that, in a human team, depends on a manager enforcing the workflow. Here, it is the workflow.

**Hooks as structural enforcement.** Claude Code supports hooks — shell scripts that fire before or after tool calls and can block actions by exiting with a deny status. Lacrimosa uses hooks to enforce rules that prompts alone cannot guarantee: a security review gate that blocks every commit until a security officer agent scans the staged changes. A class size enforcer that blocks any edit creating a class over 300 lines or 15 methods. A corrections enforcer that blocks known anti-patterns learned from past mistakes. The critical property of hooks is that they are not suggestions. A shell script that exits with `deny` cannot be prompt-engineered around. Prompts suggest behavior. Hooks enforce it.

### The Existence Proof

The point of this section is narrower than it might appear. The argument is that the architecture is *possible* — that the full engineering loop can be expressed as a system, that eleven specialists can share state and coordinate through structure rather than conversation, that the organizational roles of a software team can be modeled and automated.

Whether this particular implementation is the right one matters less than the fact that it works. The loop runs. Software ships. The system is real.

---

## 4. What Happened When It Ran

Lacrimosa has been running continuously in production since March 13, 2026, managing a real commercial AI product. The numbers below are not benchmarks from a controlled test. They are operational data from twenty-seven days of unattended execution.

### The Throughput

In twenty-seven days, the system produced 327 commits on the main branch — roughly twelve per day. It closed 193 GitHub issues, merged 131 pull requests, and spawned 68 implementation workers in isolated worktrees. The discovery specialist processed 189 signals from six internal sensors and sixty external crawls (competitor changelogs, review sites, Reddit), creating 34 engineering tickets from its own findings — issues that no human identified or requested.

These are not lines of code or token counts. These are shipped features, fixed bugs, and closed tickets. The output of a functioning engineering process, measured in the same units you would use to evaluate a human team.

### The Quality

Raw throughput without quality control is noise. The more interesting data is what happened when quality dropped.

In the second week of operation, the revert rate — the percentage of merged pull requests that were later reverted because they broke something — spiked to fifteen percent. This is a serious quality problem. In a human team, it would trigger an incident review, a tightening of the review process, and probably a difficult conversation about rushing code.

Lacrimosa had that conversation with itself. The MetaSensor — the self-observation module that snapshots the system's own performance every four hours — detected the revert spike. The AutoTuner matched it against a reactive rule: "if revert rate exceeds ten percent over three days, tighten review criteria and add a self-reflection step to the implementation phase." The adjustment was applied. The implementation workflow gained an additional phase where the system reviews its own code before submitting it for external review — asking, explicitly, "if I were reviewing this PR, what would I flag?"

Within a week, the revert rate dropped to zero percent. It stayed there for nine consecutive days.

A similar pattern played out with discovery accuracy. The false positive rate — the percentage of auto-created tickets that turned out to be noise — hit seventy-two percent. The system was creating more bad tickets than good ones. The AutoTuner raised the evidence thresholds for sensor validation, requiring stronger signals before converting an observation into an engineering ticket. Signal-to-issue conversion improved from twenty-eight percent to sixty-one percent.

When the content specialist crashed four times in twenty-four hours due to an MCP tool timeout during long article generation, the conductor auto-disabled it and created an escalation ticket for human investigation. It did not retry blindly. It did not ignore the failures. It quarantined the failing component and asked for help.

When cost per merged PR declined thirty percent over five days — a positive trend — the proactive rules logged the pattern and correlated it with improved backlog grooming that had been happening during YELLOW throttle windows (the rate-limit-aware mode where the system does research and planning instead of expensive implementation work). The system noticed that its own cost management strategy was improving its output quality.

### What This Means

These are not cherry-picked successes. The system made real mistakes — merging code that needed to be reverted, creating tickets for problems that did not exist, running a specialist into a crash loop. The point is not that it was perfect. The point is that it detected its own failures, corrected them, measured whether the corrections worked, and reverted changes that made things worse. Over twenty-seven days, quality trended upward while throughput remained stable.

That is not "AI that writes code." That is a learning organization compressed into software. The feedback loops that take a human team weeks to execute through retrospectives and process changes — detect a quality problem, hypothesize a fix, try the fix, measure the outcome, keep it or revert it — Lacrimosa runs in hours, continuously, with an auditable trail of every adjustment it made and why.

### An Early Prototype

One fact makes all of this more significant: these results came from Opus 4.5 and Sonnet 4.5/4.6 — models that are, by the time you read this, likely superseded. Mythos is already inside Anthropic. OpenAI's next frontier models are weeks away. Beyond language models entirely, foundational world models are emerging — systems like those from AMI Labs that extend AI reasoning beyond text and code into spatial, physical, and perceptual domains. Each generation does not just improve coding ability. It expands the surface area of what autonomous systems can sense, reason about, and act on.

What took months of careful prompt engineering, trust calibration, and architectural iteration to get right will collapse into something that works out of the box. The ceiling this prototype hit is the floor of what comes next.

To be clear about the limitations: this is twenty-seven days of data from one product, on one codebase, with one AI provider. It is an existence proof, not a universal law. But an existence proof is all that is needed to change the conversation. Before Lacrimosa ran, the full-loop automation of software engineering was a theoretical possibility. After it ran, it is an engineering fact.

---

## 5. The Self-Correcting Organization

The previous section described what the system did when it caught its own mistakes. This section describes *how* — the mechanisms that make self-correction structural rather than accidental.

Lacrimosa was built to compress the self-correcting behavior of a functioning engineering organization — the thing that makes good teams good — into software that runs continuously.

### Trust: The Quality Thermostat

Every domain in Lacrimosa's project space — Platform, Billing, iOS, Marketing, or whatever domains are configured — has a trust tier that controls how much autonomy the system gets in that area. There are three tiers. A new domain starts at T0: one concurrent worker, three issues per day, a fifteen-file limit per pull request. As the system demonstrates clean output in that domain — PRs that pass review, merges that do not get reverted — it promotes to T1 (two workers, five issues per day) and eventually T2 (three workers, ten issues per day, up to forty files per PR).

Trust contracts on failure. A PR rejected by reviewers, a merge that gets reverted, a worker that escalates to a human — each of these events pushes the domain's trust score down. Multiple review iterations on a single PR (more than two rounds) also contract trust, because they indicate the implementation quality is not meeting the review bar.

The effect is a thermostat. When the system starts struggling in a domain — producing PRs that fail review, writing code that needs to be reverted — it automatically loses concurrency and capacity in that domain. It throttles itself where it is weak. No human has to notice the quality drop and manually intervene. The system's own output data gates its own future behavior.

When the Platform domain achieved nine consecutive days with zero reverts, trust was automatically promoted from T1 to T2. The system earned its own autonomy through demonstrated competence.

### The MetaSensor and AutoTuner: Institutional Learning

Beyond per-domain trust, Lacrimosa runs a broader self-observation loop. Every four hours, the MetaSensor collects a snapshot of the system's own performance across six categories: throughput (issues completed, PRs merged, time-to-merge), quality (revert rate, review iterations, bugs per task), cost (tokens per task, cost per merged PR), discovery (signal conversion rate, false positive rate), ceremonies (missed count, schedule adherence), and system health (rate limit usage, specialist error rates).

The AutoTuner evaluates two types of rules against these snapshots. Reactive rules fire when something goes wrong — a revert rate above ten percent triggers tighter review criteria; a false positive rate above seventy percent raises evidence thresholds; a specialist that restarts more than three times in twenty-four hours gets auto-disabled and escalated. Proactive rules fire when things are going well — zero reverts for a week triggers trust tier promotion consideration; declining cost per PR triggers a log entry reinforcing whatever pattern is working.

When a rule fires, it does not just log a note. It creates a structured learning event with a root cause analysis, a proposed adjustment, and an impact window — typically twenty-four hours. After the window, the system measures whether the metric improved. If it did, the adjustment is kept and the pattern is reinforced. If the metric degraded, the adjustment is automatically reverted and the failure is recorded.

Every adjustment, every measurement, every revert is written to an append-only ledger. Nothing is silently changed. The full history of what the system tried, what worked, and what it rolled back is auditable by anyone who wants to look.

This is the behavior that good engineering organizations exhibit: detect a quality problem, hypothesize a root cause, try a targeted fix, measure the outcome, keep it or roll it back. In a human organization, this cycle runs through retrospectives and process changes, and it takes weeks. Lacrimosa runs it in hours, continuously, with a paper trail.

### The Throttle: Resource Awareness

An autonomous system that runs its specialists around the clock will exhaust any API budget if left unchecked. Lacrimosa solves this with a three-color throttle that reads its own rate limit counters every five minutes and adjusts behavior in real time.

GREEN means full autonomy — all specialists at full cadence. YELLOW means research-only mode — no new implementation workers are dispatched, but triage, grooming, backlog improvement, and discovery continue. The system uses its remaining budget to improve the quality of the work queue so that when budget replenishes, the next GREEN window starts with better-prepared issues. RED means everything pauses except monitoring of already-running workers.

The sentinel — the production watchdog — is never throttled until ninety-five percent of the weekly budget. A service throwing 500s at three in the morning gets an urgent ticket regardless of throttle color.

This is resource awareness: the ability to recognize when you are running out of capacity and shift to activities that are valuable but less expensive. A good engineering manager does this intuitively — when the team is stretched thin, they stop starting new projects and focus on grooming the backlog, writing specs, and triaging incoming requests. The throttle encodes that judgment.

### Why This Matters

Each of these mechanisms — trust, self-observation, throttling — could be dismissed individually as a clever engineering trick. Together, they constitute something more: a system that exhibits the organizational intelligence of a functioning engineering team. It notices when quality drops and tightens its standards. It notices when things are going well and gives itself more autonomy. It manages its own resources. It learns from its own mistakes. And it does all of this continuously, without meetings, without retrospectives, without management judgment.

That is not a coding tool. That is management — encoded, automated, and running around the clock.

---

## 6. What This Means for Engineers

The conventional understanding of the software engineer's job is that it centers on writing code. The supporting activities — reading requirements, reviewing pull requests, debugging production issues, attending standups — orbit around this core competency. A good engineer writes good code. The tools and frameworks change, but the fundamental act remains: translating human intent into working software through the act of programming.

Lacrimosa does not need anyone to write code.

The familiar "AI will write code for you" narrative does not capture what is happening here. AI-assisted coding has been a reality since GitHub Copilot launched in 2022. The difference is scope. Lacrimosa does not just write code. It decides what code to write. It prioritizes the work. It decomposes problems. It tests its own output. It reviews its own pull requests through multiple specialized lenses. It merges clean code and rejects dirty code. It tracks releases. It monitors production. It runs retrospectives on its own performance and adjusts its own process.

What remains is a different job entirely: configure the system, set the direction, handle the cases it escalates, and make the decisions it is not authorized to make on its own. In Lacrimosa's current architecture, that means one thing: deciding when to deploy to production. Everything else runs.

This is a transformation from practitioner to operator. The practitioner's value was in the craft — the ability to hold a system's architecture in their head, to write clean code under constraints, to debug subtle production issues through intuition and experience. The operator's value is in judgment — knowing what the autonomous system should be building, recognizing when it is drifting off course, and intervening at the right level of abstraction.

### The Timeline

The model trajectory described in Section 4 has a direct implication for careers: someone will build a better Lacrimosa in a weekend. Then it will ship as a feature of the tools engineers already use. The expectation will shift from "write code" to "operate autonomous engineering systems at scale."

The capabilities that make this possible — long context windows, reliable tool use, structured multi-step reasoning — are improving on a cycle measured in months. The gap between "prototype that runs with careful tuning" and "product that works out of the box" is closing with each release.

### The Shrinking Human Boundary

There is a tempting response to this argument: "Sure, coding might be automated, but there are things that still require a human. Customer conversations. Partnership decisions. Regulatory judgment. Strategy." 

This response is increasingly wrong. Not because the capability is not there — it already is — but because people have not updated their mental model of what AI systems can do.

Customer conversations are handled by AI today. Full executive assistants manage phone calls, email, bookings, research, and errands on behalf of their users, handling the complete operational surface of a professional life. Partnership and regulatory advisory draw on reasoning and real-time search capabilities that already provide analysis on strong evidential grounds. The honest boundary between human and automated work is no longer defined by capability. It is defined by trust, liability, and institutional inertia. 

What remains genuinely human is accountability — someone has to own the consequences of a decision. But accountability is a social and legal convention, not a technical constraint. It is a line that societies draw, and it moves. The question is not whether AI can do these things. The question is how long institutions will take to recognize that it already does.

### The Uncomfortable Middle

There is a period — we are in it now — where this recognition has not caught up with reality. Engineers who understand how to build and operate autonomous engineering systems are extraordinarily valuable. They can do the work of a team. They can ship product at a pace that was previously impossible for a single person. They represent a compression ratio that changes the economics of software development fundamentally.

Engineers who cannot do this — who define their value as "I write code" — are increasingly redundant. Not because they are bad at their jobs. Because the job is changing, and the part they are good at is the part that automated first.

This is not a comfortable thing to write, and it is not written with contempt. The Lacrimosa name was not chosen carelessly. This is a requiem. The craft that defined generations of engineers — the act of reasoning through a hard architectural problem, the satisfaction of a clean implementation, the pride of a well-debugged production issue — these experiences are real and they mattered. But they are not going to be the center of the profession for much longer. The center is shifting to something most engineers have not started preparing for.

The preparation does not start with learning a new framework or mastering a new language. It starts with looking clearly at what is already possible and asking: what does my job become when the coding is done for me? The answer is "something different" — and it is already taking shape. But the window for making that transition gracefully is shorter than most people think.

---

## 7. What Comes Next

The models are improving on a cadence that outpaces career planning. When the next generation arrives — and the one after that — Lacrimosa will not become obsolete. It will become trivial. All of the craft that went into making this system work will collapse into default behavior. The next person to build something like this will spend a weekend. The person after that will not build it at all — it will be generated on demand and discarded, the way we generate a utility function today and move on without a second thought.

I am publishing Lacrimosa now because the window for it to matter as a distinct artifact is closing. Within months, not years, autonomous engineering loops will be table stakes — features of the tools engineers already use, not standalone systems that require weeks of configuration. The value of Lacrimosa was never the code — it is the understanding: that the full loop is automatable, that it works, and that its implications extend far beyond coding.

If this makes you think, run with it — fork it, break it apart, write about it, argue with it, build something better. Lacrimosa is a blueprint shared openly — under a non-commercial license, because a system that automates the full engineering loop is not something to deploy at scale without thinking carefully about what it means. It is a mirror. Look at what one person and a few Max subscriptions accomplished, and extrapolate six months forward. We are not ready for what that implies. But we can start preparing.

Mozart completed eight bars of the Lacrimosa before the pen left his hand. His student Süssmayr finished the Requiem — competently, faithfully, but without Mozart's voice. The piece was completed. The music plays to this day. But something was lost in the handoff — the irreducible quality of the person who started it.

I think about that handoff when I consider the artifact I am releasing. This system will be outdated in months. Its architecture will be superseded, its patterns absorbed into platforms, its innovations made obvious by models that did not exist when I wrote it. As an artifact, it has the shelf life of any piece of technology in a field that moves this fast.

But the act of building it taught me something that will not expire. Crafting and operating an autonomous engineering loop requires — and develops — architectural judgment, business reasoning, operational awareness, and strategic thinking across every domain the system touches. You cannot build a system that senses product signals, triages engineering work, manages trust, calibrates quality, and tracks releases without understanding the full surface area of how software gets built, shipped, and maintained. That understanding transfers. The next generation of models will make the artifact obsolete, but the foundational knowledge and the ability to recognize where and how to apply it — that is what will distinguish the engineer from the outdated "code monkey."

Not the artifact. The judgment that came from building it.

The engineers who thrive in what is coming will not be the ones who cling to writing code by hand. And they will not be the ones who passively wait for the tools to do it for them. They will be the ones who built something like this — or understood it deeply enough to operate it — and carried that knowledge forward into whatever comes next.

The requiem is playing. The question is not whether to listen. It is what you build while you still can.

---

*Lacrimosa is open-source under a non-commercial license. Source code, documentation, and configuration examples are available on GitHub.*
