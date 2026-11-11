import ast
import importlib.util
import unittest
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
CORE_PATH = BACKEND_ROOT / "npps4" / "system" / "core.py"
USER_PATH = BACKEND_ROOT / "npps4" / "system" / "user.py"


def _load_core():
    spec = importlib.util.spec_from_file_location("npps4_exp_total_core", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load NPPS4 core.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass
class NextLevelInfo:
    level: int
    from_exp: int


def _load_set_exp_total():
    user_tree = ast.parse(USER_PATH.read_text(encoding="utf-8"))
    function = next(
        (
            node
            for node in user_tree.body
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "set_exp_total"
        ),
        None,
    )
    if function is None:
        raise RuntimeError("npps4.system.user.set_exp_total is missing")

    namespace = {
        "core": _load_core(),
        "idol": SimpleNamespace(BasicSchoolIdolContext=object),
        "main": SimpleNamespace(User=object),
        "NextLevelInfo": NextLevelInfo,
        "add_exp": None,
    }
    module = ast.Module(body=[function], type_ignores=[])
    exec(compile(module, str(USER_PATH), "exec"), namespace)
    return namespace


class ExpTotalValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.core = _load_core()

    def test_valid_absolute_totals(self):
        for value in (0, 1, 123456789, self.core.MAX_SQLITE_INT):
            with self.subTest(value=value):
                self.assertEqual(self.core.validate_exp_total(value), value)

    def test_invalid_absolute_totals_are_rejected(self):
        for value in (True, False, -1, 1.5, "10", None, self.core.MAX_SQLITE_INT + 1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.core.validate_exp_total(cast(Any, value))


class SetExpTotalTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.function_globals = _load_set_exp_total()
        cls.core = cls.function_globals["core"]
        cls.set_exp_total = cls.function_globals["set_exp_total"]

    def setUp(self):
        self.context = SimpleNamespace(db=SimpleNamespace(main=SimpleNamespace(flush=AsyncMock())))
        self.add_exp = AsyncMock()
        self.function_globals["add_exp"] = self.add_exp

    def make_user(self, level: int, exp: int) -> SimpleNamespace:
        return SimpleNamespace(level=level, exp=exp)

    async def test_lowering_within_current_rank_updates_only_exp(self):
        level = 10
        rank_floor = self.core.get_next_exp_cumulative(level - 1)
        current_exp = rank_floor + 50
        target_exp = rank_floor + 25
        user = self.make_user(level, current_exp)

        result = await self.set_exp_total(self.context, user, target_exp)

        self.assertEqual(user.exp, target_exp)
        self.context.db.main.flush.assert_awaited_once_with()
        self.add_exp.assert_not_awaited()
        self.assertEqual(result, [NextLevelInfo(level=level, from_exp=current_exp)])

    async def test_lowering_below_rank_floor_is_rejected_without_mutation(self):
        level = 10
        rank_floor = self.core.get_next_exp_cumulative(level - 1)
        current_exp = rank_floor + 25
        user = self.make_user(level, current_exp)

        with self.assertRaisesRegex(ValueError, "rank downgrade"):
            await self.set_exp_total(self.context, user, rank_floor - 1)

        self.assertEqual(user.exp, current_exp)
        self.context.db.main.flush.assert_not_awaited()
        self.add_exp.assert_not_awaited()

    async def test_increasing_absolute_total_reuses_existing_rankup_logic(self):
        level = 10
        rank_floor = self.core.get_next_exp_cumulative(level - 1)
        current_exp = rank_floor + 25
        target_exp = self.core.get_next_exp_cumulative(level) + 50
        user = self.make_user(level, current_exp)
        expected = [NextLevelInfo(level=level, from_exp=current_exp)]
        self.add_exp.return_value = expected

        result = await self.set_exp_total(self.context, user, target_exp)

        self.add_exp.assert_awaited_once_with(self.context, user, target_exp - current_exp)
        self.assertIs(result, expected)
        self.assertEqual(user.exp, current_exp)

    async def test_same_absolute_total_is_a_noop(self):
        level = 10
        current_exp = self.core.get_next_exp_cumulative(level - 1) + 25
        user = self.make_user(level, current_exp)

        result = await self.set_exp_total(self.context, user, current_exp)

        self.assertEqual(user.exp, current_exp)
        self.context.db.main.flush.assert_not_awaited()
        self.add_exp.assert_not_awaited()
        self.assertEqual(result, [NextLevelInfo(level=level, from_exp=current_exp)])

    async def test_inconsistent_current_rank_is_rejected(self):
        level = 10
        user = self.make_user(level, self.core.get_next_exp_cumulative(level))

        with self.assertRaisesRegex(ValueError, "inconsistent"):
            await self.set_exp_total(self.context, user, user.exp)

        self.context.db.main.flush.assert_not_awaited()
        self.add_exp.assert_not_awaited()

    async def test_invalid_total_is_rejected_before_mutation(self):
        level = 10
        current_exp = self.core.get_next_exp_cumulative(level - 1) + 25
        user = self.make_user(level, current_exp)

        for target in (True, -1, 1.5, "100", self.core.MAX_SQLITE_INT + 1):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    await self.set_exp_total(self.context, user, cast(Any, target))
                self.assertEqual(user.exp, current_exp)

        self.context.db.main.flush.assert_not_awaited()
        self.add_exp.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
