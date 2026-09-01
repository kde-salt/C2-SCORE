# Fixed seed to make gmmschema fully deterministic across runs.
# Overridable via the GMMSCHEMA_SEED env var (used for seed-sweep experiments).
import os

RANDOM_SEED = int(os.environ.get("GMMSCHEMA_SEED", "42"))

# Delimiter for property-key lists in the mid-table CSV (storing.py writes,
# infer.py reads back). Must be a character that cannot appear in property
# keys: IRI keys (dblp / dbpedia) contain ":", so the original ":" delimiter
# split them into fragments.
PROP_SEP = "\x1f"
