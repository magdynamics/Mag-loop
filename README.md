# Mag-loop

Three Claude Code skills that turn GitHub Issues plus GitHub pull requests into
a small, human-gated software factory:

**idea → `/mag-spec` interviews you and files the issue → you label it
`agent-ready` → `/mag-build` claims it and opens a PR → `/mag-review` posts a
verdict → you merge.**

Three skills, one approval label, one rule: **humans merge.**

- [`skills/mag-spec`](skills/mag-spec/SKILL.md) — researches the repo,
  interviews you until the behavior is unambiguous, then files an issue with
  acceptance criteria (`AC-N`) and non-goals (`NG-N`).
- [`skills/mag-build`](skills/mag-build/SKILL.md) — claims the next safe
  `agent-ready` issue, implements only its contract, verifies it, and opens a
  PR. Runs repeatedly under `/loop /mag-build`.
- [`skills/mag-review`](skills/mag-review/SKILL.md) — reviews the PRs
  `mag-build` opened against their linked issue and required CI, then posts a
  three-group verdict. Runs repeatedly under `/loop /mag-review`.

There is no engine and no daemon. The scheduler is Claude Code's built-in
`/loop`; the durable state is GitHub Issues, labels, PRs, and CI. The `mag-`
prefix keeps these from colliding with bundled commands like `/review`.

## Requirements

