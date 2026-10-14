#!/usr/bin/env python
"""Create the Case N2 (Table 4) paired databases `suni1` / `suni1-norm`.

S_Uni-1 is the University scenario of Schrott et al., "Graph-Native
Normalization" (arXiv:2603.02995, EDBT 2027). The original graph is the
artifact file graphs/lecture.cypher (tag `edbt-2027`); the normalized graph is
the paper's Fig. 2 (psi_between-n-ep moves the duplicated `usingBook` property
from the TEACHES edges to the Course node). Both are stored verbatim in
experiment/normalization_test/data/.

Usage (from the repository root, .venv activated):

  python experiment/normalization_test/load_suni1.py

The script drops and recreates only `suni1` / `suni1-norm`, loads the Cypher
files, and verifies each database against the paper's published figures
(4 nodes / 3 edges; AvgPropNode 1.25 vs 1.5; AvgPropEdge 2 vs 1).
"""

from pathlib import Path

from neo4j import GraphDatabase

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

DATA_DIR = Path(__file__).parent / "data"

# db name -> (cypher file, expected verification values)
DATASETS = {
    "suni1": {
        "file": DATA_DIR / "suni1.cypher",
        "avg_node_props": 1.25,
        "avg_edge_props": 2.0,
        "using_book_on_edges": 3,
        "using_book_on_nodes": 0,
        "teaches_keys": {"at", "usingBook"},
    },
    "suni1-norm": {
        "file": DATA_DIR / "suni1-norm.cypher",
        "avg_node_props": 1.5,
        "avg_edge_props": 1.0,
        "using_book_on_edges": 0,
        "using_book_on_nodes": 1,
        "teaches_keys": {"at"},
    },
}


def read_statement(path: Path) -> str:
    """Strip `//` comment lines; the remaining CREATE clauses form one query."""
    lines = [l for l in path.read_text().splitlines() if not l.lstrip().startswith("//")]
    return "\n".join(l for l in lines if l.strip())


def check(name, actual, expected, failures):
    ok = actual == expected
    print(f"    {name}: {actual} (expected {expected}) {'OK' if ok else 'MISMATCH'}")
    if not ok:
        failures.append(name)


def verify(driver, db_name, expect, failures):
    with driver.session(database=db_name) as s:
        nodes = s.run("MATCH (n) RETURN count(n) AS c").single()["c"]
        edges = s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
        labels = s.run(
            "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l"
        ).values()
        avg_np = s.run(
            "MATCH (n) RETURN avg(size(keys(n))) AS a").single()["a"]
        avg_ep = s.run(
            "MATCH ()-[r]->() RETURN avg(size(keys(r))) AS a").single()["a"]
        ub_edges = s.run(
            "MATCH ()-[r]->() WHERE r.usingBook IS NOT NULL RETURN count(r) AS c"
        ).single()["c"]
        ub_nodes = s.run(
            "MATCH (n) WHERE n.usingBook IS NOT NULL RETURN count(n) AS c"
        ).single()["c"]
        teaches_keys = set(
            s.run(
                "MATCH ()-[r:TEACHES]->() UNWIND keys(r) AS k RETURN DISTINCT k"
            ).value()
        )

    check("nodes", nodes, 4, failures)
    check("edges", edges, 3, failures)
    check("labels", dict(labels), {"Course": 1, "Lecturer": 3}, failures)
    check("avg node props", avg_np, expect["avg_node_props"], failures)
    check("avg edge props", avg_ep, expect["avg_edge_props"], failures)
    check("usingBook on edges", ub_edges, expect["using_book_on_edges"], failures)
    check("usingBook on nodes", ub_nodes, expect["using_book_on_nodes"], failures)
    check("TEACHES property keys", teaches_keys, expect["teaches_keys"], failures)


def main():
    driver = GraphDatabase.driver(URI, auth=AUTH)
    failures = []
    with driver.session(database="system") as sys_session:
        existing = {r["name"] for r in sys_session.run("SHOW DATABASES YIELD name")}
        for db_name in DATASETS:
            state = "exists (will be replaced)" if db_name in existing else "new"
            print(f"[pre-check] {db_name}: {state}")

        for db_name, expect in DATASETS.items():
            print(f"[create] CREATE OR REPLACE DATABASE {db_name}")
            sys_session.run(f"CREATE OR REPLACE DATABASE `{db_name}` WAIT").consume()
            statement = read_statement(expect["file"])
            with driver.session(database=db_name) as s:
                s.run(statement).consume()
            print(f"[load] {expect['file'].name} loaded into {db_name}")

    for db_name, expect in DATASETS.items():
        print(f"[verify] {db_name}")
        verify(driver, db_name, expect, failures)

    driver.close()
    if failures:
        raise SystemExit(f"verification FAILED: {failures}")
    print("All checks passed.")


if __name__ == "__main__":
    main()
