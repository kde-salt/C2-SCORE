"""Extraction runner: execute one schema extraction method on one database,
under a wall-clock timeout and an RSS memory limit.

Used both for the dbpedia feasibility measurements (short observation
windows, extrapolate ETA from the [progress] log lines) and for the real
dblp / dbpedia extraction runs.

Usage (from the repository root, with .venv activated):
    python -m schema_extraction.run_extraction --db dbpedia --method lei \
        --timeout 21600 --mem-limit-gb 100

Outcome per run is appended to experiment/complex_pgs_test/results/extraction_runs.csv
and the child's full output goes to schema_extraction/logs/.
"""

import os
import sys
import argparse
import csv
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

from experiment.common.config import NEO4J_URI as BOLT_URI, NEO4J_USER as USER_NAME, NEO4J_PASSWORD as PASSWORD

# Method parameters, copied from schema_extraction/main.py L46-54.
LABEL_WEIGHT = 1
PROP_WEIGHT = 0
TOPOLOGY_WEIGHT = 0
THETA = 0.5
SAMPLING_RATE = 80
PG_HIVE_CLUSTERING = "LSH"

METHODS = ("lei", "schemi", "gmmschema", "pg-hive")
LOG_DIR = Path("schema_extraction/logs")
RUNS_CSV = Path("experiment/complex_pgs_test/results/extraction_runs.csv")
POLL_SEC = 30

# Lines that mean the JVM ran out of heap inside the budget (the runner's own
# RSS limit was never reached, so only the log can tell us).
OOM_MARKERS = ("OutOfMemoryError", "Java heap space", "GC overhead limit")
# Signals that come from outside the runner (an operator, a session teardown),
# as opposed to the kernel's SIGKILL under memory pressure.
EXTERNAL_SIGNALS = (-signal.SIGTERM, -signal.SIGINT, -signal.SIGHUP)
# The dense nested ladder, smallest first.  G(ds) ⊆ G(dm2) ⊆ G(dl2) holds by
# construction.
NESTED_LADDER = ("dbpedia-ds", "dbpedia-dm2", "dbpedia-dl2")


def run_child(db_name, method):
    if method == "lei":
        from schema_extraction.lei.lei import main as lei
        lei(BOLT_URI, USER_NAME, PASSWORD, db_name,
            LABEL_WEIGHT, PROP_WEIGHT, TOPOLOGY_WEIGHT, THETA)
    elif method == "schemi":
        from schema_extraction.schemi.schemi import main as schemi
        schemi(BOLT_URI, USER_NAME, PASSWORD, db_name)
    elif method == "gmmschema":
        from schema_extraction.gmmschema.cluster_script import main as gmmschema
        mid_table = f"schema_extraction/gmmschema/data-{db_name}.csv"
        gmmschema(BOLT_URI, USER_NAME, PASSWORD, db_name,
                  mid_table, SAMPLING_RATE)
    elif method == "pg-hive":
        from schema_extraction.pg_hive.pg_hive import main as pg_hive
        pg_hive(BOLT_URI, USER_NAME, PASSWORD, db_name,
                PG_HIVE_CLUSTERING, extract=True)
    else:
        raise ValueError(f"unknown method: {method}")


def group_rss_gb(pgid):
    """Total RSS of the child's process group in GiB (macOS ps: RSS in KiB)."""
    try:
        out = subprocess.run(["ps", "-o", "rss=", "-g", str(pgid)],
                             capture_output=True, text=True, timeout=10).stdout
    except subprocess.TimeoutExpired:
        return 0.0
    return sum(int(x) for x in out.split() if x.isdigit()) / 2**20


def kill_group(pgid):
    # PermissionError: macOS raises EPERM instead of ESRCH when the group
    # only contains members we can no longer signal (observed after the
    # child's own workers already exited).
    for sig, grace in ((signal.SIGTERM, 30), (signal.SIGKILL, 0)):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        if grace:
            time.sleep(grace)


def cleanup(db_name):
    for f in ("all_nodes.json", "all_edges.json",
              f"schema_extraction/gmmschema/data-{db_name}.csv"):
        Path(f).unlink(missing_ok=True)


