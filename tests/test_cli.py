import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from magloop.brief import render_brief
from magloop.cli import main
from magloop.state import LoopState, state_path


class CliHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)

    def run_cli(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = main(["--root", str(self.root), *args])
        return code, buf.getvalue()

    def state(self):
        return LoopState.load(state_path(self.root))

    def init(self, *extra):
        return self.run_cli("init", "--goal", "make tests pass", "--verify", "true", *extra)


class InitTests(CliHarness):
    def test_init_writes_state(self):
        code, out = self.init("--task", "one", "--task", "two")
        self.assertEqual(code, 0)
        self.assertIn("initialised loop", out)
        state = self.state()
        self.assertEqual(state.goal, "make tests pass")
        self.assertEqual([t.title for t in state.tasks], ["one", "two"])

    def test_second_init_refuses_without_force(self):
        self.init()
        code, out = self.init()
        self.assertEqual(code, 1)
        self.assertIn("already initialised", out)

    def test_force_overwrites(self):
        self.init("--task", "one")
        code, _ = self.run_cli("init", "--goal", "different", "--verify", "true", "--force")
        self.assertEqual(code, 0)
        self.assertEqual(self.state().goal, "different")
        self.assertEqual(self.state().tasks, [])


class TaskCommandTests(CliHarness):
    def test_add_start_done_drop(self):
        self.init()
        self.run_cli("task", "add", "alpha", "beta")
        self.assertEqual(len(self.state().tasks), 2)

        self.run_cli("task", "start", "1")
        self.assertEqual(self.state().get_task(1).status, "doing")

        self.run_cli("task", "done", "1", "--note", "verified")
        self.assertEqual(self.state().get_task(1).status, "done")
        self.assertEqual(self.state().get_task(1).note, "verified")

        self.run_cli("task", "drop", "2")
        self.assertEqual(self.state().get_task(2).status, "dropped")

    def test_non_numeric_id_is_a_clean_error(self):
        self.init()
        self.run_cli("task", "add", "alpha")
        code, out = self.run_cli("task", "done", "alpha")
        self.assertEqual(code, 2)
        self.assertIn("must be a number", out)


class VerifyTests(CliHarness):
    def test_passing_command_recorded(self):
        self.init()
        code, _ = self.run_cli("verify", "echo hello")
        self.assertEqual(code, 0)
        verify = self.state().last_verify
        self.assertTrue(verify.ok)
        self.assertIn("hello", verify.summary)

    def test_failing_command_recorded_and_returns_nonzero(self):
        self.init()
        code, _ = self.run_cli("verify", "echo boom >&2; exit 3")
        self.assertEqual(code, 1)
        verify = self.state().last_verify
        self.assertFalse(verify.ok)
        self.assertEqual(verify.exit_code, 3)
        self.assertIn("boom", verify.summary)

    def test_missing_command_is_rejected(self):
        self.run_cli("init", "--goal", "g")
        code, out = self.run_cli("verify")
        self.assertEqual(code, 2)
        self.assertIn("no verify command", out)

    def test_verify_runs_in_project_root(self):
        self.init()
        (self.root / "marker.txt").write_text("here", encoding="utf-8")
        self.run_cli("verify", "cat marker.txt")
        self.assertIn("here", self.state().last_verify.summary)


class RecordTests(CliHarness):
    def test_record_advances_iteration(self):
        self.init("--task", "one")
        code, out = self.run_cli("record", "--action", "did the thing")
        self.assertEqual(code, 0)
        self.assertEqual(self.state().iteration, 1)
        self.assertIn("continue", out)

    def test_record_done_ends_run(self):
        self.init("--task", "one")
        self.run_cli("record", "--action", "finished", "--decision", "done")
        self.assertEqual(self.state().status, "done")

    def test_record_on_finished_run_is_a_clean_error(self):
        self.init("--task", "one")
        self.run_cli("stop", "--status", "done", "--reason", "manual")
        code, out = self.run_cli("record", "--action", "late")
        self.assertEqual(code, 2)
        self.assertIn("magloop reset", out)

    def test_budget_exhaustion_shows_in_record_output(self):
        self.init("--max-iterations", "1", "--task", "one")
        _, out = self.run_cli("record", "--action", "one and done")
        self.assertIn("HALT", out)
        self.assertIn("iteration budget exhausted", out)


class BlockAndResetTests(CliHarness):
    def test_block_then_unblock(self):
        self.init("--task", "one")
        self.run_cli("block", "need an API key")
        self.assertIn("need an API key", self.state().halt_reason())
        self.run_cli("unblock")
        self.assertIsNone(self.state().halt_reason())

    def test_reset_clears_progress_but_keeps_config(self):
        self.init("--task", "one")
        self.run_cli("record", "--action", "something")
        self.run_cli("reset")
        state = self.state()
        self.assertEqual(state.iteration, 0)
        self.assertEqual(state.history, [])
        self.assertEqual(state.tasks, [])
        self.assertEqual(state.goal, "make tests pass")
        self.assertEqual(state.verify_command, "true")

    def test_reset_keep_tasks_preserves_statuses(self):
        self.init("--task", "one", "--task", "two")
        self.run_cli("task", "done", "1")
        self.run_cli("reset", "--keep-tasks", "--goal", "new goal")
        state = self.state()
        self.assertEqual(state.goal, "new goal")
        self.assertEqual([(t.title, t.status) for t in state.tasks], [("one", "done"), ("two", "todo")])


class ReportingTests(CliHarness):
    def test_status_and_log_render(self):
        self.init("--task", "one")
        self.run_cli("verify", "echo ok")
        self.run_cli("record", "--action", "ran the tests")

        _, status = self.run_cli("status")
        self.assertIn("make tests pass", status)
        self.assertIn("[ ] 1. one", status)
        self.assertIn("pass", status)

        _, log = self.run_cli("log")
        self.assertIn("ran the tests", log)

    def test_status_json_is_machine_readable(self):
        import json

        self.init()
        _, out = self.run_cli("status", "--json")
        self.assertEqual(json.loads(out)["goal"], "make tests pass")

    def test_log_on_fresh_run(self):
        self.init()
        _, out = self.run_cli("log")
        self.assertIn("no iterations recorded", out)

    def test_no_state_gives_actionable_error(self):
        code, out = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("magloop init", out)


class BriefTests(CliHarness):
    def test_brief_carries_working_context(self):
        self.init("--task", "one")
        self.run_cli("verify", "echo boom >&2; exit 1")
        self.run_cli("record", "--action", "first attempt")

        _, out = self.run_cli("brief")
        self.assertIn("iteration 2 of 12", out)
        self.assertIn("make tests pass", out)
        self.assertIn("[1] one", out)
        self.assertIn("FAILED (exit 1)", out)
        self.assertIn("boom", out)
        self.assertIn("first attempt", out)
        self.assertIn("magloop record", out)

    def test_brief_says_halt_and_drops_protocol_when_guardrail_trips(self):
        self.init("--max-iterations", "1", "--task", "one")
        self.run_cli("record", "--action", "used the whole budget")
        _, out = self.run_cli("brief")
        self.assertIn("HALT", out)
        self.assertIn("iteration budget exhausted", out)
        self.assertNotIn("## Protocol", out)

    def test_brief_prompts_for_a_plan_when_no_tasks_exist(self):
        self.init()
        _, out = self.run_cli("brief")
        self.assertIn("magloop task add", out)

    def test_render_brief_ends_with_single_newline(self):
        self.init("--task", "one")
        text = render_brief(self.state())
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))


