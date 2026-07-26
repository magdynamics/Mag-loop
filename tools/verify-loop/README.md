# verify-loop (`magloop`)

**Not part of Mag-loop.** Mag-loop proper is the three prompt-only skills in
[`skills/`](../../skills) driven by Claude Code's `/loop`, with GitHub as the
durable state. This directory holds a separate, standalone Python loop engine
built before that architecture was settled. It works and it is tested; delete
this directory if you do not want it.

## What it does

Drives a *single* goal to green against a verification command, in bounded
iterations, with its own on-disk state in `.mag-loop/state.json`. Where Mag
Loop's queue is GitHub issues and its unit of work is a pull request,
`magloop`'s queue is a task list inside one run and its unit of work is one
task.

```bash
pip install -e .

magloop init --goal "make the auth tests pass" --verify "pytest tests/auth -q"
magloop task add "reproduce the failure" "fix token refresh" "add a regression test"

magloop brief      # what to do now, with the last failure output
magloop verify     # run the proof, record the result
magloop record --action "reproduced the 401 on expired tokens"
```

Or unattended, one fresh `claude -p` per iteration:

```bash
magloop run --claude-args "--permission-mode acceptEdits"
magloop run --dry-run
```

## Where it might still be useful

Inside a single `mag-build` pass, when one issue turns out to need several
rounds of fix-and-recheck against a slow test suite, and you want that inner
grind bounded and resumable rather than left to the agent's judgement. It is
strictly optional — `mag-build` does not reference it.

## Guardrails

Iteration budget (12), stall detection (3 identical rounds), blockers, and a
verification gate that refuses to call a run finished while the proof command
is red. The runner advances the iteration counter itself when an agent finishes
without recording, so the budget binds regardless of model cooperation.

## Tests

```bash
python3 -m unittest discover -s tests
```

See [DESIGN.md](DESIGN.md) for why it is shaped this way.
