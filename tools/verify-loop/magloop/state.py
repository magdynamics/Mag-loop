"""Persistent state for a Mag Loop run.

The loop has to outlive the agent driving it: context gets compacted, sessions
restart, a run gets picked up again hours later. So everything an iteration
needs in order to decide what to do next lives in `.mag-loop/state.json` on
disk, never in the conversation.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

STATE_DIRNAME = ".mag-loop"
STATE_FILENAME = "state.json"

TASK_STATUSES = ("todo", "doing", "done", "dropped")
OPEN_TASK_STATUSES = ("todo", "doing")
RUN_STATUSES = ("running", "done", "blocked", "stopped")
DECISIONS = ("continue", "done", "blocked", "stopped")


class StateError(RuntimeError):
    """Raised for any misuse the caller can correct: no run, bad status, bad id."""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Task:
    id: int
    title: str
    status: str = "todo"
    note: str = ""

    @property
    def is_open(self) -> bool:
        return self.status in OPEN_TASK_STATUSES

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "status": self.status, "note": self.note}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Task":
        return cls(
            id=int(raw["id"]),
            title=str(raw["title"]),
            status=str(raw.get("status", "todo")),
            note=str(raw.get("note", "")),
        )


@dataclass
class VerifyResult:
    command: str
    exit_code: int
    summary: str
    at: str = field(default_factory=utcnow)

    @property
    def ok(self) -> bool:
        return self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "ok": self.ok,
            "summary": self.summary,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "VerifyResult":
        return cls(
            command=str(raw.get("command", "")),
            exit_code=int(raw["exit_code"]),
            summary=str(raw.get("summary", "")),
            at=str(raw.get("at", utcnow())),
        )


@dataclass
class HistoryEntry:
    iteration: int
    action: str
    decision: str
    verify_ok: bool | None = None
    at: str = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration": self.iteration,
            "action": self.action,
            "decision": self.decision,
            "verify_ok": self.verify_ok,
            "at": self.at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "HistoryEntry":
        return cls(
            iteration=int(raw["iteration"]),
            action=str(raw.get("action", "")),
            decision=str(raw.get("decision", "continue")),
            verify_ok=raw.get("verify_ok"),
            at=str(raw.get("at", utcnow())),
        )


@dataclass
class LoopState:
    goal: str
    verify_command: str = ""
    max_iterations: int = 12
    stall_limit: int = 3
    status: str = "running"
    iteration: int = 0
    stall_count: int = 0
    last_signature: str = ""
    stop_reason: str = ""
    tasks: list[Task] = field(default_factory=list)
    history: list[HistoryEntry] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    last_verify: VerifyResult | None = None
    created_at: str = field(default_factory=utcnow)
    updated_at: str = field(default_factory=utcnow)
    version: int = SCHEMA_VERSION

    # ---- tasks -------------------------------------------------------------

    @property
    def open_tasks(self) -> list[Task]:
        return [t for t in self.tasks if t.is_open]

    def add_task(self, title: str, note: str = "") -> Task:
        title = title.strip()
        if not title:
            raise StateError("task title cannot be empty")
        task = Task(id=self._next_task_id(), title=title, note=note.strip())
        self.tasks.append(task)
        return task

    def get_task(self, task_id: int) -> Task:
        for task in self.tasks:
            if task.id == task_id:
                return task
        raise StateError(f"no task with id {task_id}")

    def set_task_status(self, task_id: int, status: str, note: str = "") -> Task:
        if status not in TASK_STATUSES:
            raise StateError(f"unknown task status {status!r}; expected one of {', '.join(TASK_STATUSES)}")
        task = self.get_task(task_id)
        task.status = status
        if note:
            task.note = note.strip()
        return task

    def _next_task_id(self) -> int:
        return max((t.id for t in self.tasks), default=0) + 1

    # ---- progress ----------------------------------------------------------

    def record_verify(self, result: VerifyResult) -> None:
        self.last_verify = result

    def signature(self) -> str:
        """Fingerprint of everything an iteration is supposed to move.

        Two consecutive iterations with the same fingerprint mean the loop
        spun without changing the world, which is what `stall_limit` catches.
        """
        parts = [f"{t.id}:{t.status}:{t.title}" for t in sorted(self.tasks, key=lambda t: t.id)]
        if self.last_verify is not None:
            parts.append(f"verify:{self.last_verify.exit_code}:{self.last_verify.summary}")
        digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
        return digest[:16]

    def record_iteration(self, action: str, decision: str = "continue") -> HistoryEntry:
        """Close out an iteration: bump the counter, log it, update stall tracking."""
        if decision not in DECISIONS:
            raise StateError(f"unknown decision {decision!r}; expected one of {', '.join(DECISIONS)}")
        if self.status != "running":
            raise StateError(f"run is {self.status}, not running; use `magloop reset` to start over")

        self.iteration += 1
        signature = self.signature()
        # An unchanged signature means this iteration moved nothing.
        self.stall_count = self.stall_count + 1 if signature == self.last_signature else 0
        self.last_signature = signature

        entry = HistoryEntry(
            iteration=self.iteration,
            action=action.strip(),
            decision=decision,
            verify_ok=None if self.last_verify is None else self.last_verify.ok,
        )
        self.history.append(entry)

        if decision != "continue":
            self.status = decision if decision in RUN_STATUSES else "stopped"
            self.stop_reason = f"agent decided: {decision}"
        return entry

    def add_blocker(self, text: str) -> None:
        text = text.strip()
        if text and text not in self.blockers:
            self.blockers.append(text)

    def stop(self, status: str, reason: str) -> None:
        if status not in RUN_STATUSES:
            raise StateError(f"unknown run status {status!r}; expected one of {', '.join(RUN_STATUSES)}")
        self.status = status
        self.stop_reason = reason.strip()

    # ---- guardrails --------------------------------------------------------

    def halt_reason(self) -> str | None:
        """Why the loop must not run another iteration, or None to keep going."""
        if self.status != "running":
            return self.stop_reason or f"run is {self.status}"
        if self.iteration >= self.max_iterations:
            return f"iteration budget exhausted ({self.iteration}/{self.max_iterations})"
        if self.stall_count >= self.stall_limit:
            return f"no progress for {self.stall_count} consecutive iterations"
        if self.blockers:
            return f"blocked: {self.blockers[-1]}"
        if self.tasks and not self.open_tasks:
            if self.verify_command and (self.last_verify is None or not self.last_verify.ok):
                return None
            return "all tasks closed and verification is green"
        return None

    @property
    def should_continue(self) -> bool:
        return self.halt_reason() is None

    # ---- serialisation -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "goal": self.goal,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "iteration": self.iteration,
            "max_iterations": self.max_iterations,
            "stall_count": self.stall_count,
            "stall_limit": self.stall_limit,
            "last_signature": self.last_signature,
            "verify_command": self.verify_command,
            "last_verify": None if self.last_verify is None else self.last_verify.to_dict(),
            "tasks": [t.to_dict() for t in self.tasks],
            "blockers": list(self.blockers),
            "history": [h.to_dict() for h in self.history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LoopState":
        version = int(raw.get("version", SCHEMA_VERSION))
        if version > SCHEMA_VERSION:
            raise StateError(
                f"state.json is schema v{version} but this magloop understands v{SCHEMA_VERSION}; upgrade magloop"
            )
        last_verify = raw.get("last_verify")
        return cls(
            goal=str(raw.get("goal", "")),
            verify_command=str(raw.get("verify_command", "")),
            max_iterations=int(raw.get("max_iterations", 12)),
            stall_limit=int(raw.get("stall_limit", 3)),
            status=str(raw.get("status", "running")),
            iteration=int(raw.get("iteration", 0)),
            stall_count=int(raw.get("stall_count", 0)),
            last_signature=str(raw.get("last_signature", "")),
            stop_reason=str(raw.get("stop_reason", "")),
            tasks=[Task.from_dict(t) for t in raw.get("tasks", [])],
            history=[HistoryEntry.from_dict(h) for h in raw.get("history", [])],
            blockers=[str(b) for b in raw.get("blockers", [])],
            last_verify=None if not last_verify else VerifyResult.from_dict(last_verify),
            created_at=str(raw.get("created_at", utcnow())),
            updated_at=str(raw.get("updated_at", utcnow())),
            version=version,
        )

    def save(self, path: Path) -> None:
        self.updated_at = utcnow()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"
        # Write-then-rename so an interrupted run never leaves a half-written state.
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".state-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    @classmethod
    def load(cls, path: Path) -> "LoopState":
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise StateError(f"no loop state at {path}; run `magloop init --goal ...` first") from None
        except json.JSONDecodeError as exc:
            raise StateError(f"{path} is not valid JSON: {exc}") from None
        return cls.from_dict(raw)


def state_path(root: Path) -> Path:
    return root / STATE_DIRNAME / STATE_FILENAME


def find_root(start: Path | None = None) -> Path:
    """Nearest ancestor holding a `.mag-loop/` directory, else the git root, else `start`."""
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if (candidate / STATE_DIRNAME).is_dir():
            return candidate
    for candidate in (start, *start.parents):
        if (candidate / ".git").exists():
            return candidate
    return start
