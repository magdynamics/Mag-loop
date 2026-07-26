"""Headless driver: run the loop by invoking the Claude Code CLI per iteration.

Each cycle starts a fresh `claude -p` process. That is deliberate — the durable
context is `.mag-loop/state.json`, not a long-lived conversation, so an
iteration cannot be derailed by whatever accumulated in the previous one, and a
run can be interrupted and resumed without losing its place.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Sequence

from magloop.brief import render_brief
from magloop.state import LoopState, state_path

PREAMBLE = """You are one iteration of a Mag Loop run in this repository.

Read the brief below and carry out exactly one iteration of the protocol it
describes. Use the `magloop` CLI for all loop bookkeeping — do not edit
`.mag-loop/state.json` by hand. Stop as soon as the iteration is recorded.

---

"""


def _bar(text: str) -> str:
    return f"\n{'=' * 72}\n{text}\n{'=' * 72}"


def run_loop(
    root: Path,
    iterations: int | None = None,
    claude_bin: str = "claude",
    extra_args: Sequence[str] = (),
    dry_run: bool = False,
    timeout: int = 3600,
) -> int:
    path = state_path(root)
    state = LoopState.load(path)

    if dry_run:
        halt = state.halt_reason()
        if halt:
            print(f"loop would halt immediately: {halt}")
            return 0
        print(PREAMBLE + render_brief(state))
        return 0

    completed = 0
    while True:
        # Reload every cycle: the agent mutates state through the CLI, out of process.
        state = LoopState.load(path)

        halt = state.halt_reason()
        if halt:
            print(_bar(f"loop halted after {completed} iteration(s): {halt}"))
            break
        if iterations is not None and completed >= iterations:
            print(_bar(f"reached this invocation's cap of {iterations} iteration(s); run again to continue"))
            break

        print(_bar(f"iteration {state.iteration + 1}/{state.max_iterations} — {state.goal}"))
        prompt = PREAMBLE + render_brief(state)
        command = [claude_bin, "-p", prompt, *extra_args]

        try:
            result = subprocess.run(command, cwd=str(root), timeout=timeout)
        except FileNotFoundError:
            print(
                f"magloop: cannot find {claude_bin!r} on PATH. Install the Claude Code CLI "
                f"or pass --claude-bin /path/to/claude.",
                file=sys.stderr,
            )
            return 2
        except subprocess.TimeoutExpired:
            print(f"magloop: iteration timed out after {timeout}s", file=sys.stderr)
            after = LoopState.load(path)
            after.stop("blocked", f"iteration {after.iteration + 1} timed out after {timeout}s")
            after.save(path)
            return 1

        completed += 1
        after = LoopState.load(path)

        # The guardrails only bite if the counter moves, so never trust the agent
        # to have recorded its own iteration.
        if after.iteration == state.iteration and after.status == "running":
            note = "agent did not record this iteration"
            if result.returncode != 0:
                note = f"{note}; claude exited {result.returncode}"
            after.record_iteration(f"({note})")
            after.save(path)
            print(f"magloop: {note} — recorded on its behalf", file=sys.stderr)

    final = LoopState.load(path)
    print(
        f"\nrun {final.status}"
        + (f" — {final.stop_reason}" if final.stop_reason else "")
        + f"\niterations {final.iteration}/{final.max_iterations}"
        + f"\nopen tasks {len(final.open_tasks)}/{len(final.tasks)}"
    )
    return 0 if final.status in ("done", "running") else 1
