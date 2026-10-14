# Sourced by the helper scripts: sets $DC to whichever Compose v2 front end is
# available. Docker ships it as the `docker compose` plugin; some installations
# only have the standalone `docker-compose` binary.
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' was found." >&2
  exit 1
fi
