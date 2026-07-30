# GPM Design Package — Review & Build Guide

**Reviewing:** Global Project Management Tool (GPM), System Design Package v1.0
**Date:** 2026-07-30
**Status:** Review complete — recommendations + implementation guideline

---

## Part A — Overall Assessment

The package is a strong v1.0. Its two best decisions are worth protecting through
every later trade-off:

1. **A single named problem.** "Agreed requirements silently going undone" gives the
   whole platform a success criterion. Every scope decision below is tested against it.
2. **"Minimize manual entry, maximize automated capture."** For a 3–5 person team this
   is the only viable posture — a governance tool that demands data entry from five
   busy people dies in a month.

The main risks are not in what the package says, but in what it leaves undefined and
in how much it tries to build:

| # | Risk | Severity | Where addressed |
|---|---|---|---|
| 1 | **Scope vs. team size.** 5 layers + 15 agents + a chat system + a design system is a multi-year product for a team that also has day jobs. | High | §B.9, Part C phasing |
| 2 | **The `Task` entity is never defined**, yet requirement-to-task mapping is the enforcement core. | High | §B.2 |
| 3 | **Flags have no lifecycle.** Agents "flag" and "escalate" everywhere, but there is no entity that holds a flag, no owner, no resolved state. Flags will silently go undone — the exact problem GPM exists to solve, one level up. | High | §B.3 |
| 4 | **No eventing/trigger architecture.** Agents are listed with responsibilities but nothing defines *when they run* or *how they're allowed to write*. | High | §B.6, §C.4 |
| 5 | **Deterministic rules and LLM agents are mixed together.** Several "agents" (flag rules, ID assignment, gate blocking) are plain queries/code and must be deterministic to be trustworthy. | Medium | §B.7 |
| 6 | **UX governance as a manual gate will be bypassed.** "Any UI change requires a PMO change request" is too heavy for 3–5 people; encode the handbook as CI checks instead. | Medium | §B.5 |
| 7 | **PMO lands in Phase 2**, but PMO *is* the named problem. The thinnest useful slice of GPM is a requirements registry with flags — it should ship first. | Medium | Part C |
| 8 | Minor: §8 says "Twelve specialized agents" but lists 15. | Low | §B.7 |

**Bottom line recommendation:** build it as a **modular monolith on one database with
an event log at the center**, ship the PMO registry + flags first, consolidate the 15
agents into ~6 runtime services, and enforce UX governance through CI rather than
meetings. Details follow.

---

## Part B — Component-by-Component Review

### B.1 Admin Platform (§3)

**Sound:** four roles is the right number for this team size; department/team CRUD is
straightforward; audit log on permission changes is correct.

**Gaps & recommendations:**

- **Capacity is named but not modeled.** Dashboards (§3.4) and three agents
  (Decision-Support, Scheduling, Capacity Planning) all consume "capacity," but nothing
  defines it. Minimum viable model: `TeamMember.hours_per_week` (default 40 × allocation
  fraction) and `Commitment(member, project, hours_per_week, start, end)`. Utilization
  is then a query, not an agent.
- **Skills taxonomy missing.** Decision-Support is supposed to detect "skill gaps" — that
  requires `Skill` and `MemberSkill(level)` tables. Keep it to a flat tag list (≤30 tags);
  a formal competency framework is overkill.
- **"Historical team performance (velocity, on-time delivery rate)"** — derive these from
  task completion data; do not build a separate tracking feature. They only become
  meaningful after ~2 quarters of real data, so exclude from early phases.
- **Add agent identities.** Every AI agent should be a first-class principal (a `User`
  with `kind = 'agent'` and scoped permissions) so the audit trail (§5.6) and
  accountability (§5.5) fall out naturally: "who did this" is answered the same way for
  humans and agents.
- **Dashboards:** status roll-up rules must be explicit or dashboards lie. Recommend
  deterministic derivation: a project is *at-risk* if any linked requirement is At
  Risk/Overdue or any open flag is ≥ severity=high; *blocked* if a gate is failing or a
  dependency flag is open. Never let status be a hand-set field with no backing data.

