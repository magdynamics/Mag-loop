---
name: mag-build
description: Claim the next safe agent-ready GitHub issue, implement only its contract, and open a pull request. Also repairs Mag-loop review feedback on existing PRs. Use when asked to run Mag-loop's builder or work the approved queue. Designed for /loop; one pass does exactly one unit of work.
---

# Mag-loop builder

**One pass = one unit of work.** Either repair review feedback on one existing
pull request, or build one issue end to end. Under `/loop`, each iteration runs
this skill exactly once, so finishing a unit and ending the pass is correct
behavior — not stopping early.

Never merge, and never enable auto-merge. Humans merge.

## 0. Preflight

Before touching issues, branches, or files:

- Confirm you are in the intended repository and `origin` is reachable
  (`gh repo view`).
- Detect the default branch; never assume it is `main`:
  ```bash
  gh repo view --json defaultBranchRef --jq .defaultBranchRef.name
  ```
- Require a clean working tree. `git status --porcelain` must be empty. If it
  is dirty, report the paths and end the pass. **Never stash, reset, check out
  over, or commit work you did not create** — it may be the user's in-progress
  edits.

## 1. Repair review feedback first

Draining the repair queue before starting new work keeps the number of open,
half-finished pull requests bounded.

```bash
gh pr list --state open --label loop-changes-requested \
  --json number,title,headRefName,headRefOid,labels,updatedAt,url
```

Skip any PR labeled `needs-human-review` or `loop-stuck`. Both have
deliberately left the automated queue and are waiting on a person.

If a PR remains, take the **least recently updated** one and:

1. Read its linked issue and the most recent `Mag-loop review of <sha>` comment.
2. Count existing `Mag-loop fix round N` comments on the PR. **If two rounds
   have already happened**, add `loop-stuck`, remove `loop-changes-requested`,
   comment explaining that two repair rounds did not converge, and end the pass.
   An agent must not argue with a reviewer indefinitely.
3. Otherwise check out the branch and fix **only** the items under "Must fix
   before merge". Do not opportunistically improve anything else.
4. Run the relevant checks, push, remove `loop-changes-requested`, and comment
   `Mag-loop fix round N` followed by what changed.

End the pass.

If a requested fix would cross a non-goal or needs a product decision, **do not
implement it.** Comment the exact conflict, add `needs-human-review`, remove
`loop-changes-requested`, and end the pass. This stops the next iteration from
retrying a decision only a human can make.

## 2. Pick

### First, release abandoned work

An issue carries `agent-building` while a pass builds it. If that pass crashed,
or its pull request was closed without merging, the issue stays claimed
forever — and because the pick query below only returns unassigned issues, no
later pass will ever see it again. Sweep for that before picking:

```bash
gh issue list --state open --label agent-building --json number,title,assignees,url
gh pr list --state open --json number,body,url
```

Release an `agent-building` issue only when **both** are true: its number
appears in no open pull request body as `Closes #N`, and it is assigned to you
or to nobody. Never strip a label or an assignee off work a person has taken —
a human who picked up a stalled issue by hand looks exactly like an orphan from
the outside, and the difference is the assignee:

```bash
gh issue edit N --remove-label agent-building --remove-assignee @me
```

### Then pick

Put every filter in the query itself. A filter that lives only in prose is one
the next pass can forget, and the one that matters here keeps the builder off
work a human has gated:

```bash
gh issue list --state open \
  --search "label:agent-ready -label:blocked no:assignee sort:created-asc" \
  --json number,title,labels,createdAt,url
```

Confirm from the returned labels that each candidate really is `agent-ready`
and really is not `blocked`. Then read each candidate's body for a
`Blocked by #N` section and check every issue it names:

```bash
gh issue view N --json state,title
```

Skip the candidate unless all of its blockers are closed. Among what remains,
prefer higher priority labels if the repo uses them, then oldest first.

If nothing qualifies, say so and end the pass. **Do not invent work**, and do
not pick a blocked issue because the queue looks empty.

## 3. Claim

Claim before reading deeply or writing any code:

```bash
gh issue edit N --add-assignee @me --add-label agent-building
```

Re-fetch the issue immediately afterwards. If it is now assigned to someone
else, labeled `blocked`, or no longer `agent-ready`, release your own claim
before returning to step 2 — dropping it silently leaves the issue assigned to
you and labeled `agent-building` while somebody else works on it:

```bash
gh issue edit N --remove-label agent-building --remove-assignee @me
```

The assignee is a **cooperative lock between people**, not an atomic one. Two
sessions authenticated as the same account cannot reliably lock each other, so
run only one builder loop per repository.

## 4. Read the contract

Fetch the issue in full, including comments:

```bash
gh issue view N --json title,body,labels,comments,url
```

Implement its acceptance criteria and nothing else. **Non-goals are binding.**
Compare every `AC-N` against every `NG-N` before you start editing.

If an acceptance criterion is ambiguous, contradicts a non-goal, or depends on
something unresolved, go to step 8. **Never guess** — a wrong guess costs a
whole review cycle and erodes trust in the queue.

## 5. Build

- Fetch the latest default branch from `origin`, then create or resume a branch
  named `mag/<issue-number>-<short-slug>`.
- Implement the acceptance criteria in the repository's existing style,
  architecture, and naming conventions. Read neighbouring code first.
- Add or update tests whenever the change touches logic, data flow,
  permissions, integrations, or user-visible behavior.
- Preserve every behavior outside the issue contract.
- No unrelated changes and no opportunistic refactors, however tempting. They
  make the diff unreviewable and they are how non-goals get violated by
  accident.

## 6. Verify

Run the repository's relevant lint, typecheck, build, and the narrowest useful
tests. Everything attributable to this change must pass before you open a pull
request.

If a broad check has a **pre-existing** failure unrelated to your change, run a
targeted check instead, keep the evidence, and disclose both results in the PR
body. Do not silently accept a red check, and do not "fix" unrelated failures
inside this PR.

Read `git diff` and `git status` before shipping. Stop if the diff contains
unrelated work, generated artifacts, or anything resembling a credential.

## 7. Ship

Push and open the pull request. The body must contain:

- What changed, and why
- `Closes #N` with the real issue number, so the merge closes the issue
- A **scope ledger**: one evidence line per `AC-N`, one preservation line per
  `NG-N`, and a final `Other behavior changes: None`
- Numbered manual verification steps matching what you actually built
- The automated checks you ran and their results
- `Risk: Low` / `Medium` / `High`

If `Other behavior changes: None` is not truthful, **stop.** Get the issue
amended to cover the extra behavior before opening the PR. The alternative is
scope expanding through a PR description, which defeats the whole contract.

Then remove `agent-building` from the issue and end the pass. Never merge and
never enable auto-merge.

## 8. Blocked

Comment **one specific question a human can answer asynchronously**, then
release the issue completely:

```bash
gh issue edit N --add-label blocked --remove-label agent-building --remove-assignee @me
```

Removing `agent-building` matters as much as unassigning. That label is the
claim that an agent is working on this right now; leaving it behind makes a
blocked issue indistinguishable from live work, both to you and to anything
you later build on top of these labels.

Leave `agent-ready` in place. The pick query excludes `blocked`, so the issue
reappears in the queue only after a human answers and removes that label.

Never write "this is unclear". State the exact decision to be made, the options
you see, your recommendation, and which acceptance criterion it affects. Then
end the pass so the next iteration can pick up different work.
