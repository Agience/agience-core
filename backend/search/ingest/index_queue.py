"""Asynchronous indexing queue for unified search pipelines.

Provides a lightweight in-process worker pool that accepts indexing callables and
executes them concurrently on background threads. This keeps API handlers responsive
while OpenSearch finishes index refreshes, and exposes simple status metrics so the UI
can surface pending work to users if needed.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class IndexTask:
    """Callable payload queued for background execution."""

    action: Callable[[], bool]
    description: str = ""
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class IndexQueue:
    """Thread pool for concurrent search indexing operations."""

    def __init__(self, max_workers: int = 4) -> None:
        self._queue: "queue.Queue[IndexTask]" = queue.Queue()
        self._executor: Optional[ThreadPoolExecutor] = None
        self._coordinator: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._max_workers = max_workers

        self._pending_per_tenant: Dict[str, int] = defaultdict(int)
        self._total_enqueued = 0
        self._total_processed = 0
        self._total_failed = 0

    # --- lifecycle -----------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._executor and self._coordinator and self._coordinator.is_alive():
                return
            self._stop_event.clear()
            self._executor = ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="IndexWorker")
            self._coordinator = threading.Thread(target=self._coordinator_loop, daemon=True)
            self._coordinator.start()
            logger.info(f"IndexQueue worker pool started with {self._max_workers} threads")

    def stop(self, *, drain: bool = True, timeout: float = 5.0) -> None:
        if drain:
            self.flush(timeout=timeout)
        self._stop_event.set()
        
        executor = None
        coordinator = None
        with self._lock:
            executor = self._executor
            coordinator = self._coordinator
            self._executor = None
            self._coordinator = None
        
        if coordinator:
            coordinator.join(timeout=timeout)
            if coordinator.is_alive():
                logger.warning("IndexQueue coordinator did not stop within timeout")
        
        if executor:
            executor.shutdown(wait=True, cancel_futures=not drain)
        
        logger.info("IndexQueue worker pool stopped")

    def is_running(self) -> bool:
        with self._lock:
            return bool(self._executor and self._coordinator and self._coordinator.is_alive())

    # --- enqueue -------------------------------------------------------
    def enqueue(self, task: IndexTask) -> None:
        if task.tenant_id:
            with self._lock:
                self._pending_per_tenant[task.tenant_id] += 1
        with self._lock:
            self._total_enqueued += 1
        self._queue.put(task)
        logger.debug(f"Enqueued task: {task.description} (queue size: {self._queue.qsize()})")

    # --- status --------------------------------------------------------
    def get_status(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        with self._lock:
            pending_total = self._queue.qsize()
            status = {
                "pending_total": pending_total,
                "total_enqueued": self._total_enqueued,
                "total_processed": self._total_processed,
                "total_failed": self._total_failed,
                "worker_alive": self.is_running(),
            }
            if tenant_id:
                status["pending_for_tenant"] = self._pending_per_tenant.get(tenant_id, 0)
            else:
                status["pending_per_tenant"] = dict(self._pending_per_tenant)
            return status

    def flush(self, timeout: float = 5.0) -> None:
        """Block until the queue is empty or the timeout elapses."""
        deadline = time.time() + timeout
        while True:
            if self._queue.empty():
                return
            if time.time() >= deadline:
                logger.warning("IndexQueue flush timed out with %s items pending", self._queue.qsize())
                return
            time.sleep(0.05)

    # --- coordinator loop ----------------------------------------------
    def _coordinator_loop(self) -> None:
        """Coordinator thread that dispatches tasks to worker pool.
        
        Aggressively drains queue and submits all pending tasks to executor
        to minimize latency between enqueue and execution start.
        """
        futures = []
        while not self._stop_event.is_set():
            # Drain completed futures to prevent memory buildup
            futures = [f for f in futures if not f.done()]
            
            # Drain ALL available tasks from queue at once (non-blocking)
            tasks_to_submit = []
            try:
                # Get first task (blocking with timeout)
                task = self._queue.get(timeout=0.2)
                tasks_to_submit.append(task)
                
                # Then drain any additional tasks that are ready (non-blocking)
                while not self._queue.empty():
                    try:
                        task = self._queue.get_nowait()
                        tasks_to_submit.append(task)
                    except queue.Empty:
                        break
            except queue.Empty:
                continue

            # Submit all tasks to thread pool (this should be fast with unbounded queue)
            if self._executor:
                for task in tasks_to_submit:
                    try:
                        future = self._executor.submit(self._execute_task, task)
                        futures.append(future)
                    except Exception as e:
                        logger.error(f"Failed to submit task to executor: {e}")
                        self._queue.task_done()
            else:
                logger.warning("Executor not available, skipping tasks")
                for _ in tasks_to_submit:
                    self._queue.task_done()

    def _execute_task(self, task: IndexTask) -> None:
        """Execute a single indexing task (runs in worker thread)."""
        import time
        from datetime import datetime, timezone
        start_time = time.time()
        logger.debug(f"[{datetime.now(timezone.utc).isoformat()}] 🏁 Starting task: {task.description}")
        try:
            task.action()
            with self._lock:
                self._total_processed += 1
            elapsed = time.time() - start_time
            logger.debug(f" Task completed in {elapsed:.2f}s: {task.description}")
        except Exception:  # pragma: no cover - logged for observability
            with self._lock:
                self._total_failed += 1
            elapsed = time.time() - start_time
            logger.exception(f" Task failed after {elapsed:.2f}s: {task.description or task.action}")
        finally:
            if task.tenant_id:
                with self._lock:
                    remaining = self._pending_per_tenant.get(task.tenant_id, 0)
                    self._pending_per_tenant[task.tenant_id] = max(0, remaining - 1)
            self._queue.task_done()


# Global singleton used by API process
_index_queue: Optional[IndexQueue] = None


def _get_queue() -> IndexQueue:
    """Lazy initialization of index queue with config."""
    global _index_queue
    if _index_queue is None:
        from core import config
        _index_queue = IndexQueue(max_workers=config.INDEX_QUEUE_MAX_WORKERS)
    return _index_queue


def start_worker() -> None:
    _get_queue().start()


def stop_worker(*, drain: bool = True, timeout: float = 5.0) -> None:
    _get_queue().stop(drain=drain, timeout=timeout)


def enqueue(action: Callable[[], bool], *, description: str = "", tenant_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
    queue = _get_queue()
    if not queue.is_running():
        raise RuntimeError(f"IndexQueue worker not running - cannot enqueue task: {description}")
    task = IndexTask(action=action, description=description, tenant_id=tenant_id, metadata=metadata or {})
    queue.enqueue(task)
    # Return immediately - task will be processed asynchronously in background threads


def flush(timeout: float = 5.0) -> None:
    _get_queue().flush(timeout=timeout)


def get_status(tenant_id: Optional[str] = None) -> Dict[str, Any]:
    return _get_queue().get_status(tenant_id=tenant_id)


def is_running() -> bool:
    return _get_queue().is_running()
