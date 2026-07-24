import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_e10_conformance import verify


class E10ConformanceTests(unittest.TestCase):
    def test_exact_shared_fixture(self):
        fixture = (
            Path(__file__).resolve().parents[2].parent
            / "BetaEvolve/Packages/BetaEvolveMechanisms/Tests/Fixtures/e10_archive_conformance.json"
        )
        self.assertTrue(verify(fixture)["passed"])


if __name__ == "__main__":
    unittest.main()
