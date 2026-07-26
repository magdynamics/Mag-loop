# Mag-loop — team guide

Mag-loop is three Claude Code skills that turn GitHub Issues and pull requests
into a human-gated software factory. An agent writes the code; a person decides
what gets built and what gets merged.

One rule underpins everything: **humans merge.** Agents research, draft, code,
test, and propose. They never merge and never enable auto-merge.

Read this once before your first run. It is the whole contract.

---

## 1. Install

Mag-loop is a **machine-wide skill set, not a per-project one.** The three
skills name no repository — they infer it from your working directory — so you
install them once and they work everywhere. Only the labels are per-project.

**Once per machine:**

```bash
./install.sh --global      # -> ~/.claude/skills/
```

Then run `/reload-skills` in Claude Code, and confirm `/skills` lists
`mag-spec`, `mag-build`, and `mag-review`. Those commands now exist in every
repository you open.

**Once per project you want the loop in:**

```bash
cd ~/code/some-project
/path/to/mag-loop/install.sh --labels-only
```

That creates the seven labels and reports whether the default branch has a
required status check. Nothing gets copied into the project, so there is no
per-project version to keep in sync — upgrading is one `--global` re-run.

Add `--dry-run` to either command to report without changing anything. Both are
idempotent.

You need: a GitHub repo with a working `origin`, Claude Code 2.1.71 or newer
(`/loop` arrived there), and `gh` authenticated with write access.

### Working across several projects

The loop is repository-scoped at run time, not machine-scoped: each pass reads
the queue of whichever repo you are in. So `/loop /mag-build` in
`~/code/project-a` will only ever touch project A's issues and branches.

Two consequences worth knowing:

- **One builder loop per repository**, and one Claude Code session per loop.
  Two builder loops in the same repo can race on the same issue. Two loops in
  *different* repos are fine and independent.
- A project you have not run `--labels-only` on has no `agent-ready` label, so
  the builder finds an empty queue and ends the pass. It fails safe rather than
  inventing work.

If you pin one project to an older version by installing into its
`.claude/skills/`, that copy **shadows** the global one for that project only.
The installer warns when both exist.

### The one prerequisite people skip

**At least one required status check on your default branch.** `mag-review`
refuses to apply `loop-approved` to a repository with no required checks — it
escalates to a human instead, because Mag-loop does not treat missing CI as
green. Without it you get a careful review assistant rather than a factory.

Configure it in Settings → Branches → Branch protection rules. The installer
warns you when it is missing.

---

## 2. The daily rhythm

About fifteen minutes of human time.

**Capture an idea.** Run `/mag-spec` and describe it roughly. It will research
the code, then interview you — expect more questions than you are used to, with
no cap on rounds. It files a GitHub issue with numbered acceptance criteria
(`AC-1`, `AC-2`…) and non-goals (`NG-1`, `NG-2`…).

**Approve it.** Read the filed issue. If, and only if, the contract is exactly
what you want built, apply the `agent-ready` label yourself. That label is the
single gate between an idea and an agent writing code against it, and no skill
will ever apply it for you.

**Start the loop.** `/loop /mag-build`. Each pass claims one issue, implements
only its contract, verifies it, and opens one pull request. For continuous
review, run `/loop /mag-review` in a second session.

**Merge.** Only pull requests that are `loop-approved`, conflict-free, and green
on every required check. `loop-approved` is evidence for your decision, not
permission for anything to merge.

**Unblock.** Answer the concrete question on any `blocked` issue, then remove
the `blocked` label so a later pass can resume it.

Run **one builder loop per repository.** The issue assignee is a cooperative
lock between people, not an atomic one — two sessions on the same account cannot
reliably lock each other. Use separate worktrees if you need parallelism.

`/loop` only runs while its Claude Code session is open. Watch the first few
passes, and your usage, before leaving a new installation unattended.

---

## 3. Writing a spec that works

**Spec quality is the bottleneck.** Everything downstream inherits it. A vague
acceptance criterion produces a confident, wrong pull request, which costs a
full review cycle plus your attention — far more than another round of
questions would have.

The test `mag-spec` applies before it stops asking:

> Could two competent engineers read this spec independently and ship the same
> observable behavior?

Answer its questions properly. It only asks about things the codebase cannot
answer — genuine product decisions, scope boundaries, edge cases that move
acceptance criteria.

Good acceptance criteria are **observable outcomes**, not implementation notes:

| Weak | Strong |
| --- | --- |
| Refactor the auth module | AC-1 — An expired token returns 401 with `{"error":"token_expired"}` |
| Make the list faster | AC-1 — The issue list renders in under 200 ms with 1,000 rows |
| Fix the mobile layout | AC-1 — At 375 px the site view scrolls vertically only, with no horizontal overflow |

**Non-goals are binding.** They are how you stop an agent from tidying up
adjacent code, renaming things, or "improving" something you deliberately left
alone. Use them freely — `NG-1 — Do not change the database schema` is worth
more than three paragraphs of explanation.

