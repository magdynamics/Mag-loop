import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from magloop.state import LoopState, StateError, VerifyResult, find_root, state_path


def make_state(**kwargs):
    defaults = dict(goal="ship the thing", verify_command="true", max_iterations=5, stall_limit=2)
    defaults.update(kwargs)
    return LoopState(**defaults)


class TaskTests(unittest.TestCase):
    def test_ids_increment_and_survive_removal(self):
        state = make_state()
        first = state.add_task("a")
        second = state.add_task("b")
        self.assertEqual([first.id, second.id], [1, 2])
        state.tasks.remove(first)
        self.assertEqual(state.add_task("c").id, 3)

    def test_empty_title_rejected(self):
        with self.assertRaises(StateError):
            make_state().add_task("   ")

    def test_open_tasks_excludes_closed(self):
        state = make_state()
        state.add_task("a")
        state.add_task("b")
        state.add_task("c")
        state.set_task_status(2, "done")
        state.set_task_status(3, "dropped")
        self.assertEqual([t.id for t in state.open_tasks], [1])

    def test_unknown_status_and_id_rejected(self):
        state = make_state()
        state.add_task("a")
        with self.assertRaises(StateError):
            state.set_task_status(1, "finished")
        with self.assertRaises(StateError):
            state.set_task_status(99, "done")


class GuardrailTests(unittest.TestCase):
    def test_fresh_run_continues(self):
        state = make_state()
        state.add_task("a")
        self.assertIsNone(state.halt_reason())

    def test_iteration_budget_halts(self):
        state = make_state(max_iterations=2)
        state.add_task("a")
        for _ in range(2):
            state.add_task("more work")  # keep the signature moving
            state.record_iteration("did a thing")
        self.assertIn("iteration budget exhausted", state.halt_reason())

    def test_stall_detected_when_nothing_changes(self):
        state = make_state(stall_limit=2)
        state.add_task("a")
        state.record_iteration("noop")
        self.assertEqual(state.stall_count, 0)
        state.record_iteration("noop again")
        self.assertEqual(state.stall_count, 1)
        state.record_iteration("noop once more")
        self.assertEqual(state.stall_count, 2)
        self.assertIn("no progress", state.halt_reason())

    def test_progress_resets_stall_count(self):
        state = make_state(stall_limit=2)
        state.add_task("a")
        state.record_iteration("noop")
        state.record_iteration("noop")
        self.assertEqual(state.stall_count, 1)
        state.add_task("newly discovered work")
        state.record_iteration("found more to do")
        self.assertEqual(state.stall_count, 0)

    def test_verification_failure_keeps_loop_alive_with_all_tasks_closed(self):
        state = make_state()
        state.add_task("a")
        state.set_task_status(1, "done")
        state.record_verify(VerifyResult(command="true", exit_code=1, summary="boom"))
        self.assertIsNone(state.halt_reason())

    def test_all_tasks_closed_and_green_halts(self):
        state = make_state()
        state.add_task("a")
        state.set_task_status(1, "done")
        state.record_verify(VerifyResult(command="true", exit_code=0, summary="ok"))
        self.assertIn("all tasks closed", state.halt_reason())

    def test_no_tasks_does_not_count_as_finished(self):
        state = make_state()
        self.assertIsNone(state.halt_reason())

    def test_blocker_halts(self):
        state = make_state()
        state.add_task("a")
        state.add_blocker("need production credentials")
        self.assertIn("need production credentials", state.halt_reason())

    def test_blockers_deduplicate(self):
        state = make_state()
        state.add_blocker("same")
        state.add_blocker("same")
        state.add_blocker("  ")
        self.assertEqual(state.blockers, ["same"])

    def test_recording_on_finished_run_rejected(self):
        state = make_state()
        state.stop("done", "finished")
        with self.assertRaises(StateError):
            state.record_iteration("too late")

    def test_terminal_decision_sets_status(self):
        state = make_state()
        state.add_task("a")
        state.record_iteration("wrapped up", decision="done")
        self.assertEqual(state.status, "done")
        self.assertIn("done", state.halt_reason())

    def test_unknown_decision_rejected(self):
        state = make_state()
        with self.assertRaises(StateError):
            state.record_iteration("x", decision="maybe")


class PersistenceTests(unittest.TestCase):
    def test_round_trip_preserves_everything(self):
        state = make_state()
        state.add_task("a", note="careful")
        state.set_task_status(1, "doing")
        state.record_verify(VerifyResult(command="pytest", exit_code=1, summary="1 failed"))
        state.record_iteration("started task a")
        state.add_blocker("needs review")

        with tempfile.TemporaryDirectory() as tmp:
            path = state_path(Path(tmp))
            state.save(path)
            loaded = LoopState.load(path)

        self.assertEqual(loaded.to_dict(), state.to_dict())
        self.assertEqual(loaded.tasks[0].note, "careful")
        self.assertFalse(loaded.last_verify.ok)
        self.assertEqual(loaded.history[0].verify_ok, False)

    def test_save_is_atomic_and_leaves_no_temp_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = state_path(Path(tmp))
            make_state().save(path)
            make_state(goal="second").save(path)
            leftovers = [p.name for p in path.parent.iterdir() if p.name != path.name]
            self.assertEqual(leftovers, [])
            self.assertEqual(LoopState.load(path).goal, "second")

    def test_missing_and_malformed_state_give_actionable_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = state_path(Path(tmp))
            with self.assertRaises(StateError) as ctx:
                LoopState.load(path)
            self.assertIn("magloop init", str(ctx.exception))

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(StateError) as ctx:
                LoopState.load(path)
            self.assertIn("not valid JSON", str(ctx.exception))

    def test_future_schema_version_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = state_path(Path(tmp))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"version": 99, "goal": "x"}), encoding="utf-8")
            with self.assertRaises(StateError) as ctx:
                LoopState.load(path)
            self.assertIn("upgrade magloop", str(ctx.exception))


class FindRootTests(unittest.TestCase):
    def test_prefers_existing_loop_dir_over_git_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            nested = root / "pkg" / "sub"
            nested.mkdir(parents=True)
            (root / "pkg" / ".mag-loop").mkdir()
            self.assertEqual(find_root(nested), root / "pkg")

    def test_falls_back_to_git_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            nested = root / "a" / "b"
            nested.mkdir(parents=True)
            self.assertEqual(find_root(nested), root)


if __name__ == "__main__":
    unittest.main()
