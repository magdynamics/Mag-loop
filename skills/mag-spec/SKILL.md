---
name: mag-spec
description: Interview the user about a rough idea until the behavior is unambiguous, then file a build-ready GitHub issue. Use when asked to run Mag-loop's spec interview, write a queue-ready issue, or plan a feature before building it. Interactive — the user must be present; never run this under /loop.
---

# Mag-loop spec interview

Turn a rough idea into a GitHub issue so complete that a build agent needs
nothing else. Research the code, interview the user in rounds until the
behavior is unambiguous, draft, confirm, file.

The division of labour is strict: **the user owns product decisions, you own
the codebase.** Never guess a product decision, and never ask the user
something you could answer by reading the repo.

## 1. Research before you ask

Read the relevant code first. Work out which files are involved, what patterns
already exist, what the current behavior actually is, and what constraints
apply. Questions that the repository already answers waste the user's attention
and make them trust the rest of the interview less.

## 2. Interview in rounds

Ask one to four questions per round. Give concrete options for each, with your
recommendation first. Ask only about things that genuinely change what gets
built:

- **Behavior forks** — who sees this, what exactly happens, where does it live
- **Scope boundaries** — what is explicitly not part of this issue
- **Edge cases that move acceptance criteria** — empty states, permissions,
  concurrent use, failure handling
- **Data implications** — existing records, migrations, backfills

Fold each round's answers into your working draft, then apply the confidence
test:

> Could two competent engineers read this spec independently and ship the same
> observable behavior?

If any fork remains, ask another round. **There is no cap on rounds.** A small
fix might take two questions; a real feature can legitimately take twenty.
Never stop early because it feels like a lot of questions — an under-specified
issue produces a confident, wrong pull request, and that costs far more than
another round. Once the test passes, stop. Do not pad with filler questions.

## 3. Draft the issue

Use exactly this shape:

```md
## Problem

The user or business problem this solves, in one or two sentences.

## Acceptance criteria

- [ ] AC-1 — Observable, testable outcome
- [ ] AC-2 — Observable, testable outcome

## Non-goals

- NG-1 — What must not change as part of this issue
- NG-2 — What is explicitly excluded or deferred

## Relevant files

- path/to/file.ts — why it matters

## Test expectations

- What should be covered, automatically or manually

## How to verify

1. Numbered steps anyone can follow to confirm the work: where to go, what to
   do, what should happen. Cover every AC.

## Blocked by

- #123 — optional; omit this section when nothing blocks the issue
```

Rules for the draft:

- Every acceptance criterion is an **observable outcome** with a stable `AC-N`
  id. Every non-goal has a stable `NG-N` id. Those ids are the contract that
  `mag-build` and `mag-review` enforce, so they must not be renumbered later.
- **No acceptance criterion may require a non-goal.** If one does, you have a
  contradiction — resolve it with the user before filing, not after.
- Size the issue to **one day of agent work or less**. Larger work becomes a
  chain of small issues, ordered so each one is buildable using only the merged
  output of the ones before it. Link that order with `Blocked by #N`.

## 4. Confirm, then file

Show the complete draft in chat and get an explicit go-ahead. Then file it:

```bash
gh issue create --title "<title>" --body-file <path>
```

Report the issue number and URL exactly as `gh` returned them. Later skills use
that number rather than guessing it.

## Hard rule

**Never apply the `agent-ready` label.** The user applies it themselves after a
final read. That label is the entire approval gate between "an idea" and "an
agent writes code for it", and a spec skill that applies its own approval has
removed the only human checkpoint before implementation.
