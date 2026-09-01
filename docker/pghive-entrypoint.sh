#!/usr/bin/env bash
#
# PG-HIVE runs share the sbt build output and the fixed-path output txt
# (schemadiscovery/pg_schema_output_strict.txt), so two concurrent runs
# silently corrupt each other's results. The lock file lives on the
# pghive-target volume, which makes this guard effective across containers.

set -euo pipefail

# Hadoop (pulled in by Spark) logs in through UnixLoginModule, which fails with
# a NullPointerException when the running uid has no passwd entry -- the case
# whenever compose maps the container to the host's uid. Add one on the fly.
if ! getent passwd "$(id -u)" >/dev/null 2>&1; then
  echo "runner:x:$(id -u):$(id -g):runner:/home/runner:/bin/bash" >> /etc/passwd
fi

LOCK_DIR=/workspace/schema_extraction/pg_hive/schemadiscovery/target
LOCK="$LOCK_DIR/.pghive.lock"

mkdir -p "$LOCK_DIR"
exec 9>"$LOCK"
if ! flock -n 9; then
  cat >&2 <<'MSG'
ERROR: another PG-HIVE run is already holding the lock.

All PG-HIVE runs share the sbt build output and the fixed-path output txt, so
concurrent runs silently corrupt each other's results. Wait for the running
extraction to finish before starting another one.
MSG
  exit 1
fi

# fd 9 is inherited by the exec'd process, so the lock is held for its lifetime.
exec "$@"
