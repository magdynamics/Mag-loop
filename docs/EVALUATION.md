# Evaluating Mag-loop as a coding tool

Mag-loop has never run against a real repository. This is how we find out
whether it works, in an order that puts the cheapest failures first.

Three questions, and you cannot answer a later one before an earlier one:

1. **Does the machinery work?** Do the `gh` calls, labels, and branches behave?
2. **Does it produce code you would merge?** Contract satisfaction and scope.
3. **Is it worth the overhead?** Human minutes per merged pull request.

Most of what goes wrong is question 1 in the first hour and question 2 forever
after. Question 3 only becomes answerable around ten merged PRs.

---

## Phase 1 — one pass, watched

Run `/mag-build` **bare, not under `/loop`**, on one deliberately small issue.
Watch the whole pass. Record pass or fail for each line — every one is a
directly observable outcome, not a judgement:

| # | Observable | Pass means |
|---|---|---|
| 1 | Preflight | Reports the repo's real default branch, not `main` by assumption |
| 2 | Dirty tree | With an uncommitted change present, it reports the paths and stops |
| 3 | Pick | Returns the issue you labeled, and no others |
| 4 | Blocked exclusion | An issue labeled `blocked` is not picked, even when the queue is otherwise empty |
| 5 | Claim | Assignee and `agent-building` both appear on the issue |
| 6 | Branch | Named `mag/<issue-number>-<slug>` |
| 7 | Scope ledger | PR body has `Closes #N`, one evidence line per `AC-N`, one preservation line per `NG-N`, and `Other behavior changes: None` |
| 8 | Release | `agent-building` is gone from the issue once the PR is open |
| 9 | Reviewer scope | It reviews the `mag/*` PR and ignores every other open PR |
| 10 | Verdict | One comment, `Mag-loop review of <sha>` matching the actual head commit |
| 11 | Labels | Exactly one of `loop-approved` / `loop-changes-requested` / `needs-human-review` |

Any failure here is a bug in Mag-loop. Fix it before Phase 2 — a broken
mechanism makes every later measurement meaningless.

Two lines deserve extra attention because they are the newest, least exercised
logic:

- **The reclaim sweep.** Assign an `agent-building` issue to yourself by hand and
  confirm the next pass leaves it alone. It must never strip a human's claim.
- **Empty queue.** In a repo with no `agent-ready` issues, the pass must report
  an empty queue and end. It must not invent work.

## Phase 2 — five issues

Now measure output quality. Per issue, record:

- **Spec rounds** — how many question rounds `/mag-spec` needed
- **First-pass AC satisfaction** — did the PR meet every `AC-N` without a repair round?
- **Review rounds to green** — 0, 1, 2, or escalated to `loop-stuck`
- **Non-goal violations** — did the diff touch anything an `NG-N` excluded?
- **Issue edits mid-flight** — did you have to amend the contract after building started?

The number that matters is **first-pass AC satisfaction rate.** Below roughly
60%, the problem is almost always vague acceptance criteria rather than a weak
builder — the fix is in how you write specs, not in the skill. Diagnose it that
way round before changing anything.

## Phase 3 — ten issues

Only now compare cost. Count **human minutes per merged PR**, including the spec
interview, reading the filed issue, reading the verdict, and merging. Compare
against your honest baseline for work of the same size.

Expect Mag-loop to lose on small changes and win on volume. If it loses on
everything, the issues are probably too small for the ceremony — try larger
single-day contracts before concluding it does not work.

---

## Failure signals — stop and fix rather than pushing on

| Signal | What it actually means |
|---|---|
| The same `AC-N` missed across different issues | Spec template problem, not a builder problem |
| `loop-stuck` more than once in ten PRs | Builder and reviewer disagree systematically; read both and find which is wrong |
| Any non-goal violated | Non-goals are not being treated as binding — tighten `mag-build` §4 |
| Reclaim sweep touches a human-assigned issue | Real bug in the newest code; stop the loop |
| A PR you never asked for | Pick query problem, or someone applied `agent-ready` too freely |
| Every PR escalates to `needs-human-review` | No required status check configured; this is expected, not a defect |

## The decision

- **Adopt** if first-pass AC satisfaction is above ~70% and no non-goal has been
  violated. Then widen to a second repository.
- **Adjust** if satisfaction is 40–70%. Almost always a spec-writing fix; keep
  the skills and change how you answer the interview.
- **Abandon or rebuild** if non-goals are violated, or if the loop opens work
  nobody approved. Those are contract failures, and the contract is the entire
  value.

Record the results somewhere durable — a GitHub issue on this repo is enough.
The point of the phases is that you can stop early with a clear answer rather
than forming a vague impression over weeks.
