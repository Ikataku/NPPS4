import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Any
from unittest.mock import AsyncMock

SESSION_PATH = Path(__file__).resolve().parents[1] / "npps4" / "idol" / "session.py"


class _FakeContext:
    async def __aenter__(self) -> "_FakeContext":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False


class _FailingContext:
    async def __aenter__(self) -> "_FailingContext":
        raise RuntimeError("context entry failed")

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False


class SessionCleanupGuardTests(unittest.IsolatedAsyncioTestCase):
    namespace: dict[str, Any]

    @classmethod
    def setUpClass(cls) -> None:
        tree = ast.parse(SESSION_PATH.read_text(encoding="utf-8"))
        function = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.AsyncFunctionDef) and node.name == "try_cleanup_tokens"
            ),
            None,
        )
        if function is None:
            raise RuntimeError("npps4.idol.session.try_cleanup_tokens is missing")

        module = ast.Module(body=[function], type_ignores=[])
        namespace: dict[str, Any] = {}
        exec(compile(ast.fix_missing_locations(module), str(SESSION_PATH), "exec"), namespace)
        cls.namespace = namespace

    def setUp(self) -> None:
        self.namespace["_currently_cleaning"] = False
        self.namespace["asyncio"] = SimpleNamespace(sleep=AsyncMock())
        self.namespace["BasicSchoolIdolContext"] = _FakeContext
        self.namespace["cleanup_session_table"] = AsyncMock()

    async def test_guard_is_released_after_database_cleanup_failure(self) -> None:
        cleanup = self.namespace["cleanup_session_table"]
        assert isinstance(cleanup, AsyncMock)
        cleanup.side_effect = RuntimeError("database cleanup failed")

        with self.assertRaisesRegex(RuntimeError, "database cleanup failed"):
            await self.namespace["try_cleanup_tokens"]()

        self.assertFalse(self.namespace["_currently_cleaning"])
        cleanup.assert_awaited_once()

    async def test_guard_is_released_after_cancellation_during_delay(self) -> None:
        async def cancel_delay(_delay: float) -> None:
            raise asyncio.CancelledError

        asyncio_stub = self.namespace["asyncio"]
        assert isinstance(asyncio_stub, SimpleNamespace)
        asyncio_stub.sleep = AsyncMock(side_effect=cancel_delay)

        with self.assertRaises(asyncio.CancelledError):
            await self.namespace["try_cleanup_tokens"]()

        self.assertFalse(self.namespace["_currently_cleaning"])

    async def test_guard_is_released_when_context_entry_fails(self) -> None:
        self.namespace["BasicSchoolIdolContext"] = _FailingContext
        cleanup = self.namespace["cleanup_session_table"]
        assert isinstance(cleanup, AsyncMock)

        with self.assertRaisesRegex(RuntimeError, "context entry failed"):
            await self.namespace["try_cleanup_tokens"]()

        self.assertFalse(self.namespace["_currently_cleaning"])
        cleanup.assert_not_awaited()

    async def test_cleanup_can_retry_after_previous_failure(self) -> None:
        cleanup = self.namespace["cleanup_session_table"]
        assert isinstance(cleanup, AsyncMock)
        cleanup.side_effect = [RuntimeError("first attempt failed"), None]

        with self.assertRaisesRegex(RuntimeError, "first attempt failed"):
            await self.namespace["try_cleanup_tokens"]()
        await self.namespace["try_cleanup_tokens"]()

        self.assertFalse(self.namespace["_currently_cleaning"])
        self.assertEqual(cleanup.await_count, 2)

    async def test_duplicate_cleanup_request_is_skipped(self) -> None:
        self.namespace["_currently_cleaning"] = True
        asyncio_stub = self.namespace["asyncio"]
        assert isinstance(asyncio_stub, SimpleNamespace)
        delay = asyncio_stub.sleep
        cleanup = self.namespace["cleanup_session_table"]
        assert isinstance(delay, AsyncMock)
        assert isinstance(cleanup, AsyncMock)

        await self.namespace["try_cleanup_tokens"]()

        delay.assert_not_awaited()
        cleanup.assert_not_awaited()
        self.assertTrue(self.namespace["_currently_cleaning"])


if __name__ == "__main__":
    unittest.main()
