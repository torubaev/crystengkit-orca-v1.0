import tempfile
import unittest
from pathlib import Path

from tools.Orca_input.orca_job_queue import OrcaJobQueue, OrcaQueueJob

WORK_ROOT = Path(__file__).resolve().parents[1] / "tmp" / "codex_work"


class OrcaJobQueueTests(unittest.TestCase):
    def test_remove_indices_mutates_active_queue_and_reports_count(self):
        queue = OrcaJobQueue({
            "work": [
                OrcaQueueJob("a.inp", "a.out"),
                OrcaQueueJob("b.inp", "b.out"),
                OrcaQueueJob("c.inp", "c.out"),
            ]
        }, "work")

        removed = queue.remove_indices([2, 0, 99])

        self.assertEqual(removed, 2)
        self.assertEqual([job.name for job in queue.jobs], ["b.inp"])

    def test_reset_finished_requeues_terminal_jobs(self):
        queue = OrcaJobQueue({
            "work": [
                OrcaQueueJob("a.inp", "a.out", "done", "ok"),
                OrcaQueueJob("b.inp", "b.out", "failed", "bad"),
                OrcaQueueJob("c.inp", "c.out", "queued", ""),
            ]
        }, "work")

        queue.reset_pending()

        self.assertEqual([job.status for job in queue.jobs], ["queued", "queued", "queued"])
        self.assertEqual([job.message for job in queue.jobs], ["", "", ""])

    def test_save_and_load_preserve_named_queues(self):
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        queue = OrcaJobQueue({
            "first": [OrcaQueueJob("a.inp", "a.out", "done", "ok")],
            "second": [OrcaQueueJob(
                "b.inp",
                "b.out",
                context={"interaction_enabled": True, "frag_a_charge": 0},
            )],
        }, "second")
        with tempfile.TemporaryDirectory(dir=WORK_ROOT) as directory:
            path = Path(directory) / "jobs.orcaqueue.json"
            queue.save(path)
            loaded = OrcaJobQueue.load(path)

        self.assertEqual(loaded.queue_names(), ["first", "second"])
        self.assertEqual(loaded.active_queue, "second")
        self.assertEqual(loaded.jobs[0].name, "b.inp")
        self.assertTrue(loaded.jobs[0].context["interaction_enabled"])
        self.assertEqual(loaded.jobs[0].context["frag_a_charge"], 0)

    def test_old_queue_json_without_context_remains_compatible(self):
        queue = OrcaJobQueue.from_json(
            '{"jobs": [{"input_path": "a.inp", "output_path": "a.out"}]}'
        )

        self.assertEqual(queue.jobs[0].context, {})


if __name__ == "__main__":
    unittest.main()
