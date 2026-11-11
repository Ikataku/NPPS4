import unittest
from typing import Any, cast

from npps4.system import core


class ExpMultiplierValidationTests(unittest.TestCase):
    def test_valid_multiplier_returns_exact_delta(self) -> None:
        self.assertEqual(core.validate_exp_multiplier(12, 3, 100), 36)
        self.assertEqual(core.validate_exp_multiplier(123, 1, 100), 123)
        self.assertEqual(core.validate_exp_multiplier(0, 10, 100), 0)

    def test_non_positive_or_non_integer_multiplier_is_rejected(self) -> None:
        for multiplier in (0, -1, True, False, 1.5, "2", None):
            with self.subTest(multiplier=multiplier):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    core.validate_exp_multiplier(10, cast(Any, multiplier), 100)

    def test_invalid_base_exp_is_rejected(self) -> None:
        for base_exp in (-1, True, False, 1.5, "10", None):
            with self.subTest(base_exp=base_exp):
                with self.assertRaises(ValueError):
                    core.validate_exp_multiplier(cast(Any, base_exp), 2, 100)

    def test_resulting_exp_must_fit_sqlite_signed_64_bit_integer(self) -> None:
        maximum = core.MAX_SQLITE_INT
        self.assertEqual(core.validate_exp_multiplier(1, maximum - 10, 10), maximum - 10)
        with self.assertRaisesRegex(ValueError, "SQLite signed 64-bit"):
            core.validate_exp_multiplier(1, maximum - 9, 10)

    def test_current_exp_is_validated_even_for_zero_base_exp(self) -> None:
        for current_exp in (-1, True, core.MAX_SQLITE_INT + 1):
            with self.subTest(current_exp=current_exp):
                with self.assertRaisesRegex(ValueError, "current EXP"):
                    core.validate_exp_multiplier(0, 2, current_exp)




class ExpStateValidationTests(unittest.TestCase):
    def test_valid_rank_and_cumulative_exp_boundaries(self) -> None:
        first_rank_ceiling = core.get_next_exp_cumulative(1)
        self.assertEqual(core.validate_exp_state(1, 0), 0)
        self.assertEqual(core.validate_exp_state(1, first_rank_ceiling - 1), first_rank_ceiling - 1)
        self.assertEqual(core.validate_exp_state(2, first_rank_ceiling), first_rank_ceiling)

    def test_invalid_level_is_rejected(self) -> None:
        for level in (0, -1, True, False, 1.5, "1", None):
            with self.subTest(level=level):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    core.validate_exp_state(cast(Any, level), 0)

    def test_invalid_or_inconsistent_exp_is_rejected(self) -> None:
        first_rank_ceiling = core.get_next_exp_cumulative(1)
        invalid_states = (
            (1, -1),
            (1, True),
            (1, core.MAX_SQLITE_INT + 1),
            (1, first_rank_ceiling),
            (2, first_rank_ceiling - 1),
        )
        for level, current_exp in invalid_states:
            with self.subTest(level=level, current_exp=current_exp):
                with self.assertRaises(ValueError):
                    core.validate_exp_state(level, cast(Any, current_exp))


if __name__ == "__main__":
    unittest.main()
