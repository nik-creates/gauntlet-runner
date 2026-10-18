import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import runner

FAILED = {"status": "completed", "verdict": "failed", "tests_passed": 0, "tests_total": 5}


class RunnerTests(unittest.TestCase):
    def test_signature_matches_gateway(self):
        self.assertEqual(
            runner.sign(b"k", "result", "j1", b'{"a":1}'),
            "e81f48ca5fa3c0a16608d363b78dc176f1509ac688772da9a0ec906df20fd54b",
        )

    def test_passed(self):
        r = runner.verdict_from({"passed": 5, "total": 5}, 5, False)
        self.assertEqual((r["verdict"], r["tests_passed"]), ("passed", 5))

    def test_partial_is_failed(self):
        r = runner.verdict_from({"passed": 3, "total": 5}, 5, False)
        self.assertEqual((r["verdict"], r["tests_passed"]), ("failed", 3))

    def test_missing_or_timeout_is_failed(self):
        self.assertEqual(runner.verdict_from(None, 5, False), FAILED)
        self.assertEqual(runner.verdict_from({"passed": 5, "total": 5}, 5, True), FAILED)

    def test_tampered_totals_are_rejected(self):
        for bad in ({"passed": 1, "total": 1}, {"passed": 9, "total": 5}, {"passed": -1, "total": 5},
                    {"passed": True, "total": 5}, {"passed": "5", "total": 5}, {}):
            self.assertEqual(runner.verdict_from(bad, 5, False), FAILED, bad)

    def test_image_allowlist_and_job_id(self):
        self.assertIn("python:3.12-slim", runner.allowed_images())
        self.assertNotIn("ubuntu:latest", runner.allowed_images())
        self.assertTrue(runner.JOB_ID_RE.match("123e4567-e89b-12d3-a456-426614174000"))
        self.assertFalse(runner.JOB_ID_RE.match("x; rm -rf /"))


if __name__ == "__main__":
    unittest.main()
