import ast
import importlib.util
from pathlib import Path
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = BACKEND_ROOT / "npps4" / "system" / "core.py"
USER_PATH = BACKEND_ROOT / "npps4" / "system" / "user.py"


def _load_core():
    spec = importlib.util.spec_from_file_location("npps4_rankup_core", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load NPPS4 core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _is_core_call(node: ast.AST, method: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == method
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "core"
    )


def _simulate(core, start_level: int, total_exp: int, incremental: bool):
    level = start_level
    next_exp = core.get_next_exp_cumulative(level)
    transitions = [(level, total_exp)]

    for _ in range(20_001):
        if total_exp < next_exp:
            return level, transitions, next_exp

        level += 1
        transitions.append((level, next_exp))
        if incremental:
            next_exp += core.get_next_exp(level)
        else:
            next_exp = core.get_next_exp_cumulative(level)

    raise AssertionError("rank-up simulation exceeded the safety bound")


class AddExpRankUpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = _load_core()
        cls.user_tree = ast.parse(USER_PATH.read_text(encoding="utf-8"))
        cls.add_exp = next(
            (
                node
                for node in cls.user_tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "add_exp"
            ),
            None,
        )
        if cls.add_exp is None:
            raise RuntimeError("npps4.system.user.add_exp is missing")

    def test_cumulative_threshold_is_exactly_previous_plus_next_rank(self):
        for rank in (1, 2, 33, 34, 99, 100, 101, 299, 300, 301, 999, 1000, 2000, 10000):
            with self.subTest(rank=rank):
                expected = (
                    self.core.get_next_exp_cumulative(rank - 1)
                    + self.core.get_next_exp(rank)
                )
                self.assertEqual(self.core.get_next_exp_cumulative(rank), expected)

    def test_actual_add_exp_uses_one_initial_lookup_and_incremental_loop(self):
        cumulative_calls = [
            node for node in ast.walk(self.add_exp) if _is_core_call(node, "get_next_exp_cumulative")
        ]
        self.assertEqual(len(cumulative_calls), 1)

        loops = [node for node in ast.walk(self.add_exp) if isinstance(node, ast.While)]
        self.assertEqual(len(loops), 1)
        self.assertFalse(
            any(_is_core_call(node, "get_next_exp_cumulative") for node in ast.walk(loops[0]))
        )

        increments = [
            statement
            for statement in loops[0].body
            if isinstance(statement, ast.AugAssign)
            and isinstance(statement.target, ast.Name)
            and statement.target.id == "next_exp"
            and isinstance(statement.op, ast.Add)
            and _is_core_call(statement.value, "get_next_exp")
        ]
        self.assertEqual(len(increments), 1)
        argument = increments[0].value.args[0]
        self.assertIsInstance(argument, ast.Attribute)
        self.assertEqual(argument.attr, "level")
        self.assertIsInstance(argument.value, ast.Name)
        self.assertEqual(argument.value.id, "user")

        validate_calls = [
            node for node in ast.walk(self.add_exp) if _is_core_call(node, "validate_exp_delta")
        ]
        self.assertEqual(len(validate_calls), 1)
        self.assertIsInstance(self.add_exp.body[0], ast.Assign)
        self.assertTrue(_is_core_call(self.add_exp.body[0].value, "validate_exp_delta"))

    def test_incremental_and_cumulative_transition_sequences_match(self):
        for start_level in (1, 2, 33, 34, 99, 100, 101, 299, 300, 301, 999):
            base = self.core.get_next_exp_cumulative(start_level)
            for award in (0, 1, 2, 10, 1000, 1_000_000, 100_000_000):
                total_exp = max(0, base - 1 + award)
                with self.subTest(start_level=start_level, award=award):
                    expected = _simulate(self.core, start_level, total_exp, False)
                    actual = _simulate(self.core, start_level, total_exp, True)
                    self.assertEqual(actual, expected)

        start_level = 100
        total_exp = self.core.get_next_exp_cumulative(start_level) + 100_000_000
        self.assertEqual(
            _simulate(self.core, start_level, total_exp, True),
            _simulate(self.core, start_level, total_exp, False),
        )


if __name__ == "__main__":
    unittest.main()