class RunnerTests(CliHarness):
    def test_dry_run_prints_prompt_without_invoking_claude(self):
        self.init("--task", "one")
        code, out = self.run_cli("run", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("one iteration of a Mag Loop run", out)
        self.assertIn("[1] one", out)
        self.assertEqual(self.state().iteration, 0)

    def test_dry_run_reports_halt(self):
        self.init("--max-iterations", "1", "--task", "one")
        self.run_cli("record", "--action", "done for now")
        code, out = self.run_cli("run", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("would halt", out)

    def test_missing_claude_binary_is_a_clean_error(self):
        self.init("--task", "one")
        code, out = self.run_cli("run", "--claude-bin", "definitely-not-a-real-binary")
        self.assertEqual(code, 2)
        self.assertIn("cannot find", out)

    def test_runner_records_iterations_the_agent_skipped(self):
        """The budget only bites if the counter moves, agent cooperation or not."""
        self.init("--max-iterations", "2", "--task", "one")
        code, out = self.run_cli("run", "--claude-bin", "true")
        self.assertEqual(code, 0)
        self.assertEqual(self.state().iteration, 2)
        self.assertIn("did not record", out)
        self.assertIn("iteration budget exhausted", out)

    def test_iterations_flag_caps_a_single_invocation(self):
        self.init("--max-iterations", "10", "--task", "one")
        self.run_cli("run", "--claude-bin", "true", "--iterations", "1")
        self.assertEqual(self.state().iteration, 1)
        self.assertEqual(self.state().status, "running")


if __name__ == "__main__":
    unittest.main()
