"""Timestamped progress logging for long-running extractions.

Injected into the extraction methods so that long-running loops emit
periodic lines like:

    [progress] 21:05:30 lei:sim-edge: 12,345,678/381,522,016,125 (0.003%) ETA 1234.5h rate=6,860/s rss=45.2GB elapsed=1800s

The measured rate / ETA / RSS trend backs the feasibility decisions for
the large-scale runs.
"""

import resource
import sys
import time


class Progress:
    def __init__(self, label, total=None, interval_sec=30):
        self.label = label
        self.total = total
        self.interval = interval_sec
        self.count = 0
        self.start = time.time()
        self.last_emit = self.start

    def tick(self, n=1):
        self.count += n
        now = time.time()
        if now - self.last_emit >= self.interval:
            self._emit(now)
            self.last_emit = now

    def done(self):
        self._emit(time.time())

    def _emit(self, now):
        elapsed = now - self.start
        rate = self.count / elapsed if elapsed > 0 else 0.0
        # ru_maxrss is bytes on macOS, kilobytes on Linux
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_gb = rss / 2**30 if sys.platform == "darwin" else rss / 2**20
        msg = f"[progress] {time.strftime('%H:%M:%S')} {self.label}: {self.count:,}"
        if self.total:
            pct = self.count / self.total * 100
            if rate > 0:
                eta_h = (self.total - self.count) / rate / 3600
                msg += f"/{self.total:,} ({pct:.3f}%) ETA {eta_h:,.1f}h"
            else:
                msg += f"/{self.total:,} ({pct:.3f}%)"
        msg += f" rate={rate:,.0f}/s rss={rss_gb:.1f}GB elapsed={elapsed:,.0f}s"
        print(msg, flush=True)
