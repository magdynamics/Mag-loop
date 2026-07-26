# Mag Loop

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
- [`skills/mag-review`](skills/mag-review/SKILL.md) — reviews open PRs against
  their linked issue and required CI, then posts a three-group verdict. Runs
  repeatedly under `/loop /mag-review`.

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
human instead. Mag Loop does not treat missing CI as green, so without required
checks you get a review assistant rather than a factory.

Mag Loop does not create CI for your project. Your repository owns its build,
test, and security checks.

## Install

Paste this into Claude Code, inside the repo where you want the factory:

```text
Set up Mag Loop from https://github.com/magdynamics/Mag-Loop-.

1. Copy these files from that repo into this repo, preserving their contents:
   skills/mag-spec/SKILL.md   → .claude/skills/mag-spec/SKILL.md
   skills/mag-build/SKILL.md  → .claude/skills/mag-build/SKILL.md
   skills/mag-review/SKILL.md → .claude/skills/mag-review/SKILL.md

2. Check `claude --version` is 2.1.71 or newer.

3. Check that `gh auth status` and `gh repo view` both work. Detect this
   repository's real default branch; do not assume it is main. Confirm the
   authenticated account can push here.

4. Create these labels, ignoring any that already exist:
   agent-ready, blocked, agent-building, loop-approved,
   loop-changes-requested, needs-human-review, loop-stuck

5. List the required status checks on the default branch. If there are none,
   tell me plainly that Mag Loop will escalate every PR for human review until
   I configure at least one, and ask whether I want to continue anyway.

6. Confirm all three SKILL.md files have valid YAML frontmatter. Tell me to run
   `/reload-skills` (or restart Claude Code), then have me confirm `/skills`
   lists mag-spec, mag-build, and mag-review.

7. Smoke test by listing: open issues labeled agent-ready that are unassigned
   and not blocked; the default branch and its required checks; open pull
   requests with their Mag Loop labels. If every read succeeds and all three
   skills appear, tell me how to run my first spec and loop.
```

No placeholders to replace — `gh` infers the repository from the working
directory.

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
| `agent-building` | Builder | Claimed and in progress |
| `loop-approved` | Reviewer | No must-fix finding, required checks green, no conflict |
| `loop-changes-requested` | Reviewer | Must-fix findings; back to the builder |
| `needs-human-review` | Either | Scope conflict, missing CI, or a product decision |
| `loop-stuck` | Builder | Two repair rounds failed to converge |

`loop-approved` is **evidence for your merge decision, not permission for
anything to merge.**

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

Mag Loop is a port of [Finn-loop](https://github.com/finna/Finn-loop) by Alex
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
  `Mag Loop fix round N` comments and escalates to `loop-stuck` after two, so an
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
Mag Loop proper is prompt-only. It is kept because it works and it is tested;
delete `tools/verify-loop/` if you do not want it. See
[its design notes](tools/verify-loop/DESIGN.md).

## Validate

```bash
node scripts/validate.mjs
cd tools/verify-loop && python3 -m unittest discover -s tests
```