### B.2 Project Catalog (§4)

**Sound:** project-as-hub with a unique ID is the correct spine. The
`GPM-{project_id}-{short-name}` naming convention is a great, cheap idea — it turns
asset discovery into a string match.

**Gaps & recommendations:**

- **Define the `Task` entity — it's the biggest omission in the package.** Everything in
  the PMO depends on it. Minimum:

  ```
  Task: id, project_id, title, description,
        owner_id (User — human or agent), status (todo/in_progress/blocked/done/cancelled),
        due_date, estimate_hours, created_by, source (manual/agent/import),
        external_ref (e.g. GitHub issue URL)
  RequirementTask: requirement_id, task_id   -- the many-to-many the flag rules run on
  TaskDependency: task_id, depends_on_task_id
  ```

- **Add `Project` to the entity list** with lineage: `idea_id` (traceability back to
  intake) and `charter_id`. The intake → decision → project chain should be walkable in
  both directions.
- **`sponsor` should be a foreign key to `User`**, not free text — sponsors receive
  escalations, so they must be addressable.
- **Stage needs a transition rule, not just an enum.** Formalize: stage can only advance
  when all gates configured for the current stage are approved. That single sentence is
  the entire mechanical link between §4 and §5.4 — write it into the spec.
- **Asset links:** store `{type, url, external_id, verified_at}`. The Archiving agent's
  real job is reconciliation: scan GitHub/Drive for `GPM-*` names, match to projects,
  flag orphans and misnamed assets. That's a nightly deterministic job with an LLM only
  for fuzzy matching suggestions.

### B.3 PMO (§5) — the heart of the system

**Sound:** the Requirements Registry with versioning, the two flag rules in §5.2, gates
blocking stage progression, and immutable approvals are exactly right. This layer is the
product; everything else is amplification.

**Gaps & recommendations:**

- **Give flags a first-class entity and lifecycle.** This is the most important single
  change to the package:

  ```
  Flag: id, type (unlinked_requirement / scope_slip / overdue / dependency_risk /
        gate_blocked / capacity / drift / custom),
        severity (info/warn/high/critical),
        subject_type + subject_id (requirement, task, project, gate…),
        raised_by (rule id or agent id), raised_at,
        status (open / acknowledged / resolved / dismissed),
        owner_id, resolution_note, resolved_at
  ```

  Rules: every flag has an owner; a flag dismissed requires a note; critical flags
  escalate to the sponsor after N days open. Without this, "flagged immediately" (§5.2)
  has nowhere to land and the enforcement backbone enforces nothing.
- **Make the flag rules deterministic queries, not agents.** "Requirement with zero
  linked tasks" and "all tasks complete but requirement open" are SQL. Run them on every
  relevant write (event-triggered) plus a nightly sweep. Reserve LLMs for judgments
  (e.g., "does this deliverable satisfy the acceptance criteria?").
- **Acceptance criteria should be structured** (a checklist of assertions, each
  checkable manually or by an agent), not a prose blob. This is what makes §5.5's
  validation rule engine possible: the engine iterates criteria; each is either
  human-attested, rule-checked, or LLM-assessed-with-human-confirmation.
- **Requirement status (§5.3) should be derived, not typed:** Not Started = no task
  started; On Track = tasks progressing and due dates safe; At Risk = open high-severity
  flag or forecast slip; Overdue = past due, not complete; Complete = all acceptance
  criteria satisfied *and* attested. Derived status can't silently rot.
- **Define "immutable" concretely** (§5.6): an append-only `audit_log` table — no UPDATE
  or DELETE grants for the application role, writes only via a single audited code path,
  every entry `{actor_id, action, subject, before, after (JSON), at}`. Hash-chaining is
  optional; append-only + DB permissions + backups is sufficient for an internal tool.
  Log agent actions with the agent's principal ID and the triggering event ID.
- **Gate approvals need identity strength:** approval must come from an authenticated
  session of a named human (or, for automated gates like CI checks, a named agent
  principal with the check output attached). No approving on someone's behalf.

