import unittest
from typing import Any, cast

from npps4.system import core


class ExpDeltaValidationTests(unittest.TestCase):
    def test_non_negative_integer_values_are_accepted(self) -> None:
        for value in (0, 1, 123456789):
            with self.subTest(value=value):
                self.assertEqual(core.validate_exp_delta(value), value)

    def test_negative_delta_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "non-negative integer"):
            core.validate_exp_delta(-1)

    def test_bool_float_string_and_none_are_rejected(self) -> None:
        for value in (True, False, 1.5, "10", None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-negative integer"):
                    core.validate_exp_delta(cast(Any, value))


if __name__ == "__main__":
    unittest.main()