**Size every issue to one day of agent work or less.** Bigger work becomes a
chain of small issues connected with a `Blocked by #N` section, ordered so each
is buildable using only the merged output of the ones before it. The builder
checks those blockers are closed before claiming.

---

## 4. Reading a verdict

`mag-review` posts one comment per reviewed commit:

```
Mag-loop review of <sha>

CI: required checks passed | failed | not configured
Mergeability: clean | conflicting

## Review
Summary: what this PR does.

## 1. Must fix before merge
## 2. Should fix soon
## 3. Safe to merge
```

Every must-fix finding is tagged, which tells you who should act:

| Tag | Meaning |
| --- | --- |
| `[AC-N]` | The PR does not satisfy that acceptance criterion |
| `[DEFECT]` | Broken implementation, but inside the authorised scope |
| `[SECURITY]` | Severe enough on its own to block shipping |
| `[CI]` | A required check failed |
| `[SCOPE-CONFLICT AC-N ↔ NG-N]` | The contract contradicts itself — **your** call, not the agent's |

A scope conflict means an acceptance criterion cannot be satisfied without
violating a non-goal. No agent can resolve that. Edit the issue, then remove
`needs-human-review`.

---

## 5. The labels

| Label | Who sets it | Meaning |
| --- | --- | --- |
| `agent-ready` | **You, only** | Contract approved; an agent may build it |
| `blocked` | Builder | A specific question is waiting on a human |
| `agent-building` | Builder | Claimed by a pass; released on every exit |
| `loop-approved` | Reviewer | No must-fix, required checks green, no conflict |
| `loop-changes-requested` | Reviewer | Must-fix findings; back to the builder |
| `needs-human-review` | Either | Scope conflict, missing CI, or a product call |
| `loop-stuck` | Builder | Two repair rounds failed to converge |

Two of these take work **out** of the automated queue until a person acts:
`needs-human-review` and `loop-stuck`. The builder skips both. Nothing will
happen to that pull request until you resolve the cause and remove the label.

`agent-building` is the one with a lifecycle worth knowing. The builder adds it
when claiming and drops it on every exit — the PR opens, the issue gets blocked,
or the claim is abandoned. Because the pick query only returns *unassigned*
issues, a stale claim would strand that issue permanently, so each pass also
sweeps for `agent-building` issues with no open PR and releases them. That
recovers work orphaned by a crashed pass or a PR closed without merging. The
sweep will not touch an issue assigned to a person.

---

## 6. The rules that make it work

- **If it is not in the issue, it does not exist.** No side-channel
  instructions in chat, Slack, or a PR comment.
- **One issue per pull request**, sized to a day of agent work or less.
- **Acceptance criteria are observable; non-goals are binding.** A PR comment
  cannot widen scope. Only editing the issue can.
- **Blocked issues and escalated PRs leave the queue** until a human resolves
  them.
- **Agents never merge** and never enable auto-merge.
- **Only a human applies `agent-ready`.**

---

## 7. When not to use it

Mag-loop is for work whose finished state you can write down in advance. Reach
for an ordinary Claude Code session instead when:

- **You are diagnosing something.** There is no acceptance criterion for "find
  out why the runners will not start."
- **The change is genuinely one-shot and small.** The spec-approve-claim-review
  ceremony costs more than a two-line fix.
- **You are exploring.** Spikes and prototypes have no stable contract to
  enforce, which is the whole mechanism.
- **The work touches everything.** A sweeping refactor cannot be scoped to one
  issue with an honest `Other behavior changes: None`.

Expect a split in practice: the loop for features and bugs, direct conversation
for understanding.

---

## 8. Troubleshooting

**`/mag-spec` is not in `/skills`.** Run `/reload-skills`, or restart Claude
Code. Check the files landed in `.claude/skills/`, not `skills/`.

**Every PR ends up `needs-human-review`.** You have no required status checks.
See §1.

**The builder says the queue is empty but issues are waiting.** They must be
open, labeled `agent-ready`, *unassigned*, not labeled `blocked`, and have all
`Blocked by #N` issues closed. An issue still assigned from an earlier pass is
the usual culprit; the reclaim sweep handles it on the next pass.

**A PR sits at `loop-changes-requested` and nothing happens.** Check for
`needs-human-review` or `loop-stuck` alongside it. The builder skips both by
design.

**The builder refuses to start.** It requires a clean worktree, and it will
never stash, reset, or commit work it did not create. Commit or stash your own
changes first.

**Nothing is reviewed.** By default `mag-review` only looks at `mag/*` branches,
which is what `mag-build` produces. That keeps it off your teammates' and
Dependabot's pull requests. Widen the filter in the skill if you want it
reviewing everything.

---

## Credit

Mag-loop is a port of [Finn-loop](https://github.com/finna/Finn-loop) by Alex
Finn (MIT), adapted to run on GitHub Issues instead of Linear. The
architecture — three skills, `AC-N`/`NG-N` contracts, the `agent-ready` gate,
the three-group verdict, "humans merge" — is his. Read Finn-loop's README for
the roadmap beyond this starter loop: Slack control plane, risk-tiered merging,
leased persistent workers, post-merge learning.