def append_run_row(row):
    RUNS_CSV.parent.mkdir(parents=True, exist_ok=True)
    new_file = not RUNS_CSV.exists()
    with open(RUNS_CSV, "a", newline="") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(["timestamp", "db", "method", "status",
                             "wall_sec", "peak_rss_gb", "timeout_sec",
                             "mem_limit_gb", "heap_gb", "failure_kind",
                             "log_path"])
        writer.writerow(row)
        f.flush()
        os.fsync(f.fileno())


def heap_gb(env, method):
    """JVM heap actually handed to the child, in GiB. Only pg-hive forks a JVM;
    the other methods run in-process, so the column stays empty for them."""
    if method != "pg-hive":
        return ""
    raw = env.get("PGHIVE_XMX", "").strip()
    if not raw:
        return ""
    unit, digits = raw[-1].upper(), raw[:-1]
    scale = {"G": 1, "M": 1 / 1024, "K": 1 / 2**20}.get(unit)
    if scale is None:                       # plain byte count
        unit, digits, scale = "", raw, 1 / 2**30
    try:
        return f"{float(digits) * scale:g}"
    except ValueError:
        return raw


def log_has(log_path, markers):
    try:
        with open(log_path, errors="replace") as f:
            return any(any(m in line for m in markers) for line in f)
    except OSError:
        return False


def classify_failure(status, returncode, log_path):
    """timeout / memory / invalid, per the common-budget protocol.

    'memory' covers both hitting the runner's RSS limit and dying *inside* the
    budget because the kernel or the JVM ran out — those are different events
    and the peak_rss_gb column is what tells them apart, so do not read this
    column as "the limit was reached".
    """
    if status == "success":
        return ""
    if status == "timeout":
        return "timeout"
    if status == "mem-limit":
        return "memory"
    if returncode == -signal.SIGKILL or log_has(log_path, OOM_MARKERS):
        return "memory"
    if returncode in EXTERNAL_SIGNALS:
        return "invalid"
    print(f"[runner] WARNING: failure_kind undetermined "
          f"(returncode={returncode}) — read {log_path} and record it by hand",
          flush=True)
    return ""


def last_run(db_name, method):
    """Most recent recorded row for <db> x <method>, as a dict, or None."""
    try:
        with open(RUNS_CSV, newline="") as f:
            rows = [r for r in csv.DictReader(f)
                    if r["db"] == db_name and r["method"] == method]
    except OSError:
        return None
    return rows[-1] if rows else None


def implied_failure(db_name, method):
    """A failure one rung down that already settles this cell, or None.

    Every rung of NESTED_LADDER contains the one below it, and every cost
    driver of these methods -- signatures, property keys, edges -- is strictly
    larger on the larger graph.  A method that exhausts a resource on a rung
    therefore cannot finish on the rung above, so re-running it only spends
    the budget to watch the same failure.

    Two things are deliberately *not* inferred from:
      - failures we could not attribute to a resource ('invalid', or a kind we
        could not determine).  Only exhaustion inside the budget is monotone;
        an operator kill or a crash says nothing about the larger graph.
      - anything at all, once a *larger* rung is on record as a success.  That
        would contradict the inference outright, so the smaller failure was
        circumstantial and the cell is worth running.
    """
    if db_name not in NESTED_LADDER:
        return None
    i = NESTED_LADDER.index(db_name)
    for larger in NESTED_LADDER[i + 1:]:
        row = last_run(larger, method)
        if row and row["status"] == "success":
            return None
    for smaller in reversed(NESTED_LADDER[:i]):
        row = last_run(smaller, method)
        if row and row.get("failure_kind") in ("timeout", "memory"):
            return row
    return None


