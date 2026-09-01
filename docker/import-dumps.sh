#!/usr/bin/env bash
#
# Import every dump under $DUMP_DIR into the running neo4j container.
#
# Usage:
#   ./docker/import-dumps.sh
#
# This is a thin wrapper around import_dumps.sh, which the compose file mounts
# into the container at /scripts/import_dumps.sh. The dump directory is mounted
# at /dumps (set DUMP_DIR in .env to point at your download location).

set -euo pipefail

cd "$(dirname "$0")/.."
. docker/dc.sh

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

# -u neo4j is essential: `docker compose exec` defaults to root, and store
# files created by root leave the DBMS (uid 7474) unable to write the database
# afterwards -- it then fails to come online with no obvious cause.
exec $DC exec -u neo4j \
  -e NEO4J_PASSWORD="${C2_NEO4J_PASSWORD:-password}" \
  neo4j bash /scripts/import_dumps.sh /var/lib/neo4j "${1:-/dumps}"
