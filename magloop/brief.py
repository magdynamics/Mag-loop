"""Rendering of the per-iteration brief handed to the agent.

This is the only thing the agent reads at the start of an iteration, so it has
to carry the entire working context: the goal, what is still open, whether the
last verification passed, what the previous iterations already tried, and
whether a guardrail says to stop.
"""

from __future__ import annotations

from magloop.state import LoopState

PROTOCOL = """**Do exactly one thing.** Take the single smallest open task that moves the goal
forward, implement it, then prove it:

1. `magloop task start <id>` — claim the task.
2. Make the change.
3. `magloop verify` — run the project's verification command and record the result.
4. `magloop task done <id>` if it holds up, or add follow-up tasks with
   `magloop task add "..."` if you learned the work is bigger than it looked.
5. `magloop record --action "<one line on what you actually did>"` — this closes
   the iteration and advances the guardrails.

Use `--decision blocked` on `record` if you cannot proceed without a human, and
`--decision done` only when the goal is genuinely met and verification is green.
Do not skip step 5: an iteration that is not recorded does not count as progress."""

_TASK_MARKS = {"todo": "[ ]", "doing": "[~]", "done": "[x]", "dropped": "[-]"}


def render_brief(state: LoopState) -> str:
    halt = state.halt_reason()
    lines: list[str] = [
        f"# Mag Loop — iteration {state.iteration + 1} of {state.max_iterations}",
        "",
        f"**Goal:** {state.goal}",
        "",
    ]

    if halt:
        lines += [
            f"**HALT. Do not start another iteration.** Reason: {halt}",
            "",
            "Summarise what was accomplished, what remains, and stop.",
            "",
        ]

    open_tasks = state.open_tasks
    if open_tasks:
        lines.append("## Open tasks")
        for task in open_tasks:
            note = f" — {task.note}" if task.note else ""
            lines.append(f"- {_TASK_MARKS[task.status]} [{task.id}] {task.title}{note}")
    elif state.tasks:
        lines.append("## Open tasks\n\nNone — every task is closed.")
    else:
        lines.append(
            "## Open tasks\n\nNone yet. Start by breaking the goal into small, "
            'verifiable steps with `magloop task add "..."`.'
        )
    lines.append("")

    if state.last_verify is not None:
        verdict = "PASSED" if state.last_verify.ok else f"FAILED (exit {state.last_verify.exit_code})"
        lines += [
            f"## Last verification — {verdict}",
            "",
            f"`{state.last_verify.command}`",
            "",
            "```",
            state.last_verify.summary or "(no output captured)",
            "```",
            "",
        ]
    elif state.verify_command:
        lines += [
            "## Verification",
            "",
            f"Not run yet: `{state.verify_command}`",
            "",
        ]

    if state.blockers:
        lines.append("## Blockers")
        lines += [f"- {b}" for b in state.blockers]
        lines.append("")

    if state.history:
        lines.append("## Recent iterations")
        for entry in state.history[-5:]:
            verdict = {True: "verify pass", False: "verify fail", None: "no verify"}[entry.verify_ok]
            lines.append(f"- #{entry.iteration} ({verdict}, {entry.decision}): {entry.action}")
        lines.append("")

    if not halt:
        lines += ["## Protocol", "", PROTOCOL]

    return "\n".join(lines).rstrip() + "\n"