### B.4 UX Governance (§6) — right goal, wrong mechanism

**Sound:** treating UX consistency as a requirement, versioning the design system,
gating screens on compliance.

**The problem:** §6.3 routes *any* UI change through a PMO change request and gate
approval. For a 3–5 person team shipping their own internal tool, that gate will either
be rubber-stamped (governance theater) or stall work until people route around it.
Manual review doesn't scale down.

**Recommendation — govern by CI, not by committee:**

1. **The handbook is code.** Design tokens (colors, spacing, type) as a token file;
   components in a small shared library with Storybook as the living, versioned
   handbook. Screen user stories live as markdown alongside the components.
2. **Compliance testing (§6.4) is a pipeline, not a meeting:**
   - lint rule: screens may only import from the component library (no ad-hoc styles);
   - visual regression (Playwright screenshot diff) against approved baselines;
   - accessibility: `axe-core` in CI + keyboard-nav smoke tests;
   - interaction specs (§6.2) written as Playwright tests.
   A green pipeline **is** the §5.4 gate approval, logged automatically by an agent
   principal ("UX-CI") with the run attached.
3. **Reserve human gate approval for one case only:** introducing a *new* pattern or
   changing a token/component (i.e., changing the handbook itself). That's rare enough
   to review properly.
4. Design-system versions map to git tags of the component library — you get §6.3's
   version history for free.

### B.5 Workspace (§7)

**Sound:** the three-way decision with mandatory logged reasoning is excellent;
intake-agent structuring beats forms; launch meeting output feeding the Requirements
Registry closes the loop between "what we said" and "what we track."

**Gaps & recommendations:**

- **"Table" needs a revisit mechanism or it's a graveyard.** Add `revisit_on` (date) or
  `revisit_when` (condition, e.g. "when team X frees up") to the Decision entity, plus a
  scheduled job that re-surfaces tabled ideas. Otherwise tabled ideas are requirements
  silently going undone, pre-project.
