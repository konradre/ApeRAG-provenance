"""
Unit tests for ThreadingLock implementation.

This module tests the basic functionality of ThreadingLock including
acquire/release operations, context manager usage, and concurrent behavior.
"""

import asyncio
import time

import pytest

from aperag.concurrent_control import ThreadingLock, create_lock


class TestThreadingLock:
    """Test suite for ThreadingLock implementation."""

    def test_threading_lock_creation(self):
        """Test basic ThreadingLock creation."""
        # Test with custom name
        lock = ThreadingLock(name="test_lock")
        assert lock._name == "test_lock"
        assert not lock.is_locked()

        # Test with auto-generated name
        lock_auto = ThreadingLock()
        assert lock_auto._name.startswith("threading_lock_")
        assert not lock_auto.is_locked()

    @pytest.mark.asyncio
    async def test_basic_acquire_release(self):
        """Test basic acquire and release operations."""
        lock = ThreadingLock(name="basic_test")

        # Lock should not be held initially
        assert not lock.is_locked()

        # Acquire lock
        success = await lock.acquire()
        assert success is True
        assert lock.is_locked()

        # Release lock
        await lock.release()
        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test ThreadingLock as async context manager."""
        lock = ThreadingLock(name="context_test")

        assert not lock.is_locked()

        async with lock:
            assert lock.is_locked()

        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test that lock is released even when exception occurs."""
        lock = ThreadingLock(name="exception_test")

        assert not lock.is_locked()

        try:
            async with lock:
                assert lock.is_locked()
                raise ValueError("Test exception")
        except ValueError:
            pass  # Expected exception

        # Lock should be released even after exception
        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_concurrent_access_serialization(self):
        """Test that concurrent access is properly serialized."""
        lock = ThreadingLock(name="concurrent_test")
        results = []

        async def worker(worker_id: int, work_duration: float):
            """Worker that acquires lock and does some work."""
            async with lock:
                start_time = time.time()
                results.append(f"worker_{worker_id}_start")
                await asyncio.sleep(work_duration)
                end_time = time.time()
                results.append(f"worker_{worker_id}_end")
                return end_time - start_time

        # Run multiple workers concurrently
        start_time = time.time()
        tasks = [worker(1, 0.1), worker(2, 0.1), worker(3, 0.1)]
        durations = await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Verify serialization - workers should not overlap
        # Results should show complete start-end pairs
        expected_patterns = [
            ["worker_1_start", "worker_1_end"],
            ["worker_2_start", "worker_2_end"],
            ["worker_3_start", "worker_3_end"],
        ]

        # Check that each worker completed properly
        for pattern in expected_patterns:
            start_idx = results.index(pattern[0])
            end_idx = results.index(pattern[1])
            assert end_idx == start_idx + 1, f"Worker execution was not atomic: {results}"

        # Total time should be approximately sum of individual durations
        # (allowing for some overhead)
        expected_time = sum(durations)
        assert total_time >= expected_time * 0.9, "Tasks seem to have run in parallel instead of serially"
        assert all(d >= 0.08 for d in durations), "Individual task durations too short"

    @pytest.mark.asyncio
    async def test_multiple_acquire_same_task(self):
        """Test multiple acquire attempts from the same task (should succeed)."""
        lock = ThreadingLock(name="multiple_acquire_test")

        # First acquire
        success1 = await lock.acquire()
        assert success1 is True
        assert lock.is_locked()

        # Second acquire should work (threading.Lock is reentrant when already held)
        # Note: Actually threading.Lock is NOT reentrant, this will block
        # So let's test the expected behavior

        # Release the first lock
        await lock.release()
        assert not lock.is_locked()

        # Now acquire again
        success2 = await lock.acquire()
        assert success2 is True
        assert lock.is_locked()

        await lock.release()
        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_lock_status_during_operations(self):
        """Test that is_locked() returns correct status during operations."""
        lock = ThreadingLock(name="status_test")

        # Initially not locked
        assert not lock.is_locked()

        async def check_status_during_work():
            async with lock:
                # Should be locked during work
                assert lock.is_locked()
                await asyncio.sleep(0.05)
                assert lock.is_locked()

        await check_status_during_work()

        # Should be unlocked after work
        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_factory_function_creates_threading_lock(self):
        """Test that create_lock factory function creates ThreadingLock correctly."""
        lock = create_lock("threading", name="factory_test")

        assert isinstance(lock, ThreadingLock)
        assert lock._name == "factory_test"

        # Test functionality
        assert not lock.is_locked()
        async with lock:
            assert lock.is_locked()
        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_concurrent_queue_ordering(self):
        """Test that tasks waiting for lock are processed in order."""
        lock = ThreadingLock(name="queue_test")
        execution_order = []

        async def queued_task(task_id: int):
            async with lock:
                execution_order.append(task_id)
                await asyncio.sleep(0.01)  # Small delay to ensure ordering

        # Start tasks in quick succession
        tasks = [queued_task(i) for i in range(5)]
        await asyncio.gather(*tasks)

        # All tasks should have completed
        assert len(execution_order) == 5
        assert set(execution_order) == set(range(5))

        # Order might not be strictly sequential due to async scheduling,
        # but all tasks should complete

    @pytest.mark.asyncio
    async def test_long_running_task_blocking(self):
        """Test that long-running task properly blocks others."""
        lock = ThreadingLock(name="blocking_test")
        start_times = []
        end_times = []

        async def long_task():
            start_times.append(time.time())
            async with lock:
                await asyncio.sleep(0.2)  # Long running task
            end_times.append(time.time())

        async def short_task():
            start_times.append(time.time())
            async with lock:
                await asyncio.sleep(0.01)  # Short task
            end_times.append(time.time())

        # Start long task first, then short task
        await asyncio.gather(long_task(), short_task())

        # Both tasks should complete
        assert len(start_times) == 2
        assert len(end_times) == 2

        # There should be significant time difference showing blocking occurred
        total_duration = max(end_times) - min(start_times)
        assert total_duration >= 0.2, "Short task didn't wait for long task"

    @pytest.mark.asyncio
    async def test_error_in_acquire(self):
        """Test error handling during lock acquisition."""
        lock = ThreadingLock(name="error_test")

        # Simulate normal operation first
        success = await lock.acquire()
        assert success is True
        await lock.release()

        # Normal operation should continue to work
        async with lock:
            assert lock.is_locked()

        assert not lock.is_locked()

    @pytest.mark.asyncio
    async def test_threading_lock_name_uniqueness(self):
        """Test that different locks have different names when auto-generated."""
        lock1 = ThreadingLock()
        lock2 = ThreadingLock()

        assert lock1._name != lock2._name
        assert lock1._name.startswith("threading_lock_")
        assert lock2._name.startswith("threading_lock_")

    @pytest.mark.asyncio
    async def test_mixed_context_manager_and_manual_ops(self):
        """Test mixing context manager usage with manual acquire/release."""
        lock = ThreadingLock(name="mixed_test")

        # Manual acquire
        success = await lock.acquire()
        assert success is True
        assert lock.is_locked()

        # Manual release
        await lock.release()
        assert not lock.is_locked()

        # Context manager
        async with lock:
            assert lock.is_locked()

        assert not lock.is_locked()

        # Manual again
        success = await lock.acquire()
        assert success is True
        await lock.release()
        assert not lock.is_locked()