def run_supervised(db_name, method, timeout_sec, mem_limit_gb):
    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    evidence = implied_failure(db_name, method)
    if evidence is not None:
        # Not a measurement: wall_sec and peak_rss_gb stay empty on purpose, and
        # log_path points at the smaller run this was inferred from.
        append_run_row([ts, db_name, method, "implied-failure", "", "",
                        timeout_sec, mem_limit_gb,
                        heap_gb(os.environ, method),
                        evidence["failure_kind"], evidence["log_path"]])
        print(f"[runner] {db_name} x {method}: implied-failure — "
              f"{evidence['db']} x {method} already ended in "
              f"{evidence['status']} ({evidence['failure_kind']}) and "
              f"{evidence['db']} is contained in {db_name}. Not running it.",
              flush=True)
        return "implied-failure"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"{db_name}-{method}-{ts}.log"

    env = os.environ | {"PYTHONHASHSEED": "0"}
    if method == "pg-hive":
        # Heap of the forked Spark JVM (build.sbt javaOptions), not sbt's own.
        env.setdefault("PGHIVE_XMX", "80G")

    print(f"[runner] {db_name} x {method}: timeout={timeout_sec}s "
          f"mem_limit={mem_limit_gb}GB log={log_path}", flush=True)
    start = time.time()
    with open(log_path, "w") as log:
        proc = subprocess.Popen(
            [sys.executable, "-m", "schema_extraction.run_extraction",
             "--child", "--db", db_name, "--method", method],
            stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, env=env)
        pgid = os.getpgid(proc.pid)

        status = None
        peak_rss = 0.0
        returncode = None
        while status is None:
            try:
                proc.wait(timeout=POLL_SEC)
                returncode = proc.returncode
                status = "success" if proc.returncode == 0 else "failed"
                # Negative returncode = killed by that signal (e.g. -9 means
                # SIGKILL from outside — typically kernel memory pressure).
                print(f"[runner] child exited with returncode="
                      f"{proc.returncode}", flush=True)
                break
            except subprocess.TimeoutExpired:
                pass
            rss = group_rss_gb(pgid)
            peak_rss = max(peak_rss, rss)
            elapsed = time.time() - start
            if rss > mem_limit_gb:
                print(f"[runner] RSS {rss:.1f}GB > limit {mem_limit_gb}GB "
                      f"at {elapsed:,.0f}s — killing process group", flush=True)
                kill_group(pgid)
                status = "mem-limit"
            elif elapsed > timeout_sec:
                print(f"[runner] timeout {timeout_sec}s reached — "
                      "killing process group", flush=True)
                kill_group(pgid)
                status = "timeout"

    wall = time.time() - start
    cleanup(db_name)
    failure_kind = classify_failure(status, returncode, log_path)
    append_run_row([ts, db_name, method, status, f"{wall:.0f}",
                    f"{peak_rss:.1f}", timeout_sec, mem_limit_gb,
                    heap_gb(env, method), failure_kind, log_path])
    print(f"[runner] {db_name} x {method}: {status} "
          f"(wall={wall:,.0f}s peak_rss={peak_rss:.1f}GB"
          + (f" failure_kind={failure_kind}" if failure_kind else "") + ")",
          flush=True)
    return status


def main():
    parser = argparse.ArgumentParser(description="Schema extraction runner")
    parser.add_argument("--db", required=True)
    parser.add_argument("--method", required=True, choices=METHODS)
    parser.add_argument("--timeout", type=int, default=21600,
                        help="wall-clock limit in seconds (default 6h)")
    parser.add_argument("--mem-limit-gb", type=float, default=100.0)
    parser.add_argument("--child", action="store_true",
                        help="internal: run the method in-process")
    args = parser.parse_args()

    if args.child:
        run_child(args.db, args.method)
    else:
        status = run_supervised(args.db, args.method,
                                args.timeout, args.mem_limit_gb)
        sys.exit(0 if status == "success" else 1)


if __name__ == "__main__":
    # Hash-seed pinning as in schema_extraction.main, but inside the
    # __main__ guard: worker processes re-importing this module must not
    # trigger the execv, or each worker would restart the full run.
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.environ["PYTHONHASHSEED"] = "0"
        os.execv(sys.executable, [sys.executable, "-m",
                                  "schema_extraction.run_extraction"] + sys.argv[1:])
    main()