- **Don't build a chat system.** §7.6's goal ("discussion tied to the project, not
  scattered") is right, but building messaging means building presence, threads,
  notifications, mobile — a product in itself, and people won't leave Slack anyway.
  Instead: **each project/idea gets a bound Slack channel or thread**; the Communication
  Agent ingests it (summaries, decisions, action items → PMO, with human confirmation).
  The workspace UI shows the *distilled* record — decisions, action items, summaries —
  which is the part that actually matters for governance. Same principle as intake:
  capture where people already are.
- **Intake dedup:** ideas arriving via form + Slack + email will duplicate. The Intake
  Agent should check similarity against open intakes/projects and propose merges.
- **Launch meeting (§7.5):** "captured in real time" should mean: meeting transcript or
  shared notes → extraction agent proposes charter entries (decisions, assignments,
  success criteria, requirements) → **humans confirm each item before it enters the
  Requirements Registry**. Auto-capture, human-ratify. Never let unratified extraction
  become a binding requirement.
- **Decision-Support Agent output should be a scorecard** (capacity fit, skill fit,
  strategic fit, risk notes), each with the evidence it used — not a bare go/no-go
  recommendation. The team is the decider; the agent's job is to make the trade-offs
  visible.

### B.6 AI Agent Ecosystem (§8) — consolidate 15 into 6

First the small fix: the section header says twelve agents; the table lists fifteen.

The deeper issue: 15 separately-built agents is an operational burden (15 prompts, 15
eval sets, 15 failure modes) and many overlap heavily. Group by *runtime shape* instead
of by responsibility. Everything in the package survives — as rule packs and skills
inside six services:

| Runtime service | Absorbs package agents | Shape |
|---|---|---|
| **1. Intake & Decision Service** | Intake (1), Decision-Support (2) | Event: idea received → structure → scorecard → await decision |
| **2. Provisioning Service** | Project Charter (3), Scheduling (4), Archiving (7) | Event: Go decision → create catalog entry, draft charter, checklist, book meeting; nightly asset reconciliation |
| **3. Extraction Service** | Communication (6), Knowledge Extraction (11) | Event: new discussion/meeting content → summarize, extract decisions/actions/knowledge → human-ratify queue |
| **4. Watchdog Service** | Follow-up (5), Dependency (10), Capacity (12), Risk (14) | Scheduled sweeps + event triggers → raise/update/escalate Flags. Mostly deterministic rules; LLM only for narrative risk summaries |
| **5. Verification Service** | Task Accountability (8), Requirements Traceability (9), Compliance Enforcement (13) | Event: task/requirement marked done → check against acceptance criteria & UX pipeline → attest or flag |
| **6. Change Management Service** | Change Management (15) | Event: change request → impact analysis (linked requirements/tasks/dependencies) → route through gates |

Benefits: one agent runtime, one observability story, shared context-building code, and
a much smaller eval surface. The package's per-agent spec discipline ("trigger, inputs,
outputs, success criteria") applies per *capability* within a service.

**Agent governance rules (add these to the spec — they're currently absent):**

1. **Every agent action is either `draft` (human ratifies) or `auto` (logged, reversible).**
   Every capability launches in draft mode; promote to auto only after its precision is
   proven on real usage. Destructive or externally-visible actions (sending messages,
   closing requirements) stay draft-mode indefinitely.
2. **Agents propose; rules enforce.** Anything that blocks or unblocks work (gates, stage
   transitions, flag rules) is deterministic code. LLM output feeds human decisions or
   raises flags — it never silently gates.
3. **Structured outputs only.** Every LLM call returns JSON against a schema, validated
   before write. Free-text goes only into fields meant for prose (summaries, notes).
4. **Per-capability spec:** trigger event(s), input context, output schema, write scope
   (which tables/fields it may touch), draft/auto mode, escalation path, eval set, token
   budget.
5. **Measure precision, not just activity.** Track per capability: proposals made,
   accepted, edited, rejected. A flag stream with >30–40% dismissals gets ignored by
   humans within weeks — false-alarm rate is the metric that decides promotion to auto
   mode or retirement.
6. **Every agent run is recorded:** `AgentRun {capability, trigger_event, input_refs,
   output, status, tokens, cost, latency}` — this is §5.5's accountability made concrete,
   and it's also your cost dashboard.

### B.7 Answers to the Open Questions (§10)

1. **Time tracking:** No actual-hours tracking in v1 — it's the highest-friction data
   entry there is, and the named problem doesn't need it. Derive progress from task
   status + due dates; model capacity as planned commitments (§B.1). Revisit only if
   forecasting proves inaccurate after two quarters.
2. **Integration priority:** ① Slack (intake capture + notifications + discussion
   ingestion — it powers three subsystems), ② GitHub (asset linking, task sync, CI
   signals for gates), ③ Google Calendar (Scheduling service), ④ Google Drive
   (archiving/reconciliation), ⑤ email last (intake only).
3. **Notifications:** In-app inbox is the **system of record** (it's just the Flag +
   ratification queues); Slack is the delivery channel. Default to a per-person daily
   digest; real-time Slack ping only for `critical` flags and gate blocks; email only
   for weekly sponsor digests. Per-user overrides. The failure mode to design against is
   notification fatigue — a muted channel means the enforcement backbone goes blind.
4. **Authentication:** SSO via Google Workspace (OIDC) — the team already lives in
   Drive/Gmail, it eliminates password management, and deactivation (§3.1) becomes
   "disable the Google account." No standalone accounts. Agents authenticate as service
   principals with scoped API tokens.

---

## Part C — Build Guideline

### C.1 Architecture: modular monolith around an event log

Do **not** build five layers as five services. For this team size:

```
┌────────────────────────────────────────────────────────┐
│  Web app (React + shared component library/Storybook)  │
└──────────────────────────┬─────────────────────────────┘
┌──────────────────────────┴─────────────────────────────┐
│  API (single TypeScript service, modular by domain)     │
│  modules: admin · catalog · pmo · workspace · knowledge │
│  every state change → domain event (outbox table)       │
└──────────────────────────┬─────────────────────────────┘
┌──────────────────────────┴─────────────────────────────┐
│  Worker (single process)                                │
│  • deterministic rule packs (flags, gates, reconcile)   │
│  • 6 agent services (Claude Agent SDK), draft/auto      │
│  • integrations: Slack · GitHub · Google                │
└──────────────────────────┬─────────────────────────────┘
        ┌──────────────────┴──────────────────┐
        │  Postgres: domain tables + events +  │
        │  audit_log + agent_runs + job queue  │
        └─────────────────────────────────────┘
```

- **One Postgres database** holds everything: domain data, the append-only event/outbox
  table, audit log, agent runs, and the job queue (pg-boss). No Kafka, no Redis, no
  microservices — you can add them later if ever needed; you cannot un-add them.
- **The event log is the keystone.** Every mutation emits an event
  (`idea.received`, `decision.made`, `project.created`, `task.completed`,
  `requirement.updated`, `gate.approved`, `flag.raised`, `content.ingested`, …).
  Agents and rule packs are *subscribers*. This single pattern answers "when do agents
  run," powers the audit trail, and makes replay/debugging possible.
- **Agent runtime:** Claude Agent SDK inside the worker. Each of the six services is a
  subscriber with a set of capabilities; all writes go through the same API layer as
  humans (agent principal + permission scopes), never raw SQL — so audit and RBAC apply
  uniformly.

### C.2 Recommended stack (opinionated, minimal)

| Concern | Choice | Why |
|---|---|---|
| Language | TypeScript end-to-end, monorepo (pnpm) | One language for 3–5 people; shared types between API/UI/agents |
| Web | React + Vite (or Next.js), Storybook | Storybook doubles as the UX handbook (§B.4) |
| API | NestJS or Fastify + zod schemas | Modular monolith; zod schemas shared with agent output validation |
| DB/ORM | Postgres + Drizzle or Prisma | Migrations, one store for everything |
| Jobs/events | pg-boss (Postgres-backed queue) + outbox table | No extra infra |
| Agents | Claude Agent SDK (`claude-sonnet-5` default; `claude-opus-5` for decision scorecards & impact analysis; `claude-haiku-4-5` for high-volume summarization) | Match model cost to task stakes |
| Auth | Google Workspace OIDC | §B.7.4 |
| Testing | Vitest; Playwright + axe-core (also the UX gate) | Tests *are* the governance pipeline |
| Deploy | Docker Compose on a single VM, or Fly.io/Railway; nightly `pg_dump` offsite | Internal tool for ≤5 users — keep ops near zero |
| Observability | Structured logs + a simple in-app admin page over `agent_runs` and `flags` | Your own dashboards; no external APM needed at this scale |

### C.3 Core schema (build order)

Phase-1 tables: `users` (humans + agents), `roles`, `departments`, `teams`,
`team_memberships`, `projects`, `tasks`, `requirement*` tables, `flags`, `audit_log`,
`events` (outbox). Phase-2: `approval_gates`, `gate_approvals`, `ideas`, `decisions`,
`commitments`. Phase-3: `agent_runs`, `ratification_queue`, `knowledge_articles`,
`asset_links`, `change_requests`. Key entities are specified in §B.2 (Task), §B.3
(Flag, audit), and §B.6 (AgentRun).

### C.4 Phased roadmap (re-sequenced from §9)

The package's Phase 1 is admin plumbing; the named problem isn't addressed until
Phase 2. Re-sequence so **every phase ends with something the team uses daily**, and
the problem-solving core ships first. Durations assume ~2 people part-time on the build.

**Phase 0 — Walking skeleton (1–2 weeks)**
Repo, CI, deploy pipeline, OIDC login, Postgres with migrations, event outbox pattern
proven end-to-end with one toy event, component library seeded with tokens + 5 base
components + Storybook + axe in CI.
*Exit: a deployed authenticated page; a commit that violates a lint/a11y rule fails CI.*

**Phase 1 — The enforcement core (3–4 weeks)** ← the re-sequenced heart
Users/teams/departments (minimal CRUD), Project Catalog with ID generation, Tasks,
Requirements Registry with versioning + structured acceptance criteria,
requirement↔task mapping, **deterministic flag rules + Flag lifecycle UI**, append-only
audit log, basic status dashboard (derived statuses).
*Exit: the team runs one real project through it; both §5.2 flag rules fire on real
data; every change is in the audit log. GPM is already solving its named problem —
with zero AI.*

**Phase 2 — Gates & intake flow (3–4 weeks)**
Approval gates + stage-transition blocking, idea intake (manual form first), three-way
decision with logged reasoning + tabled-idea revisit dates, project conversion,
compliance dashboard roll-ups, Slack notifications (digest + critical pings).
*Exit: a project cannot skip a gate; a tabled idea resurfaces automatically; sponsors
get a weekly digest.*

**Phase 3 — First agents, draft mode (4–6 weeks)**
Agent runtime (Claude Agent SDK + `agent_runs` + ratification queue). Ship in order of
value-per-risk: ① Intake structuring (Slack/email → structured intake), ② Extraction
(Slack thread + meeting notes → decisions/action items → ratify → PMO), ③ Provisioning
(charter draft, checklist, calendar booking), ④ Decision scorecard.
*Exit: raw idea → structured intake with no form-filling; meeting → ratified
requirements in the registry; every agent action visible in `agent_runs` with
accept/edit/reject tracked.*

**Phase 4 — Watchdog & verification (4–6 weeks)**
Watchdog service (deadline/dependency/capacity/risk sweeps → flags with owners and
escalation), Verification service (acceptance-criteria checking, scope-drift
detection), UX compliance pipeline wired as an automated gate, GitHub + Drive
reconciliation (naming convention audit). Promote proven Phase-3 capabilities from
draft to auto based on precision data.
*Exit: a requirement can't be marked complete without its criteria attested; missed
deadlines escalate to sponsors without human triage.*

**Phase 5 — Intelligence & polish (ongoing)**
Knowledge extraction into the KB (with provenance links), change management service
with impact analysis, capacity forecasting, portfolio compliance reporting exports,
historical team-performance views (now that real data exists).

### C.5 Definition of "fully operational"

Treat these as the platform's own PMO requirements — load them into GPM in Phase 1 and
let it track its own completion:

**Functional** — ✅ idea→decision→project→launch flow runs without manual data re-entry;
✅ both flag rules + overdue/dependency sweeps run on schedule; ✅ gates mechanically
block stage transitions; ✅ every requirement traceable idea → decision → charter →
tasks → attestation; ✅ audit export answers "committed vs. delivered" per project/team.

**Agent quality** — ✅ every capability has an eval set and a live precision metric;
✅ ≥80% acceptance rate before any capability leaves draft mode; ✅ flag dismissal rate
< 30%; ✅ monthly token cost visible per capability.

**Operational** — ✅ nightly backups with a tested restore; ✅ deploy is one command and
rollback-able; ✅ failed agent runs alert and are replayable from the event log;
✅ integration token expiry monitored; ✅ a runbook covering: Slack outage, LLM API
outage (system degrades to manual-entry mode — deterministic core keeps working), and
DB restore.

**Adoption (the real bar)** — ✅ the team runs *all* projects in it, including GPM's own
development, for a full quarter; ✅ zero governance work happens in side spreadsheets;
✅ in retrospective: at least one real "would have silently slipped" catch credited to
the system.

### C.6 Process recommendations

1. **Dogfood from Phase 1, day one:** GPM's own build is the first project in the
   catalog; its phase exits are its own gated requirements.
2. **One weekly 30-min governance review:** open flags, agent precision numbers,
   draft→auto promotions. This meeting *is* the human half of the PMO.
3. **Spec before build for each agent capability** using the §B.6 template — the
   package already mandates this (§8); hold that line.
4. **Resist building chat, time tracking, and per-agent microservices** — the three
   most tempting scope traps in this package, all addressed above (§B.5, §B.7.1, §B.6).

---

*End of review.*
