# Mag Loop

A resumable, verification-gated agentic loop for coding work.

You give it a goal and a command that objectively proves the goal is met. It
then works in small iterations: do one thing, run the proof, record what
happened, decide whether to keep going. It stops on its own — when the goal is
met, when the iteration budget runs out, when progress stalls, or when it hits
something only a human can resolve.

The point of the loop is not that an agent repeats itself. It is that the
repetition is **bounded** and each round is **checked**. Those two properties
live in the `magloop` CLI, outside the model's discretion, which is why a run
terminates instead of drifting.

## Install

No dependencies, Python 3.9+.

```bash
pip install -e .
```

Or skip installing and use `python3 -m magloop.cli` in place of `magloop`.

## Quickstart

```bash
magloop init --goal "make the auth tests pass" \
             --verify "pytest tests/auth -q" \
             --max-iterations 12

magloop task add "reproduce the failure" "fix the token refresh" "add a regression test"
```

Then run iterations. Manually, or from inside a Claude Code session:

```bash
magloop brief                              # what to do now, and why
# ... do the work ...
magloop verify                             # run the proof, record the result
magloop task done 1
magloop record --action "reproduced the 401 on expired tokens"
```

Or unattended, one fresh `claude -p` per iteration:

```bash
magloop run --claude-args "--permission-mode acceptEdits"
magloop run --dry-run    # show the next prompt without invoking anything
```

Check in any time with `magloop status` and `magloop log`. A run survives
interruption — the state is on disk, so `magloop run` picks up where it left
off.

## Using it inside Claude Code

`.claude/skills/mag-loop/SKILL.md` makes the loop available as `/mag-loop` in
any Claude Code session in this repository. It teaches the agent the protocol —
one task per iteration, verify before claiming done, record every iteration —
and tells it to stop when the brief says HALT.

To use the loop in another project, copy the `mag-loop` skill directory into
that repository's `.claude/skills/`, or into `~/.claude/skills/` for all
projects, and make sure `magloop` is on PATH.

## Commands

| Command | What it does |
|---|---|
| `magloop init --goal G --verify CMD` | Start a run |
| `magloop brief` | Print the current iteration's instructions and context |
| `magloop status` | Where the run stands (`--json` for machine-readable) |
| `magloop task add\|start\|done\|drop` | Manage the task list |
| `magloop verify [CMD]` | Run the proof command and record the result |
| `magloop record --action "..."` | Close out an iteration |
| `magloop block "..."` / `unblock` | Flag work needing a human |
| `magloop stop --status done` | End the run by hand |
| `magloop log` | Iteration history |
| `magloop reset` | Clear progress, keep the configuration |
| `magloop run` | Drive iterations headlessly via the Claude Code CLI |

## Guardrails

| Guardrail | Default | Catches |
|---|---|---|
| Iteration budget | 12 | Goals too big or too vague to converge |
| Stall limit | 3 | Iterations that churn without moving anything |
| Blockers | — | Work that cannot proceed without a human |
| Verification gate | — | "Done" that was never actually checked |

Stall detection fingerprints the task list plus the last verification result. If
consecutive iterations leave both identical, nothing moved, and after
`--stall-limit` of those the loop halts rather than burning the remaining
budget.

The headless runner enforces the budget independently: if an iteration ends
without the agent recording it, the runner records it anyway. Forward progress
of the counter never depends on the model cooperating.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Design

See [docs/DESIGN.md](docs/DESIGN.md) for why the loop is shaped this way —
what makes a coding loop different from a chat loop, and what each guardrail
is defending against.
