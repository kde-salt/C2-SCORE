#!/usr/bin/env bash
#
# Import all Neo4j dump files in a directory into a running Neo4j DBMS
# in one shot: each <name>.dump becomes a database called <name>.
#
# Usage:
#   ./import_dumps.sh <NEO4J_INSTANCE_DIR> [DUMP_DIR]

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: ./import_dumps.sh <NEO4J_INSTANCE_DIR> [DUMP_DIR]

Arguments:
  NEO4J_INSTANCE_DIR  Root directory of the Neo4j DBMS instance, i.e. the
                      directory that contains bin/neo4j-admin.
                      With Neo4j Desktop 2.x on macOS this is typically:
                      ~/Library/Application Support/neo4j-desktop/Application/Data/dbmss/dbms-<id>
  DUMP_DIR            Directory containing the *.dump files
                      (default: ./edbt_dumps next to this script).

Environment variables:
  NEO4J_URI           Bolt URI          (default: bolt://localhost:7687)
  NEO4J_USER          Database user     (default: neo4j)
  NEO4J_PASSWORD      Database password (default: password)

The Neo4j instance must be RUNNING. For every <name>.dump the script stops
the database <name> if it already exists, loads the dump (overwriting any
previous content), and (re)creates and starts the database. The `tmp`
workspace database is created as well.
EOF
}

if [ $# -lt 1 ] || [ $# -gt 2 ]; then
  usage
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
NEO4J_HOME="$1"
DUMP_DIR="${2:-$SCRIPT_DIR/edbt_dumps}"
NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"

NEO4J_ADMIN="$NEO4J_HOME/bin/neo4j-admin"
CYPHER_SHELL="$NEO4J_HOME/bin/cypher-shell"

[ -x "$NEO4J_ADMIN" ]   || { echo "ERROR: $NEO4J_ADMIN not found or not executable." >&2; exit 1; }
[ -x "$CYPHER_SHELL" ]  || { echo "ERROR: $CYPHER_SHELL not found or not executable." >&2; exit 1; }
[ -d "$DUMP_DIR" ]      || { echo "ERROR: dump directory $DUMP_DIR does not exist." >&2; exit 1; }

NAMES=()
for f in "$DUMP_DIR"/*.dump; do
  [ -e "$f" ] || { echo "ERROR: no *.dump files found in $DUMP_DIR." >&2; exit 1; }
  NAMES+=("$(basename "$f" .dump)")
done
echo "Found ${#NAMES[@]} dump file(s) in $DUMP_DIR."

cyq() {
  "$CYPHER_SHELL" -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
    -d system --format plain "$1"
}

# Doubles as the connectivity check: fails if the instance is not running.
if ! EXISTING="$(cyq "SHOW DATABASES YIELD name RETURN name;" | tail -n +2 | tr -d '"')"; then
  echo "ERROR: cannot connect to $NEO4J_URI. Start the Neo4j instance first." >&2
  exit 1
fi

# Stop databases that already exist so neo4j-admin can overwrite their stores.
for name in "${NAMES[@]}"; do
  if printf '%s\n' "$EXISTING" | grep -qx "$name"; then
    echo "Stopping existing database: $name"
    cyq "STOP DATABASE \`$name\` WAIT;" >/dev/null
  fi
done

echo "Loading all dumps with neo4j-admin (this may take a while)..."
"$NEO4J_ADMIN" database load --from-path="$DUMP_DIR" --overwrite-destination=true "*"

for name in "${NAMES[@]}"; do
  echo "Creating and starting database: $name"
  cyq "CREATE DATABASE \`$name\` IF NOT EXISTS WAIT;" >/dev/null
  cyq "START DATABASE \`$name\` WAIT;" >/dev/null
done

echo "Creating workspace database: tmp"
cyq "CREATE DATABASE tmp IF NOT EXISTS WAIT;" >/dev/null

# Verify that every imported database (and tmp) is online.
ONLINE="$(cyq "SHOW DATABASES YIELD name, currentStatus WHERE currentStatus = 'online' RETURN name;" | tail -n +2 | tr -d '"')"
FAILED=0
for name in "${NAMES[@]}" tmp; do
  if ! printf '%s\n' "$ONLINE" | grep -qx "$name"; then
    echo "ERROR: database $name is not online." >&2
    FAILED=1
  fi
done
[ "$FAILED" -eq 0 ] || exit 1

echo "Done: ${#NAMES[@]} database(s) imported and online (plus tmp)."
