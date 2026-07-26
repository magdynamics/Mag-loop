---
name: mag-review
description: Review one open pull request against its linked GitHub issue and required CI checks, then post a three-group verdict and set Mag Loop labels. Use when asked to run Mag Loop's reviewer or work its review queue. Designed for /loop; never merges, never pushes code.
---

# Mag Loop reviewer

**One pass = one pull request reviewed.** Under `/loop`, each iteration runs
this skill once.

You produce evidence for a human's merge decision. You never merge, never push,
and never expand scope.

## 1. Find a pull request that needs review

```bash
gh pr list --state open --json number,title,labels,isDraft,headRefOid,updatedAt,url
```

Skip drafts. For each remaining PR, find the most recent comment whose first
line is `Mag Loop review of <sha>`.

Skip the PR when that recorded sha equals its current `headRefOid` **and** it
already carries `loop-approved`, `loop-changes-requested`, `needs-human-review`,
or `loop-stuck` — it has already been reviewed at this exact commit. Review it
again when new commits landed after the recorded sha.

If nothing needs review, say so and end the pass.

## 2. Read the contract, then the code

- Parse `Closes #N` from the PR body and fetch that issue in full, including
  comments. **A PR with no linked issue is a must-fix finding** — there is no
  contract to review it against.
- Read the complete diff, and read every changed file in its surrounding
  context. A diff alone hides whether the change fits the codebase.
- Review **only against the linked issue**: unmet acceptance criteria, defects,
  broken data flow, scope the issue never authorised, security problems,
  missing loading and error states, and code that future agents will find hard
  to modify safely.
- Do not suggest unrelated improvements unless they are severe. Review noise
  trains the builder to skim.

Every must-fix finding begins with one of these tags:

- `[AC-N]` — the PR does not satisfy that acceptance criterion
- `[DEFECT]` — broken implementation, but inside the authorised scope
- `[SECURITY]` — severe enough on its own to block shipping
- `[CI]` — a required GitHub check failed

**Non-goals are binding on you too.** If fixing a finding would require
behavior a non-goal excludes, do not prescribe the code. Record
`[SCOPE-CONFLICT AC-N ↔ NG-N]` with the exact contradiction and escalate to a
human. Only editing the issue can widen scope — never a review comment.

## 3. Check merge evidence

```bash
gh pr view NUMBER --json headRefOid,mergeable,mergeStateStatus
gh pr checks NUMBER --required --json bucket,name,state,link
```

- Required checks still **pending**, or mergeability still unknown: report that
  the PR is waiting, post no verdict, change no labels, and end the pass. A
  later iteration retries it.
- A **failed** required check is a `[CI]` must-fix finding.
- A **merge conflict** is a `[DEFECT]` must-fix finding.
- **No required checks configured at all**: escalate to a human and do not
  apply `loop-approved`. Mag Loop does not treat absent CI as green — that is
  the difference between evidence and assumption.

Gather all evidence against one exact `headRefOid`, and **re-fetch it
immediately before posting**. If the head moved while you were reviewing, throw
the review away and start over on a future pass. A verdict attached to the
wrong commit is worse than no verdict.

## 4. Post exactly one verdict

```md
Mag Loop review of <sha>

CI: required checks passed | failed | not configured
Mergeability: clean | conflicting

## Review

Summary: one or two plain sentences on what this PR does.

## 1. Must fix before merge

None.

## 2. Should fix soon

None.

## 3. Safe to merge

Yes — automated review evidence is complete. A human still makes the merge decision.
```

Then set labels to match the verdict. Check which labels exist before removing
one, so removing an absent label does not fail the command.

| Verdict | Add | Remove |
|---|---|---|
| No must-fix, no escalation | `loop-approved` | `loop-changes-requested` |
| Must-fix findings present | `loop-changes-requested` | `loop-approved` |
| Scope conflict, or no required CI | `needs-human-review` | `loop-approved`, `loop-changes-requested` |

On escalation, set "Safe to merge" to `No — human decision required.`

Preserve a pre-existing `needs-human-review` label even on a clean verdict: it
may represent a separate high-risk gate that a human added deliberately.

Escalation deliberately removes a PR from the automated repair queue. A human
must resolve the cause — amend the issue, configure CI, make the product call —
and remove the label before Mag Loop reviews that unchanged commit again.

## 5. Hard limits

- **Never merge, and never enable auto-merge.**
- **Never push commits** to the PR branch. Reviewing and fixing in one pass
  destroys the independence that makes the review worth anything.
- **Never use a formal GitHub approval or change request.** Post one comment
  and set labels. The loop often runs on the PR author's token, and GitHub
  rejects self-reviews.
- `loop-approved` means: no must-fix finding against the contract, required
  checks green, no conflict at the reviewed commit. It is **evidence for a
  human**, not authorization for anything to merge.
