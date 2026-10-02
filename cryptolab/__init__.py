"""Validate synthetic UTXO transactions, conservation, fees, coinbase limits and reversible block application."""

import json

import copy


class Ledger:
    def __init__(self):
        self.utxos = {}
        self.history = []
        self.txids = set()

    def apply(self, block):
        state = copy.deepcopy(self.utxos)
        ids = set(self.txids)
        fees = 0
        coinbase = 0
        seen_coinbase = False
        for offset, tx in enumerate(block["transactions"]):
            txid = tx["id"]
            if not txid or txid in ids:
                raise ValueError("duplicate transaction id")
            ids.add(txid)
            inputs = tx["inputs"]
            outputs = tx["outputs"]
            value_out = 0
            if not outputs:
                raise ValueError("outputs required")
            for index, out in enumerate(outputs):
                amount = out["amount"]
                if (
                    not isinstance(amount, int)
                    or isinstance(amount, bool)
                    or amount <= 0
                    or not out["owner"]
                ):
                    raise ValueError("invalid output")
                value_out += amount
            if not inputs:
                if offset != 0 or seen_coinbase:
                    raise ValueError("coinbase must be first and unique")
                seen_coinbase = True
                coinbase = value_out
            else:
                consumed = set()
                value_in = 0
                for item in inputs:
                    key = (item["txid"], item["index"])
                    if key in consumed or key not in state:
                        raise ValueError("double spend or missing output")
                    consumed.add(key)
                    out = state.pop(key)
                    if item["owner"] != out["owner"]:
                        raise ValueError("owner mismatch")
                    value_in += out["amount"]
                if value_in < value_out:
                    raise ValueError("inflation")
                fees += value_in - value_out
            for index, out in enumerate(outputs):
                state[(txid, index)] = dict(out)
        subsidy = block.get("subsidy", 0)
        if not isinstance(subsidy, int) or subsidy < 0 or coinbase > subsidy + fees:
            raise ValueError("coinbase exceeds subsidy and fees")
        self.history.append((self.utxos, self.txids))
        self.utxos = state
        self.txids = ids
        return {"fees": fees, "coinbase": coinbase}

    def rollback(self):
        if not self.history:
            raise ValueError("no block to roll back")
        self.utxos, self.txids = self.history.pop()

    def snapshot(self):
        balances = {}
        for out in self.utxos.values():
            balances[out["owner"]] = balances.get(out["owner"], 0) + out["amount"]
        return {
            "balances": balances,
            "utxo_count": len(self.utxos),
            "supply": sum(balances.values()),
            "height": len(self.history),
        }


def analyze(data):
    ledger = Ledger()
    blocks = []
    for block in data["blocks"]:
        blocks.append(ledger.apply(block))
    for _ in range(data.get("rollback_blocks", 0)):
        ledger.rollback()
    return {**ledger.snapshot(), "block_results": blocks}


import argparse
import csv
import io
import sys
from pathlib import Path


def load_input(path):
    raw = Path(path).read_text(encoding="utf-8")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("invalid JSON constant: " + value)

    data = json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    return data


def flatten(value, prefix=""):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            rows.extend(flatten(item, f"{prefix}.{key}" if prefix else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(flatten(item, f"{prefix}[{index}]"))
    else:
        rows.append((prefix, json.dumps(value, ensure_ascii=False)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="JSON input file")
    parser.add_argument("--output", help="write result atomically to a file")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    args = parser.parse_args(argv)
    try:
        result = analyze(load_input(args.input))
        if args.format == "json":
            content = (
                json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
            )
        else:
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow(["path", "value"])
            writer.writerows(flatten(result))
            content = buffer.getvalue()
        if args.output:
            import os, tempfile

            target = Path(args.output)
            fd, temporary = tempfile.mkstemp(
                prefix="." + target.name + ".", dir=target.parent
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(content)
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        else:
            sys.stdout.write(content)
    except (ValueError, KeyError, TypeError, OSError, ArithmeticError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
