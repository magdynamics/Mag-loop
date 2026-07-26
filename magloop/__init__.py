"""Mag Loop — a resumable, verification-gated agentic loop for coding work."""

from magloop.state import LoopState, StateError, Task, VerifyResult

__version__ = "0.1.0"

__all__ = ["LoopState", "StateError", "Task", "VerifyResult", "__version__"]
