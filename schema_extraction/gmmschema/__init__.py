# Fixed seed to make gmmschema fully deterministic across runs.
# Overridable via the GMMSCHEMA_SEED env var (used for seed-sweep experiments).
import os

RANDOM_SEED = int(os.environ.get("GMMSCHEMA_SEED", "42"))
