import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from typing import Any, cast

from npps4.system import core
from npps4.system import user as system_user


class ExpTotalValidationTests(unittest.TestCase):
    def test_valid_absolute_totals(self) -> None:
        for value in (0, 1, 123456789, core.MAX_SQLITE_INT):
            with self.subTest(value=value):
                self.assertEqual(core.validate_exp_total(value), value)

    def test_invalid_absolute_totals_are_rejected(self) -> None:
        for value in (True, False, -1, 1.5, "10", None, core.MAX_SQLITE_INT + 1):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    core.validate_exp_total(cast(Any, value))


class SetExpTotalTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.context = SimpleNamespace(db=SimpleNamespace(main=SimpleNamespace(flush=AsyncMock())))

    def make_user(self, level: int, exp: int):
        return SimpleNamespace(level=level, exp=exp)

    async def test_lowering_within_current_rank_updates_only_exp(self) -> None:
        level = 10
        rank_floor = core.get_next_exp_cumulative(level - 1)
        current_exp = rank_floor + 50
        target_exp = rank_floor + 25
        user = self.make_user(level, current_exp)

        with patch.object(system_user, "add_exp", new_callable=AsyncMock) as add_exp:
            result = await system_user.set_exp_total(self.context, user, target_exp)

        self.assertEqual(user.exp, target_exp)
        self.context.db.main.flush.assert_awaited_once_with()
        add_exp.assert_not_awaited()
        self.assertEqual(result, [system_user.NextLevelInfo(level=level, from_exp=current_exp)])

    async def test_lowering_below_rank_floor_is_rejected_without_mutation(self) -> None:
        level = 10
        rank_floor = core.get_next_exp_cumulative(level - 1)
        current_exp = rank_floor + 25
        user = self.make_user(level, current_exp)

        with patch.object(system_user, "add_exp", new_callable=AsyncMock) as add_exp:
            with self.assertRaisesRegex(ValueError, "rank downgrade"):
                await system_user.set_exp_total(self.context, user, rank_floor - 1)

        self.assertEqual(user.exp, current_exp)
        self.context.db.main.flush.assert_not_awaited()
        add_exp.assert_not_awaited()

    async def test_increasing_absolute_total_reuses_existing_rankup_logic(self) -> None:
        level = 10
        rank_floor = core.get_next_exp_cumulative(level - 1)
        current_exp = rank_floor + 25
        target_exp = core.get_next_exp_cumulative(level) + 50
        user = self.make_user(level, current_exp)
        expected = [system_user.NextLevelInfo(level=level, from_exp=current_exp)]

        with patch.object(system_user, "add_exp", new_callable=AsyncMock, return_value=expected) as add_exp:
            result = await system_user.set_exp_total(self.context, user, target_exp)

        add_exp.assert_awaited_once_with(self.context, user, target_exp - current_exp)
        self.assertIs(result, expected)
        self.assertEqual(user.exp, current_exp)

    async def test_same_absolute_total_is_a_noop(self) -> None:
        level = 10
        current_exp = core.get_next_exp_cumulative(level - 1) + 25
        user = self.make_user(level, current_exp)

        with patch.object(system_user, "add_exp", new_callable=AsyncMock) as add_exp:
            result = await system_user.set_exp_total(self.context, user, current_exp)

        self.assertEqual(user.exp, current_exp)
        self.context.db.main.flush.assert_not_awaited()
        add_exp.assert_not_awaited()
        self.assertEqual(result, [system_user.NextLevelInfo(level=level, from_exp=current_exp)])

    async def test_inconsistent_current_rank_is_rejected(self) -> None:
        level = 10
        user = self.make_user(level, core.get_next_exp_cumulative(level))

        with self.assertRaisesRegex(ValueError, "inconsistent"):
            await system_user.set_exp_total(self.context, user, user.exp)

        self.context.db.main.flush.assert_not_awaited()

    async def test_invalid_total_is_rejected_before_mutation(self) -> None:
        level = 10
        current_exp = core.get_next_exp_cumulative(level - 1) + 25
        user = self.make_user(level, current_exp)

        for target in (True, -1, 1.5, "100", core.MAX_SQLITE_INT + 1):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    await system_user.set_exp_total(self.context, user, cast(Any, target))
                self.assertEqual(user.exp, current_exp)

        self.context.db.main.flush.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
