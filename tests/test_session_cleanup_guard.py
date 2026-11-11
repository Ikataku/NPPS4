import asyncio
import unittest
from types import TracebackType
from unittest.mock import AsyncMock, patch

from npps4.idol import session


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
    def setUp(self) -> None:
        session._currently_cleaning = False

    def tearDown(self) -> None:
        session._currently_cleaning = False

    async def test_guard_is_released_after_database_cleanup_failure(self) -> None:
        cleanup = AsyncMock(side_effect=RuntimeError("database cleanup failed"))
        with (
            patch.object(session.asyncio, "sleep", new=AsyncMock()),
            patch.object(session, "BasicSchoolIdolContext", _FakeContext),
            patch.object(session, "cleanup_session_table", new=cleanup),
        ):
            with self.assertRaisesRegex(RuntimeError, "database cleanup failed"):
                await session.try_cleanup_tokens()

        self.assertFalse(session._currently_cleaning)
        cleanup.assert_awaited_once()

    async def test_guard_is_released_after_cancellation_during_delay(self) -> None:
        async def cancel_delay(_delay: float) -> None:
            raise asyncio.CancelledError

        with patch.object(session.asyncio, "sleep", side_effect=cancel_delay):
            with self.assertRaises(asyncio.CancelledError):
                await session.try_cleanup_tokens()

        self.assertFalse(session._currently_cleaning)

    async def test_guard_is_released_when_context_entry_fails(self) -> None:
        cleanup = AsyncMock()
        with (
            patch.object(session.asyncio, "sleep", new=AsyncMock()),
            patch.object(session, "BasicSchoolIdolContext", _FailingContext),
            patch.object(session, "cleanup_session_table", new=cleanup),
        ):
            with self.assertRaisesRegex(RuntimeError, "context entry failed"):
                await session.try_cleanup_tokens()

        self.assertFalse(session._currently_cleaning)
        cleanup.assert_not_awaited()

    async def test_cleanup_can_retry_after_previous_failure(self) -> None:
        cleanup = AsyncMock(side_effect=[RuntimeError("first attempt failed"), None])
        with (
            patch.object(session.asyncio, "sleep", new=AsyncMock()),
            patch.object(session, "BasicSchoolIdolContext", _FakeContext),
            patch.object(session, "cleanup_session_table", new=cleanup),
        ):
            with self.assertRaisesRegex(RuntimeError, "first attempt failed"):
                await session.try_cleanup_tokens()
            await session.try_cleanup_tokens()

        self.assertFalse(session._currently_cleaning)
        self.assertEqual(cleanup.await_count, 2)

    async def test_duplicate_cleanup_request_is_skipped(self) -> None:
        session._currently_cleaning = True
        delay = AsyncMock()
        cleanup = AsyncMock()
        with (
            patch.object(session.asyncio, "sleep", new=delay),
            patch.object(session, "BasicSchoolIdolContext", _FakeContext),
            patch.object(session, "cleanup_session_table", new=cleanup),
        ):
            await session.try_cleanup_tokens()

        delay.assert_not_awaited()
        cleanup.assert_not_awaited()
        self.assertTrue(session._currently_cleaning)


if __name__ == "__main__":
    unittest.main()
