from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore, Lock


class BackgroundBusy(RuntimeError):
    pass


class BackgroundWork:
    def __init__(self, workers, queue_limit):
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='assistant')
        self.slots = BoundedSemaphore(queue_limit)
        self.futures = set()
        self.lock = Lock()

    def submit(self, function):
        if not self.slots.acquire(blocking=False):
            raise BackgroundBusy('Background work capacity reached; try later')
        try:
            future = self.executor.submit(function)
        except Exception:
            self.slots.release()
            raise
        with self.lock:
            self.futures.add(future)

        def finished(done):
            self.slots.release()
            with self.lock:
                self.futures.discard(done)
        future.add_done_callback(finished)
        return future

    def close(self):
        self.executor.shutdown(wait=True)
