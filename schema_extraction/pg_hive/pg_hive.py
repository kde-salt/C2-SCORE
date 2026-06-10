"""
PG-HIVE wrapper, split into two independent steps.

- extract(db_name, ...)        : run pg-hive (Scala/Spark) and archive its
                                 strict-schema txt to results/. Heavy and only
                                 needed once per dataset; rarely run afterwards.
- text_to_neo4j(..., db_name)  : read the already-extracted results/<db>.txt and
                                 commit it as the Neo4j schema db "<db>-pg-hive".
                                 This is the default / main path.

`main()` keeps the lei/schemi/gmmschema signature so main.py can call it
uniformly via `case 4: pg_hive(BOLT_URI, USER_NAME, PASSWORD, db_name, ...)`.
By default it only runs text_to_neo4j; pass extract=True to (re)run pg-hive
first.
"""

import os
import shutil
import subprocess

# Absolute path to pg-hive's sbt project root (bundled under pg_hive/)
PG_HIVE_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "schemadiscovery")
)
OUTPUT_TXT = os.path.join(PG_HIVE_DIR, "pg_schema_output_strict.txt")

# pg-hive overwrites its output every run, so keep a per-dataset copy here.
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Scala 2.12 requires Java 11 (not compatible with Java 21). Override with the
# JAVA_11_HOME env var if your toolchain lives elsewhere.
JAVA_11_HOME = os.environ.get(
    "JAVA_11_HOME",
    "/opt/homebrew/Cellar/openjdk@11/11.0.27/libexec/openjdk.jdk/Contents/Home",
)


def _run_pghive(db_name: str, clustering_method: str):
    print(f"[pg_hive] Running pg-hive: db={db_name}, method={clustering_method}")
    print(f"[pg_hive] Working dir: {PG_HIVE_DIR}")
    env = os.environ.copy()
    env["JAVA_HOME"] = JAVA_11_HOME
    env["PATH"] = f"{JAVA_11_HOME}/bin:{env.get('PATH', '')}"
    result = subprocess.run(
        ["sbt", "-java-home", JAVA_11_HOME, f"run {clustering_method} {db_name}"],
        cwd=PG_HIVE_DIR,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pg-hive failed (exit {result.returncode}). "
            "Check sbt/Spark logs above."
        )
    if not os.path.exists(OUTPUT_TXT):
        raise FileNotFoundError(
            f"Expected output not found: {OUTPUT_TXT}"
        )
    print(f"[pg_hive] pg-hive output: {OUTPUT_TXT}")
    return OUTPUT_TXT


def _archived_txt(db_name: str) -> str:
    """Path of the per-dataset archived strict-schema txt (results/<db>.txt)."""
    return os.path.join(RESULTS_DIR, f"{db_name}.txt")


def _archive_output(db_name: str, txt_path: str) -> str:
    """Copy pg-hive's (overwritten-every-run) output to a per-dataset file."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    dest = _archived_txt(db_name)
    shutil.copyfile(txt_path, dest)
    print(f"[pg_hive] archived schema: {dest}")
    return dest


def extract(db_name: str, clustering_method: str = "LSH") -> str:
    """
    Step 1 (heavy, rarely run): run pg-hive against the target Neo4j database and
    archive its strict-schema output to results/<db_name>.txt.
    Returns the archived txt path.
    """
    txt_path = _run_pghive(db_name, clustering_method)
    return _archive_output(db_name, txt_path)


def text_to_neo4j(uri: str, user: str, pw: str, db_name: str,
                  txt_path: str | None = None) -> None:
    """
    Step 2 (default, main path): read an already-extracted schema txt and commit
    it as the Neo4j schema db "<db_name>-pg-hive". Defaults to the archived
    results/<db_name>.txt.
    """
    if txt_path is None:
        txt_path = _archived_txt(db_name)
    if not os.path.exists(txt_path):
        raise FileNotFoundError(
            f"Schema txt not found: {txt_path}\n"
            f"Run extract('{db_name}') once to produce it (pg-hive extraction)."
        )
    print(f"[pg_hive] committing schema from: {txt_path}")
    from .convert import main as convert_main
    convert_main(db_name, txt_path)


def main(
    uri: str,
    user: str,
    pw: str,
    db_name: str,
    clustering_method: str = "LSH",
    extract: bool = False,
):
    """
    Default: reuse the already-extracted txt and commit to Neo4j (text_to_neo4j).
    extract=True: (re)run pg-hive first, then commit.
    """
    txt_path = None
    if extract:
        # Inlined so the `extract` flag does not shadow the extract() function.
        txt_path = _archive_output(db_name, _run_pghive(db_name, clustering_method))
    text_to_neo4j(uri, user, pw, db_name, txt_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="PG-HIVE: build Neo4j schema from a pg-hive strict-schema txt."
    )
    parser.add_argument("db_name", help="dataset / database name")
    parser.add_argument(
        "--extract", action="store_true",
        help="(re)run pg-hive to extract the txt before committing (heavy)",
    )
    parser.add_argument(
        "--clustering", default="LSH", choices=["LSH", "MINHASH", "KMEANS"],
        help="pg-hive clustering method, only used with --extract (default: LSH)",
    )
    parser.add_argument("--txt", default=None,
                        help="explicit txt path (overrides results/ archive)")
    args = parser.parse_args()

    if args.extract:
        main("bolt://localhost:7687", "neo4j", "password",
             args.db_name, args.clustering, extract=True)
    else:
        text_to_neo4j("bolt://localhost:7687", "neo4j", "password",
                      args.db_name, args.txt)
