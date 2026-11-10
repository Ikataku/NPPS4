import unittest
from typing import Any, cast

from npps4.system import core


class ExpDeltaValidationTests(unittest.TestCase):
    def test_non_negative_integer_values_are_accepted(self) -> None:
        for value in (0, 1, 123456789):
            with self.subTest(value=value):
                self.assertEqual(core.validate_exp_delta(value, 10), value)

    def test_negative_delta_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            core.validate_exp_delta(-1, 10)

    def test_bool_float_string_and_none_deltas_are_rejected(self) -> None:
        for value in (True, False, 1.5, "10", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-negative integer"):
                    core.validate_exp_delta(cast(Any, value), 10)

    def test_resulting_exp_must_fit_sqlite_signed_64_bit_integer(self) -> None:
        maximum = core.MAX_SQLITE_INT
        self.assertEqual(core.validate_exp_delta(maximum - 1, 1), maximum - 1)
        self.assertEqual(core.validate_exp_delta(0, maximum), 0)
        for delta, current in ((2, maximum - 1), (maximum + 1, 0)):
            with self.subTest(delta=delta, current=current):
                with self.assertRaisesRegex(ValueError, "SQLite signed 64-bit"):
                    core.validate_exp_delta(delta, current)

    def test_invalid_current_exp_is_rejected(self) -> None:
        maximum = core.MAX_SQLITE_INT
        for current in (True, False, -1, maximum + 1, 1.5, "10", None):
            with self.subTest(current=current):
                with self.assertRaisesRegex(ValueError, "current EXP"):
                    core.validate_exp_delta(0, cast(Any, current))


if __name__ == "__main__":
    unittest.main()
