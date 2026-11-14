#!/usr/bin/env python3
"""Source-AST regression tests for the review-only NPPS4 server-data reload candidate.

This executes the actual _server_data_fingerprint() and get() function AST from
npps4/data/__init__.py with an isolated fake filesystem/schema. It does not import
the full NPPS4 runtime, open a user database, or touch Android data.
All checks use explicit exceptions so python -O cannot erase them.
"""
from __future__ import annotations

import ast
import io
import json
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "npps4" / "data" / "__init__.py"


def fail(message: str) -> None:
    raise RuntimeError(message)


def check(name: str, condition: bool, outcomes: list[str]) -> None:
    if not condition:
        fail("FAIL: " + name)
    outcomes.append("PASS: " + name)


class FakeStat:
    def __init__(self, mtime_ns: int, ctime_ns: int, size: int, ino: int):
        self.st_mtime_ns = mtime_ns
        self.st_ctime_ns = ctime_ns
        self.st_size = size
        self.st_ino = ino


class FakeOS:
    stat_result = FakeStat

    def __init__(self, stat: FakeStat):
        self.current_stat = stat

    def stat(self, _path: str) -> FakeStat:
        return self.current_stat


class FakeSchema:
    class SerializedServerData:
        @staticmethod
        def model_validate(document: dict):
            if document.get("__invalid_schema__"):
                raise ValueError("synthetic schema rejection")
            return types.SimpleNamespace(
                json_schema_link=document.get("$schema"),
                badwords=document.get("badwords", []),
                achievement_reward=[
                    types.SimpleNamespace(achievement_id=x["achievement_id"], rewards=x["rewards"])
                    for x in document.get("achievement_reward", [])
                ],
                live_unit_drop_chance={},
                common_live_unit_drops=[],
                live_specific_live_unit_drops=[],
                live_effort_drops=[],
                secretbox_data=[],
                serial_codes=[],
                sticker_shop=[],
            )


class FakeUtil:
    class logging:
        ERROR = "ERROR"

    def __init__(self):
        self.logs = []

    def log(self, *args):
        self.logs.append(args)


class Harness:
    def __init__(self, stat: FakeStat, content: str):
        self.os = FakeOS(stat)
        self.content = content
        self.util = FakeUtil()

        def fake_open(_path, _mode, **_kwargs):
            return io.StringIO(self.content)

        self.env = {
            "os": self.os,
            "json": json,
            "schema": FakeSchema,
            "ServerData": lambda **kwargs: types.SimpleNamespace(**kwargs),
            "ensure_no_conflict": lambda items: items,
            "util": self.util,
            "open": fake_open,
            "SERVER_DATA_PATH": "synthetic/server_data.json",
            "server_data": None,
            "last_server_data_fingerprint": None,
            "last_server_data_failed_fingerprint": None,
        }

        tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
        wanted = {"_server_data_fingerprint", "get"}
        nodes = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name in wanted
        ]
        found = {node.name for node in nodes}
        if found != wanted:
            fail(f"source AST missing functions: {sorted(wanted - found)}")
        module = ast.Module(body=nodes, type_ignores=[])
        exec(compile(module, str(SOURCE), "exec"), self.env)

    def get(self):
        return self.env["get"]()


def main() -> None:
    outcomes: list[str] = []

    # Initial successful load establishes the last-successful fingerprint.
    fp_a = FakeStat(200, 300, 10, 1)
    h = Harness(fp_a, json.dumps({"badwords": ["A"]}))
    a = h.get()
    check("initial load", a.badwords == ["A"], outcomes)
    last_a = h.env["last_server_data_fingerprint"]

    # A failed reload with cached data must not advance the last-successful fingerprint.
    fp_b = FakeStat(210, 310, 11, 2)
    h.os.current_stat = fp_b
    h.content = "{ invalid json"
    fallback = h.get()
    check("failed reload retains old cache", fallback.badwords == ["A"], outcomes)
    check("failed reload retains prior successful fingerprint",
          h.env["last_server_data_fingerprint"] == last_a, outcomes)
    check("failed fingerprint is remembered",
          h.env["last_server_data_failed_fingerprint"] == (210, 310, 11, 2), outcomes)
    check("failed reload is logged", len(h.util.logs) == 1, outcomes)

    # A repeat with the same failed fingerprint is not reparsed or relogged.
    h.get()
    check("unchanged invalid fingerprint is not retried repeatedly",
          len(h.util.logs) == 1, outcomes)

    # Repair by replacing the file while preserving mtime; ctime/size/inode change.
    fp_b2 = FakeStat(210, 311, 12, 3)
    h.os.current_stat = fp_b2
    h.content = json.dumps({"badwords": ["B"]})
    repaired = h.get()
    check("same-mtime replacement is retried", repaired.badwords == ["B"], outcomes)
    check("successful retry records new fingerprint",
          h.env["last_server_data_fingerprint"] == (210, 311, 12, 3), outcomes)
    check("successful retry clears failed fingerprint",
          h.env["last_server_data_failed_fingerprint"] is None, outcomes)

    # Restoring a valid backup with an older mtime still changes ctime/inode and reloads.
    fp_c = FakeStat(150, 320, 13, 4)
    h.os.current_stat = fp_c
    h.content = json.dumps({"badwords": ["RESTORED"]})
    restored = h.get()
    check("older-mtime restore is detected", restored.badwords == ["RESTORED"], outcomes)

    # Same mtime/size but a changed ctime/inode is detected as a replacement.
    fp_d = FakeStat(150, 321, 13, 5)
    h.os.current_stat = fp_d
    h.content = json.dumps({"badwords": ["REPLACED"]})
    replaced = h.get()
    check("same-mtime replacement is detected", replaced.badwords == ["REPLACED"], outcomes)

    # Residual limitation: an in-place edit preserving the entire fingerprint is invisible.
    h.content = json.dumps({"badwords": ["UNDETECTED"]})
    unchanged_fingerprint = h.get()
    check("same-fingerprint in-place edit remains undetected",
          unchanged_fingerprint.badwords == ["REPLACED"], outcomes)

    # With no cache, a first invalid file raises; server_data remains None, so a
    # corrected file with the same identity is retried on the next call.
    fp_e = FakeStat(400, 500, 10, 6)
    cold = Harness(fp_e, "{ invalid json")
    first_failed = False
    try:
        cold.get()
    except Exception:
        first_failed = True
    check("initial invalid load fails closed", first_failed, outcomes)
    check("initial failure does not set successful fingerprint",
          cold.env["last_server_data_fingerprint"] is None, outcomes)
    cold.content = json.dumps({"badwords": ["COLD-REPAIR"]})
    cold_repaired = cold.get()
    check("cold-start same-fingerprint repair retries",
          cold_repaired.badwords == ["COLD-REPAIR"], outcomes)

    print("\n".join(outcomes))
    print(f"TOTAL {len(outcomes)}/{len(outcomes)}")


if __name__ == "__main__":
    main()