- A repository on GitHub with a working `origin` remote
- [Claude Code](https://code.claude.com/docs/en/overview) 2.1.71 or newer
  (`/loop` arrived in that release)
- The GitHub CLI (`gh`), authenticated with write access to the repo
- **At least one required status check** on the default branch

That last one is not optional in spirit. `mag-review` refuses to apply
`loop-approved` to a repository with no required checks — it escalates to a
human instead. Mag-loop does not treat missing CI as green, so without required
checks you get a review assistant rather than a factory.

Mag-loop does not create CI for your project. Your repository owns its build,
test, and security checks.

## Install

Inside the repository you want the factory in:

```bash
scripts/install.sh --dry-run   # report what would change
scripts/install.sh             # install here
scripts/install.sh --target ../myapp
```

It copies the three skills into `.claude/skills/`, creates the seven labels,
and checks your prerequisites — Claude Code's version, `gh` authentication,
and whether the default branch has a required status check. Every step is
idempotent, so re-running is also how you upgrade.

Then run `/reload-skills` in Claude Code and confirm `/skills` lists
`mag-spec`, `mag-build`, and `mag-review`.

## Share it with a team

```bash
scripts/package.sh             # -> dist/mag-loop-0.1.0.tar.gz and .zip
```

That builds a self-contained package holding the three skills, the installer,
and [the team guide](docs/TEAM-GUIDE.md) — and nothing else, so the validator,
CI, and `verify-loop` stay behind. It validates before packaging. Hand the
archive to a developer, or attach it to a GitHub Release.

**[docs/TEAM-GUIDE.md](docs/TEAM-GUIDE.md) is what to read before a first run.**
It covers writing acceptance criteria the builder can execute, reading a
verdict, who owns which label, and when to use an ordinary Claude Code session
instead.

## Daily rhythm

1. Run `/mag-spec` whenever an idea lands. Read the filed issue. If you approve
   the exact contract, apply `agent-ready` yourself. **Only a human applies that
   label.**
2. Start `/loop /mag-build`. To have reviews run continuously, start
   `/loop /mag-review` in a second session.
3. Merge only PRs that are `loop-approved`, conflict-free, and green on every
   required check. A `needs-human-review` or `loop-stuck` PR needs you to read
   and resolve the reason first.
4. Answer the concrete question on any `blocked` issue, then remove the
   `blocked` label so a later build pass can resume it.

Run **one builder loop per repository.** The issue assignee is a cooperative
lock between people; two sessions on the same account cannot reliably lock each
other. Use separate worktrees if you deliberately run more than one.

`/loop` only runs while its Claude Code session is open. Watch the first few
passes, and your usage, before leaving a new installation unattended.

## The labels

| Label | Who sets it | Meaning |
|---|---|---|
| `agent-ready` | **Human only** | The contract is approved; an agent may build it |
| `blocked` | Builder | A specific question is waiting on a human |
| `agent-building` | Builder | Claimed and in progress; released on every exit |
| `loop-approved` | Reviewer | No must-fix finding, required checks green, no conflict |
| `loop-changes-requested` | Reviewer | Must-fix findings; back to the builder |
| `needs-human-review` | Either | Scope conflict, missing CI, or a product decision |
| `loop-stuck` | Builder | Two repair rounds failed to converge |

`loop-approved` is **evidence for your merge decision, not permission for
anything to merge.**

`agent-building` is the one label with a lifecycle worth understanding. The
builder adds it when it claims an issue and drops it on every way out — the PR
opens, the issue gets blocked, or the claim is abandoned because someone else
took it. Because the pick query only returns *unassigned* issues, a stale claim
would strand that issue permanently, so each build pass also sweeps for
`agent-building` issues with no open PR and releases them. That recovers work
left behind by a crashed pass or a PR closed without merging.

By default `mag-review` only reviews branches named `mag/*`, which is what
`mag-build` produces. It will not touch your teammates' PRs or Dependabot's
unless you widen that filter in the skill.

## The rules that make it work

- If it is not in the issue, it does not exist. No side-channel instructions.
- One issue per PR, sized to a day of agent work or less.
- Acceptance criteria are observable outcomes. Non-goals are binding. A PR
  comment cannot widen scope — only editing the issue can.
- Blocked issues and escalated PRs leave the automated queue until a human
  resolves them.
- **Spec quality is the bottleneck.** Vague acceptance criteria produce
  confident, wrong PRs. Let `/mag-spec` ask as many questions as it needs.
- Agents never merge and never enable auto-merge.

## Credit and what changed

Mag-loop is a port of [Finn-loop](https://github.com/finna/Finn-loop) by Alex
Finn (MIT), adapted for how Mag Dynamics already works. The architecture — three
skills, `AC-N`/`NG-N` contracts, the `agent-ready` human gate, the three-group
verdict, "humans merge" — is his. Deliberate differences:

- **GitHub Issues instead of Linear.** No Linear workspace, connector, or
  subscription. Issue references are `#N`, so `Closes #N` closes the issue on
  merge natively. Linear's workflow states become the `agent-building` label,
  and its blocked-by relations become a `Blocked by #N` section the builder
  checks before claiming.
- **A repair-round cap, built in.** Finn-loop lists self-convergence as the
  first thing to add after the starter is stable. The builder counts
  `Mag-loop fix round N` comments and escalates to `loop-stuck` after two, so an
  unattended loop cannot ping-pong with the reviewer indefinitely.
- **`scripts/validate.mjs`** asserts the safety properties of all three skills
  in CI — that the builder still refuses dirty worktrees, that the reviewer
  still refuses to call absent CI green, and twenty other invariants. Prompts
  have no type checker; this is the substitute, and it doubles as the required
  check this repository needs.

Read Finn-loop's README for the ten-layer roadmap beyond the starter loop
(Slack control plane, risk-tiered merging, leased workers, post-merge learning).
Those apply here unchanged.

## `tools/verify-loop` — optional, unrelated

A standalone Python loop engine (`magloop`) for grinding a single goal to green
against a verify command, with its own on-disk state and iteration budget. I
built it before seeing Finn-loop, and it is **not part of this architecture** —
Mag-loop proper is prompt-only. It is kept because it works and it is tested;
delete `tools/verify-loop/` if you do not want it. See
[its design notes](tools/verify-loop/DESIGN.md).

## Validate

```bash
node scripts/validate.mjs
cd tools/verify-loop && python3 -m unittest discover -s tests
```
