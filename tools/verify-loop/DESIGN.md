# Mag Loop — design notes

## The problem with chat-style loops

A loop built for a chat assistant usually looks like: re-prompt the model with
"continue" until it says it is finished. That works well enough for writing,
where the output is the artifact and a human reads every round. It fails for
coding for three reasons:

1. **Self-reported success.** The model decides when it is done. In a codebase,
   "done" is checkable — the tests pass or they do not — and a loop that does
   not check is a loop that confidently finishes broken work.
2. **Context is the state.** When the conversation is the only memory, a
   compaction, a crash, or a new session loses the loop's place. Long coding
   tasks routinely outlive a single context window.
3. **No termination guarantee.** "Until the model says stop" is not a stopping
   condition. A confused model will keep going, and each round costs real money
   and real edits to real files.

Mag Loop is built around fixing exactly those three.

## Three properties

### 1. Every iteration is gated on an objective check

`--verify` takes a shell command — tests, a build, a linter, a type check. The
loop runs it, records the exit code and the tail of its output, and carries
that forward. An iteration cannot claim success on its own say-so, and the
next iteration starts by reading the actual failure text rather than the
previous iteration's summary of it.

This is why `magloop init` pushes hard for a verify command, and why a run
without one should be raised with the user before it starts. A loop with no
gate will spend its whole budget on plausible-looking work.

### 2. State lives on disk, not in context

Everything an iteration needs is in `.mag-loop/state.json`: the goal, the task
list with statuses, the last verification result, the iteration history, the
blockers, the guardrail counters. `magloop brief` renders it into the one
document an iteration reads.

The consequences are the useful part:

- The headless runner starts a **fresh** `claude -p` per iteration. There is no
  accumulated conversation to derail, and no context growth across a long run.
- A run survives interruption. Kill it, come back tomorrow, `magloop run` again.
- A human can inspect or correct a run mid-flight with ordinary CLI commands.
- Iteration N sees a compact, curated view rather than the transcript of
  iterations 1 through N-1.

Writes are atomic (temp file plus `os.replace`), so an interrupted run never
leaves a half-written state file.

### 3. Termination is enforced outside the model

Four independent halt conditions, checked by `LoopState.halt_reason()` before
every iteration:

| Condition | Defends against |
|---|---|
| `iteration >= max_iterations` | A goal too big or too vague to converge |
| `stall_count >= stall_limit` | Churning without moving anything |
| Any blocker recorded | Work that genuinely needs a human |
| All tasks closed **and** verification green | Actually finished |

Note the conjunction in the last row. Closing every task while the build is red
does **not** end the run — that is the most common way an agent declares
premature victory, and the gate catches it.

**Stall detection** fingerprints the task list (ids, statuses, titles) plus the
last verification result. If two consecutive iterations leave that fingerprint
identical, the second one changed nothing observable. Three of those and the
loop halts. This catches the characteristic failure where an agent rewrites the
same file repeatedly against a test it does not understand.

**The counter always advances.** The runner compares the iteration count before
and after invoking Claude; if the agent finished without recording, the runner
records on its behalf with a note. The budget therefore binds whether or not
the model follows the protocol — a guardrail that depends on the agent's
cooperation is not a guardrail.

## Why the CLI is the only way to mutate state

The agent could edit `state.json` directly. It must not.
Every guardrail — budget, stall detection, the closed-tasks-plus-green-verify
conjunction, the refusal to record onto a finished run — is implemented in the
CLI. Hand-editing the file routes around all of them. Keeping mutation behind
`magloop <verb>` is what makes the guarantees hold rather than being
suggestions in a prompt.

## Loop anatomy

```
magloop brief   ─→  goal, open tasks, last verify + output, recent history,
                    and either the protocol or a HALT instruction
      │
      ▼
   agent does exactly one task
      │
      ▼
magloop verify  ─→  runs the proof, records exit code + output tail
      │
      ▼
magloop task done <id>   (or task add for follow-ups discovered on the way)
      │
      ▼
magloop record  ─→  iteration++, stall fingerprint updated, history appended,
                    halt conditions re-evaluated
      │
      └──→ back to brief, until it says HALT
```

## Deliberate non-goals

- **No parallel iterations.** Two agents editing one working tree race on both
  the files and the state. If you want parallelism, run separate loops in
  separate worktrees.
- **No automatic commits.** The loop changes files; what to commit and when is
  the user's call. Compose it with git yourself.
- **No model-specific coupling.** The CLI knows nothing about Claude. Only
  `runner.py` shells out to `claude`, and `--claude-bin` swaps that for anything
  that accepts a prompt argument.
- **No retry-the-same-thing.** The loop does not re-run a failed iteration
  identically; stall detection exists precisely to stop that pattern.

## Tuning

- **Budget.** 12 is a reasonable default for a focused goal. If a run keeps
  exhausting it, the goal is too big — split it into several runs rather than
  raising the ceiling.
- **Stall limit.** 3 is forgiving enough for a genuinely hard debugging step
  that takes an iteration or two of pure investigation. Drop it to 2 for
  well-understood work.
- **Verify command.** Fast and specific beats slow and broad. `pytest
  tests/auth -q` gives a tighter loop than the full suite; widen it for the
  final iterations.
