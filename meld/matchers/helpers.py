
import logging
import multiprocessing
import queue
import time

from gi.repository import GLib

from meld.matchers import myers

log = logging.getLogger(__name__)


class MatcherWorker(multiprocessing.Process):

    END_TASK = -1

    matcher_class = myers.InlineMyersSequenceMatcher

    def __init__(self, tasks, results):
        super().__init__()
        self.tasks = tasks
        self.results = results
        self.daemon = True

    def run(self):
        while True:
            task_id, (text1, textn) = self.tasks.get()
            if task_id == self.END_TASK:
                break

            try:
                matcher = self.matcher_class(None, text1, textn)
                self.results.put((task_id, matcher.get_opcodes()))
            except Exception as e:
                log.error("Exception while running diff: %s", e)
            time.sleep(0)


class CachedSequenceMatcher:
    """Simple class for caching diff results, with LRU-based eviction

    Results from the SequenceMatcher are cached and timestamped, and
    subsequently evicted based on least-recent generation/usage. The LRU-based
    eviction is overly simplistic, but is okay for our usage pattern.
    """

    TASK_GRACE_PERIOD = 1

    def __init__(self, scheduler):
        """Create a new caching sequence matcher

        :param scheduler: a `meld.task.SchedulerBase` used to schedule
            sequence comparison result checks
        """
        self.scheduler = scheduler
        self.cache = {}
        self.tasks = multiprocessing.Queue()
        self.tasks.cancel_join_thread()
        # Limiting the result queue here has the effect of giving us
        # much better interactivity. Without this limit, the
        # result-checker tends to get starved and all highlights get
        # delayed until we're almost completely finished.
        self.results = multiprocessing.Queue(5)
        self.results.cancel_join_thread()
        self.thread = MatcherWorker(self.tasks, self.results)
        self.task_id = 1
        self.queued_matches = {}
        GLib.idle_add(self.thread.start)

    def stop(self) -> None:
        self.tasks.put((MatcherWorker.END_TASK, ('', '')))
        if self.thread.is_alive():
            self.thread.join(self.TASK_GRACE_PERIOD)
            if self.thread.exitcode is None:
                self.thread.terminate()
        self.cache = {}
        self.queued_matches = {}

    def match(self, text1, textn, cb):
        texts = (text1, textn)
        try:
            self.cache[texts][1] = time.time()
            opcodes = self.cache[texts][0]
            GLib.idle_add(lambda: cb(opcodes))
        except KeyError:
            GLib.idle_add(lambda: self.enqueue_task(texts, cb))

    def enqueue_task(self, texts, cb):
        if not bool(self.queued_matches):
            self.scheduler.add_task(self.check_results)
        self.queued_matches[self.task_id] = (texts, cb)
        self.tasks.put((self.task_id, texts))
        self.task_id += 1

    def check_results(self):
        try:
            task_id, opcodes = self.results.get(block=True, timeout=0.01)
            texts, cb = self.queued_matches.pop(task_id)
            self.cache[texts] = [opcodes, time.time()]
            GLib.idle_add(lambda: cb(opcodes))
        except queue.Empty:
            pass

        return bool(self.queued_matches)

    def clean(self, size_hint):
        """Clean the cache if necessary

        @param size_hint: the recommended minimum number of cache entries
        """
        if len(self.cache) <= size_hint * 3:
            return
        items = list(self.cache.items())
        items.sort(key=lambda it: it[1][1])
        for item in items[:-size_hint * 2]:
            del self.cache[item[0]]
