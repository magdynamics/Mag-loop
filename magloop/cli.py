"""Command line interface for Mag Loop.

Every mutation the loop makes to its own state goes through this CLI rather
than through the agent editing JSON by hand. That keeps the guardrails —
iteration budget, stall detection, verification gating — outside the model's
discretion, which is the whole reason the loop terminates.
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

from magloop.brief import render_brief
from magloop.state import LoopState, StateError, VerifyResult, find_root, state_path

SUMMARY_LINES = 20
SUMMARY_CHARS = 2000


def _resolve_path(args: argparse.Namespace) -> Path:
    root = Path(args.root).resolve() if args.root else find_root()
    return state_path(root)


def _load(args: argparse.Namespace) -> tuple[LoopState, Path]:
    path = _resolve_path(args)
    return LoopState.load(path), path


def _tail(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines() if line.strip()]
    summary = "\n".join(lines[-SUMMARY_LINES:])
    if len(summary) > SUMMARY_CHARS:
        summary = "..." + summary[-SUMMARY_CHARS:]
    return summary


# ---- commands --------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve() if args.root else find_root()
    path = state_path(root)
    if path.exists() and not args.force:
        print(f"loop already initialised at {path} (use --force to overwrite)", file=sys.stderr)
        return 1
    state = LoopState(
        goal=args.goal.strip(),
        verify_command=(args.verify or "").strip(),
        max_iterations=args.max_iterations,
        stall_limit=args.stall_limit,
    )
    for title in args.task or []:
        state.add_task(title)
    state.save(path)
    print(f"initialised loop at {path}")
    print(f"  goal:   {state.goal}")
    print(f"  verify: {state.verify_command or '(none — set one with `magloop init --verify`)'}")
    print(f"  budget: {state.max_iterations} iterations, stall limit {state.stall_limit}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    state, path = _load(args)
    if args.json:
        import json

        print(json.dumps(state.to_dict(), indent=2))
        return 0

    halt = state.halt_reason()
    print(f"goal      {state.goal}")
    print(f"status    {state.status}" + (f" — {state.stop_reason}" if state.stop_reason else ""))
    print(f"iteration {state.iteration}/{state.max_iterations}   stall {state.stall_count}/{state.stall_limit}")
    if state.last_verify is not None:
        mark = "pass" if state.last_verify.ok else f"FAIL (exit {state.last_verify.exit_code})"
        print(f"verify    {mark} — {state.last_verify.command}")
    elif state.verify_command:
        print(f"verify    not yet run — {state.verify_command}")
    if state.tasks:
        print("tasks")
        for task in state.tasks:
            mark = {"todo": "[ ]", "doing": "[~]", "done": "[x]", "dropped": "[-]"}[task.status]
            note = f"  ({task.note})" if task.note else ""
            print(f"  {mark} {task.id}. {task.title}{note}")
    for blocker in state.blockers:
        print(f"blocker   {blocker}")
    print(f"next      {'halt — ' + halt if halt else 'continue'}")
    print(f"state     {path}")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    """Print the iteration brief the agent should act on."""
    state, _ = _load(args)
    print(render_brief(state), end="")
    return 0


def cmd_task(args: argparse.Namespace) -> int:
    state, path = _load(args)
    if args.action == "add":
        for title in args.value:
            task = state.add_task(title)
            print(f"added [{task.id}] {task.title}")
    else:
        status = {"start": "doing", "done": "done", "drop": "dropped"}[args.action]
        for raw_id in args.value:
            try:
                task_id = int(raw_id)
            except ValueError:
                raise StateError(f"task id must be a number, got {raw_id!r}") from None
            task = state.set_task_status(task_id, status, note=args.note or "")
            print(f"[{task.id}] {task.title} -> {task.status}")
    state.save(path)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    state, path = _load(args)
    command = (args.command or state.verify_command).strip()
    if not command:
        print("no verify command configured; pass one or set it with `magloop init --verify`", file=sys.stderr)
        return 2

    print(f"$ {command}", flush=True)
    completed = subprocess.run(
        command,
        shell=True,
        cwd=str(path.parent.parent),
        capture_output=True,
        text=True,
        timeout=args.timeout,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    print(output.rstrip())

    result = VerifyResult(command=command, exit_code=completed.returncode, summary=_tail(output))
    state.record_verify(result)
    state.save(path)
    print(f"\nverify {'PASSED' if result.ok else f'FAILED (exit {result.exit_code})'}")
    return 0 if result.ok else 1


def cmd_record(args: argparse.Namespace) -> int:
    state, path = _load(args)
    entry = state.record_iteration(args.action, decision=args.decision)
    state.save(path)
    halt = state.halt_reason()
    print(f"recorded iteration {entry.iteration}: {entry.action}")
    print(f"next: {'HALT — ' + halt if halt else 'continue'}")
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    state, path = _load(args)
    state.add_blocker(args.reason)
    state.save(path)
    print(f"blocker recorded: {args.reason}")
    return 0


def cmd_unblock(args: argparse.Namespace) -> int:
    state, path = _load(args)
    state.blockers.clear()
    state.save(path)
    print("blockers cleared")
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    state, path = _load(args)
    state.stop(args.status, args.reason)
    state.save(path)
    print(f"loop {state.status}: {state.stop_reason}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    state, _ = _load(args)
    if not state.history:
        print("(no iterations recorded yet)")
        return 0
    for entry in state.history:
        verdict = {True: "pass", False: "fail", None: "----"}[entry.verify_ok]
        print(f"#{entry.iteration:>3}  {entry.at}  {verdict}  {entry.decision:<9} {entry.action}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    path = _resolve_path(args)
    state = LoopState.load(path)
    goal = args.goal.strip() if args.goal else state.goal
    fresh = LoopState(
        goal=goal,
        verify_command=state.verify_command,
        max_iterations=args.max_iterations or state.max_iterations,
        stall_limit=state.stall_limit,
    )
    if args.keep_tasks:
        for task in state.tasks:
            new = fresh.add_task(task.title, task.note)
            new.status = task.status
    fresh.save(path)
    print(f"loop reset — goal: {fresh.goal}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from magloop.runner import run_loop

    root = Path(args.root).resolve() if args.root else find_root()
    return run_loop(
        root=root,
        iterations=args.iterations,
        claude_bin=args.claude_bin,
        extra_args=shlex.split(args.claude_args or ""),
        dry_run=args.dry_run,
        timeout=args.timeout,
    )


# ---- parser ----------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="magloop", description="Resumable, verification-gated agentic loop.")
    parser.add_argument("--root", help="project root (defaults to the nearest .mag-loop/ or git root)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="start a new loop run")
    p.add_argument("--goal", required=True, help="what the loop is trying to achieve")
    p.add_argument("--verify", help="shell command that objectively proves the goal (tests, build, lint)")
    p.add_argument("--max-iterations", type=int, default=12, help="hard iteration budget (default: 12)")
    p.add_argument("--stall-limit", type=int, default=3, help="halt after N iterations with no change (default: 3)")
    p.add_argument("--task", action="append", help="seed task; repeatable")
    p.add_argument("--force", action="store_true", help="overwrite an existing run")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("status", help="show the current run at a glance")
    p.add_argument("--json", action="store_true", help="emit raw state as JSON")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("brief", help="print the next iteration's instructions for the agent")
    p.set_defaults(func=cmd_brief)

    p = sub.add_parser("task", help="manage the task list")
    p.add_argument("action", choices=["add", "start", "done", "drop"])
    p.add_argument("value", nargs="+", help="titles for `add`, task ids otherwise")
    p.add_argument("--note", help="note to attach")
    p.set_defaults(func=cmd_task)

    p = sub.add_parser("verify", help="run the verification command and record the result")
    p.add_argument("command", nargs="?", help="override the configured command")
    p.add_argument("--timeout", type=int, default=1800, help="seconds before giving up (default: 1800)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("record", help="close out an iteration")
    p.add_argument("--action", required=True, help="one line on what this iteration actually did")
    p.add_argument("--decision", default="continue", choices=["continue", "done", "blocked", "stopped"])
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("block", help="record something only a human can resolve")
    p.add_argument("reason")
    p.set_defaults(func=cmd_block)

    p = sub.add_parser("unblock", help="clear recorded blockers")
    p.set_defaults(func=cmd_unblock)

    p = sub.add_parser("stop", help="end the run")
    p.add_argument("--status", default="stopped", choices=["done", "blocked", "stopped"])
    p.add_argument("--reason", default="stopped by hand")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("log", help="show the iteration history")
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("reset", help="clear progress and start the run over")
    p.add_argument("--goal", help="new goal (defaults to the existing one)")
    p.add_argument("--max-iterations", type=int)
    p.add_argument("--keep-tasks", action="store_true")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("run", help="drive the loop headlessly with the Claude Code CLI")
    p.add_argument("--iterations", type=int, help="cap this invocation (still bounded by the run's budget)")
    p.add_argument("--claude-bin", default="claude", help="Claude Code executable (default: claude)")
    p.add_argument("--claude-args", help="extra args passed through, e.g. '--permission-mode acceptEdits'")
    p.add_argument("--timeout", type=int, default=3600, help="per-iteration seconds (default: 3600)")
    p.add_argument("--dry-run", action="store_true", help="print the prompts instead of invoking Claude")
    p.set_defaults(func=cmd_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except StateError as exc:
        print(f"magloop: {exc}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired as exc:
        print(f"magloop: command timed out after {exc.timeout}s", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nmagloop: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
