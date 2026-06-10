import os
import sys

# gmmschema's clustering iterates over sets/frozensets of strings. Python randomizes
# string hashing per process (PYTHONHASHSEED), so the iteration order — and thus the
# clustering result — varies run to run even with a fixed RANDOM_SEED. Pin the hash
# seed by re-executing once before anything else is imported.
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, "-m", "schema_extraction.main"])

from .lei.lei import main as lei
from .schemi.schemi import main as schemi
from .gmmschema.cluster_script import main as gmmschema
from .pg_hive.pg_hive import main as pg_hive

BOLT_URI = 'bolt://localhost:7687'
USER_NAME = 'neo4j'
PASSWORD = 'password'

MODE = 'all'  # all | single
DB_NAME = 'steam'  # Specify the database name here
METHOD = 4

# pg_hive options
# LSH | MINHASH | KMEANS (only used when extracting)
PG_HIVE_CLUSTERING = 'LSH'
# Default False: reuse the already-extracted results/<db>.txt and just commit to
# Neo4j. Set True to (re)run pg-hive extraction first (heavy, rarely needed).
PG_HIVE_EXTRACT = False

METHODS = [3]  # Specify the methods to run for all databases
DB_NAMES = [
    'findkg',
    'ldbc',
    'mb6',
    'network-management',
    'northwind',
    'spotify',
    'steam',
    'tpc-h',
    'twitter',
    'wordnet',
]

# lei options
LABEL_WEIGHT = 1
PROP_WEIGHT = 0
TOPOLOGY_WEIGHT = 0
THETA = 0.5

# gmmschema options
MID_TABLE_PATH = 'schema_extraction/gmmschema/data.csv'
SAMPLING_RATE = 80  # Adjust sampling rate as needed


def create_all_schema(methods):
    res = []
    for db_name in DB_NAMES:
        for method in methods:
            res.append(create_single_schema(db_name, method))
    print(res)


def create_single_schema(db_name, method):
    """
    Create schema for the specified database using the selected method.
    """
    print(f'Creating schema for {db_name} using method {method}...')
    res = ""
    try:
        match method:
            case 1:
                lei(BOLT_URI, USER_NAME, PASSWORD, db_name,
                    LABEL_WEIGHT, PROP_WEIGHT, TOPOLOGY_WEIGHT, THETA)
            case 2:
                schemi(BOLT_URI, USER_NAME, PASSWORD, db_name)
            case 3:
                gmmschema(BOLT_URI, USER_NAME, PASSWORD,
                          db_name, MID_TABLE_PATH, SAMPLING_RATE)
            case 4:
                pg_hive(BOLT_URI, USER_NAME, PASSWORD, db_name,
                        PG_HIVE_CLUSTERING, extract=PG_HIVE_EXTRACT)
        res = (db_name, method, 'success')
    except Exception as e:
        print(
            f'Error creating schema for {db_name} using method {method}: {e}')
        res = (db_name, method, 'failed')
    return res


if __name__ == "__main__":
    if MODE == 'single':
        create_single_schema(DB_NAME, METHOD)
    elif MODE == 'all':
        create_all_schema(METHODS)
    else:
        raise ValueError("Invalid mode. Use 'single' or 'all'.")
