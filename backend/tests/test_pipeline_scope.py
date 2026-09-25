"""Keep the scheduled entry point ingestion-only after the reset."""

import importlib.util
import os
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class PipelineScopeTests(unittest.TestCase):
    def test_daily_steps_are_only_ingest_and_known_board_validation(self):
        path = os.path.join(BACKEND_DIR, "run-daily.py")
        spec = importlib.util.spec_from_file_location("run_daily_scope", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        self.assertEqual(module.STEPS[0],
                         ["tools/ats-discover.py", "--apply", "--nightly", "--known-only"])
        self.assertEqual(module.STEPS[1:], [
            "ingest/ats.py", "ingest/workday.py", "ingest/builtin-nyc.py",
            "ingest/nyc-open-data.py", "ingest/weworkremotely.py",
            "ingest/hn-hiring.py",
        ])
        for step in module.STEPS[1:]:
            self.assertTrue(os.path.isfile(os.path.join(BACKEND_DIR, step)))


if __name__ == "__main__":
    unittest.main()
