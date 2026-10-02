import json
import unittest
from cryptolab import *

EXAMPLE = json.loads(
    '{"blocks": [{"subsidy": 100, "transactions": [{"id": "genesis", "inputs": [], "outputs": [{"owner": "alice", "amount": 100}]}]}, {"transactions": [{"id": "spend", "inputs": [{"txid": "genesis", "index": 0, "owner": "alice"}], "outputs": [{"owner": "bob", "amount": 60}, {"owner": "alice", "amount": 35}]}]}]}'
)


class EngineTests(unittest.TestCase):
    def test_conservation(self):
        r = analyze(EXAMPLE)
        self.assertEqual(r["supply"], 95)
        self.assertEqual(r["block_results"][1]["fees"], 5)

    def test_rollback(self):
        r = analyze({**EXAMPLE, "rollback_blocks": 1})
        self.assertEqual(r["balances"], {"alice": 100})

    def test_atomic_failure(self):
        l = Ledger()
        l.apply(EXAMPLE["blocks"][0])
        before = l.snapshot()
        bad = {
            "transactions": [
                {
                    "id": "bad",
                    "inputs": [{"txid": "genesis", "index": 0, "owner": "alice"}],
                    "outputs": [{"owner": "bob", "amount": 101}],
                }
            ]
        }
        with self.assertRaises(ValueError):
            l.apply(bad)
        self.assertEqual(l.snapshot(), before)

    def test_deterministic(self):
        self.assertEqual(analyze(EXAMPLE), analyze(EXAMPLE))

    def test_cli_json(self):
        import subprocess, sys

        result = subprocess.run(
            [sys.executable, "-m", "cryptolab", "examples/input.json"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), analyze(EXAMPLE))

    def test_cli_csv(self):
        import subprocess, sys, csv, io

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "cryptolab",
                "examples/input.json",
                "--format",
                "csv",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            list(csv.reader(io.StringIO(result.stdout)))[0], ["path", "value"]
        )

    def test_duplicate_json_keys(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"a":1,"a":2}')
            with self.assertRaises(ValueError):
                load_input(path)

    def test_atomic_output(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "out.json"
            self.assertEqual(main(["examples/input.json", "--output", str(path)]), 0)
            self.assertEqual(json.loads(path.read_text()), analyze(EXAMPLE))

    def test_input_unchanged(self):
        import copy

        before = copy.deepcopy(EXAMPLE)
        analyze(EXAMPLE)
        self.assertEqual(before, EXAMPLE)


if __name__ == "__main__":
    unittest.main()
