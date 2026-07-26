---
name: mag-loop
description: Run a goal to completion as a verification-gated iterative loop. Use when the user asks to "loop on" a goal, run Mag Loop, keep iterating until tests pass, or grind a multi-step coding task to done. Not for one-off edits or questions.
---

# Mag Loop

An iterative loop that drives one coding goal to completion. Each iteration does
exactly one small thing, proves it with a real command, and records the outcome
on disk. The loop stops on its own — when the goal is met, when the iteration
budget runs out, when progress stalls, or when it hits something only a human
can resolve.

The durable state lives in `.mag-loop/state.json`, managed entirely through the
`magloop` CLI. Never edit that file by hand: the guardrails that make the loop
terminate live in the CLI, and hand-editing routes around them.

## Starting a run

If `.mag-loop/state.json` does not exist yet, create it. The verification
command is the important argument — it is what makes an iteration's claim of
success checkable rather than self-reported. Look at the repo and pick the real
one (`npm test`, `pytest -q`, `cargo test`, `make check`, a build, a linter).

```bash
magloop init --goal "<the user's goal, in one sentence>" \
             --verify "<command that proves it>" \
             --max-iterations 12
```

Then break the goal into small, individually verifiable steps:

```bash
magloop task add "first step" "second step" "third step"
```

Keep steps small enough that one is a single iteration's work. If you cannot
name a verification command, say so to the user before starting — a loop with
no objective gate will happily run its whole budget on work that does not
compile.

## Running an iteration

```bash
magloop brief
```

That prints everything you need: the goal, open tasks, the last verification
result and its output, what previous iterations already tried, and whether a
guardrail says to stop. Act on it, and nothing else.

1. `magloop task start <id>` — claim one task.
2. Do the work.
3. `magloop verify` — run and record the verification command.
4. `magloop task done <id>`, or `magloop task add "..."` for follow-ups you
   discovered. `magloop task drop <id>` if it turned out to be unnecessary.
5. `magloop record --action "<one line on what you actually did>"`

Step 5 is mandatory. It advances the iteration counter, updates stall
detection, and is what makes the loop finite. An iteration you do not record
does not count, and the runner will record it against you with a note.

Then run `magloop brief` again for the next iteration, and repeat until it
tells you to halt.

## Ending a run

- Goal met and verification green → `magloop record --action "..." --decision done`
- Needs a human decision (credentials, a product call, an ambiguous
  requirement) → `magloop block "<what you need>"` then
  `magloop record --action "..." --decision blocked`
- Guardrail halt → `magloop brief` says HALT. Stop immediately and report.

When the loop ends, tell the user in plain prose: what the goal was, what got
done, what verification says right now, and what is left. `magloop log` and
`magloop status` have the details.

## Guardrails, and why they exist

| Guardrail | Default | What it catches |
|---|---|---|
| `--max-iterations` | 12 | A goal that is too big or too vague to converge |
| `--stall-limit` | 3 | Iterations that churn without changing tasks or verification |
| Blockers | — | Work that cannot proceed without a human |
| Verification gate | — | "Done" that was never actually checked |

Stall detection fingerprints the task list plus the last verification result.
If two iterations in a row leave both identical, nothing moved — three of those
and the loop halts rather than burning the rest of its budget.

## Running it unattended

`magloop run` drives the whole thing headlessly, starting a fresh `claude -p`
per iteration:

```bash
magloop run --claude-args "--permission-mode acceptEdits"
magloop run --dry-run   # print the next prompt without invoking anything
```

Prefer this for long grinds. Prefer the manual commands above when you are
already in a session with the user.