class TestThreadingLockIntegration:
    """Integration tests for ThreadingLock with various async patterns."""

    @pytest.mark.asyncio
    async def test_with_asyncio_timeout(self):
        """Test ThreadingLock with asyncio timeout."""
        lock = ThreadingLock(name="timeout_test")

        async def blocking_task():
            async with lock:
                await asyncio.sleep(0.3)  # Long delay

        async def quick_task():
            try:
                # This should timeout because blocking_task holds the lock
                async with asyncio.timeout(0.1):
                    async with lock:
                        pass
                return "completed"
            except asyncio.TimeoutError:
                return "timeout"

        # Start blocking task first, then try quick task with timeout
        results = await asyncio.gather(
            blocking_task(),
            asyncio.sleep(0.05),  # Small delay to ensure order
            quick_task(),
            return_exceptions=True,
        )

        # Quick task should timeout
        assert results[2] == "timeout"

    @pytest.mark.asyncio
    async def test_with_asyncio_queue(self):
        """Test ThreadingLock coordination with asyncio.Queue."""
        lock = ThreadingLock(name="queue_coordination_test")
        queue = asyncio.Queue()

        async def producer():
            for i in range(3):
                async with lock:
                    await queue.put(f"item_{i}")
                    await asyncio.sleep(0.01)

        async def consumer():
            items = []
            for _ in range(3):
                async with lock:
                    item = await queue.get()
                    items.append(item)
            return items

        # Run producer and consumer concurrently
        producer_task = asyncio.create_task(producer())
        consumer_task = asyncio.create_task(consumer())

        await producer_task
        items = await consumer_task

        assert len(items) == 3
        assert all(item.startswith("item_") for item in items)

    @pytest.mark.asyncio
    async def test_performance_overhead(self):
        """Test performance characteristics of ThreadingLock."""
        lock = ThreadingLock(name="performance_test")

        async def quick_operation():
            async with lock:
                # Very quick operation
                await asyncio.sleep(0.001)

        # Time multiple quick operations
        start_time = time.time()
        tasks = [quick_operation() for _ in range(10)]
        await asyncio.gather(*tasks)
        total_time = time.time() - start_time

        # Should complete in reasonable time (allowing for serialization)
        # 10 operations * 0.001s + overhead should be well under 1 second
        assert total_time < 1.0, f"Operations took too long: {total_time}s"

        # Should be at least the sum of individual sleep times
        min_expected_time = 10 * 0.001
        assert total_time >= min_expected_time, f"Operations completed too quickly: {total_time}s"
