#!/usr/bin/env python
"""Convert artifact-style `~label` properties into real Neo4j labels.

The DBLP / DBpedia graphs imported from the Egger et al. (PVLDB'26) artifact
store every node under the generic label `NODE` and keep the actual type(s)
in the `~label` property:

  - single type   -> string ":<URI>"           (e.g. ":http://dbpedia.org/ontology/Person")
  - multiple types-> list of ":<URI>" strings
  - no type info  -> string "NODE"             (DBpedia only)

This script rewrites those into real labels (URI local names, "NODE" ->
"Untyped"), removes the generic `NODE` label, and finally deletes the
artifact-only properties `~label` / `neo4jImportId`.

Phases (run in order; each is idempotent and can be re-run after a failure):

  python -m dataset_preparation.convert_labels --db dblp --phase mapping   # build + validate mapping (read-only)
  python -m dataset_preparation.convert_labels --db dblp --phase convert   # drop import constraint, set labels
  python -m dataset_preparation.convert_labels --db dblp --phase cleanup   # remove ~label / neo4jImportId, checkpoint

Restore from the pre-conversion dump if anything goes wrong.
"""

import argparse
import re
import sys

from neo4j import GraphDatabase

from experiment.common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

BATCH_SIZE = 10_000

# d0.owl#Activity collides with dbo:Activity when shortened to its local name.
SPECIAL_NAMES = {
    ":http://www.ontologydesignpatterns.org/ont/d0.owl#Activity": "D0Activity",
    "NODE": "Untyped",
}

# Namespace prefixes for *attribute IRIs* (values without the ":" marker).
# These occur only in the 2GNF-normalized DBpedia graph (`dbpedia-2gnf`),
# where the artifact's GNF1 step labels each extracted attribute-value node
# with the attribute's IRI.  Local names alone collide across namespaces
# (dbo:name / dbp:name / foaf:name) and with nothing else to distinguish
# them, so these labels get an explicit namespace prefix.  Type URIs
# (":<URI>" values) are NOT affected -- their names must stay identical to
# the already-converted `dblp` / `dbpedia` databases.
ATTR_NAMESPACES = [
    ("http://dbpedia.org/ontology/", "dbo_"),
    ("http://dbpedia.org/property/", "dbp_"),
    ("http://xmlns.com/foaf/0.1/", "foaf_"),
    ("http://purl.org/dc/elements/1.1/", "dc_"),
    ("http://www.w3.org/2000/01/rdf-schema#", "rdfs_"),
    ("http://www.w3.org/2002/07/owl#", "owl_"),
]


def attr_label_name(iri: str) -> str:
    """Map an attribute IRI to a namespace-prefixed Neo4j label name."""
    prefix = ""
    rest = re.sub(r"^https?://", "", iri)
    for ns, p in ATTR_NAMESPACES:
        if iri.startswith(ns):
            prefix, rest = p, iri[len(ns):]
            break
    return prefix + re.sub(r"[^0-9A-Za-z_]", "_", rest)


def local_name(value: str) -> str:
    """Map one `~label` value to a Neo4j label name.

    Values are either ":<URI>" (a node type), "NODE" (no type info), or --
    in the 2GNF graph only -- a bare attribute IRI on an extracted
    attribute-value node.
    """
    if value in SPECIAL_NAMES:
        return SPECIAL_NAMES[value]
    if not value.startswith(":"):
        return attr_label_name(value)
    uri = value.removeprefix(":")
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    return uri.rstrip("/").rsplit("/", 1)[1]


def fetch_value_distribution(session):
    """Distribution of raw `~label` values, each canonicalized to a sorted tuple."""
    result = session.run(
        "MATCH (n) "
        "WITH CASE WHEN n.`~label` IS :: LIST<ANY> "
        "  THEN [x IN n.`~label` | toString(x)] "
        "  ELSE [toString(n.`~label`)] END AS vals "
        "RETURN vals AS vals, count(*) AS cnt"
    )
    return {tuple(sorted(rec["vals"])): rec["cnt"] for rec in result}


def build_mapping(value_dist):
    """URI -> label name for every distinct `~label` value, with validation."""
    uris = sorted({v for vals in value_dist for v in vals})
    mapping = {u: local_name(u) for u in uris}

    errors = []
    by_name = {}
    for u, name in mapping.items():
        by_name.setdefault(name, []).append(u)
        if not name:
            errors.append(f"empty name for {u!r}")
        if ":" in name or any(c.isspace() for c in name):
            errors.append(f"forbidden character in {name!r} (from {u!r})")
        if name in ("NODE",):
            errors.append(f"reserved name {name!r} (from {u!r})")
    for name, sources in by_name.items():
        if len(sources) > 1:
            errors.append(f"collision on {name!r}: {sources}")
    if "Untyped" in by_name and by_name["Untyped"] != ["NODE"]:
        errors.append(f"'Untyped' produced by a real URI: {by_name['Untyped']}")
    if errors:
        for e in errors:
            print(f"MAPPING ERROR: {e}")
        sys.exit(1)
    return mapping


def phase_mapping(session, dump_path=None):
    value_dist = fetch_value_distribution(session)
    mapping = build_mapping(value_dist)
    print(f"distinct ~label values (as sets): {len(value_dist)}")
    print(f"distinct label names            : {len(mapping)}")
    if dump_path:
        with open(dump_path, "w") as f:
            f.write("| `~label` value | Neo4j label |\n|---|---|\n")
            for u, name in sorted(mapping.items()):
                f.write(f"| `{u}` | `{name}` |\n")
        print(f"mapping table written to {dump_path}")
    return value_dist, mapping


def phase_convert(session, mapping):
    session.run("DROP CONSTRAINT node_import_id IF EXISTS").consume()
    print("constraint node_import_id dropped (if it existed)")

    result = session.run(
        "CALL apoc.periodic.iterate("
        "  'MATCH (n:NODE) RETURN n',"
        "  'WITH n, CASE WHEN n.`~label` IS :: LIST<ANY> "
        "     THEN [x IN n.`~label` | $mapping[toString(x)]] "
        "     ELSE [$mapping[toString(n.`~label`)]] END AS names "
        "   CALL apoc.create.addLabels(n, names) YIELD node "
        "   REMOVE node:NODE',"
        "  {batchSize: $batchSize, parallel: false, params: {mapping: $mapping}}"
        ") YIELD batches, total, failedBatches, failedOperations, errorMessages "
        "RETURN batches, total, failedBatches, failedOperations, errorMessages",
        mapping=mapping,
        batchSize=BATCH_SIZE,
    )
    rec = result.single()
    print(
        f"convert: total={rec['total']} batches={rec['batches']} "
        f"failedBatches={rec['failedBatches']} failedOperations={rec['failedOperations']}"
    )
    if rec["failedBatches"] or rec["failedOperations"]:
        print(f"ERRORS: {rec['errorMessages']}")
        sys.exit(1)


def phase_cleanup(session):
    for prop in ("~label", "neo4jImportId"):
        result = session.run(
            "CALL apoc.periodic.iterate("
            "  'MATCH (n) WHERE n.`" + prop + "` IS NOT NULL RETURN n',"
            "  'REMOVE n.`" + prop + "`',"
            "  {batchSize: $batchSize, parallel: false}"
            ") YIELD batches, total, failedBatches, failedOperations, errorMessages "
            "RETURN batches, total, failedBatches, failedOperations, errorMessages",
            batchSize=BATCH_SIZE,
        )
        rec = result.single()
        print(
            f"remove {prop}: total={rec['total']} failedBatches={rec['failedBatches']} "
            f"failedOperations={rec['failedOperations']}"
        )
        if rec["failedBatches"] or rec["failedOperations"]:
            print(f"ERRORS: {rec['errorMessages']}")
            sys.exit(1)

    # relationships: the artifact import puts these properties on nodes only,
    # but verify that assumption on the live data before declaring done.
    rel_keys = session.run(
        "MATCH ()-[r]->() UNWIND keys(r) AS k RETURN DISTINCT k"
    ).value()
    leftover_rel = [k for k in rel_keys if k in ("~label", "neo4jImportId")]
    if leftover_rel:
        print(f"ERROR: artifact properties on relationships: {leftover_rel}")
        sys.exit(1)
    print(f"relationship property keys: {len(rel_keys)} (no artifact keys)")

    leftover = session.run(
        "MATCH (n) WHERE n.`~label` IS NOT NULL OR n.neo4jImportId IS NOT NULL "
        "RETURN count(n) AS c"
    ).single()["c"]
    if leftover:
        print(f"ERROR: {leftover} nodes still carry artifact properties")
        sys.exit(1)
    print("cleanup: ALL OK")

    session.run("CALL db.checkpoint()").consume()
    print("checkpoint done")


EXPECTED_TOTALS = {
    "dblp": (10_584_818, 23_084_323),
    "dbpedia": (19_864_182, 45_414_669),
    # 2GNF-normalized DBpedia (artifact `./main dbpedia 2 0`,
    # GNF2 row of results/dbpedia_results.csv, minus the 34 type nodes and
    # 1,170,172 `~label` edges pruned by reconstruct_2gnf_labels.py)
    "dbpedia-2gnf": (28_858_918, 120_953_920),
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, choices=sorted(EXPECTED_TOTALS))
    parser.add_argument(
        "--phase", required=True, choices=["mapping", "convert", "cleanup"]
    )
    parser.add_argument(
        "--dump-mapping", help="write the URI -> label mapping as a markdown table"
    )
    args = parser.parse_args()

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session(database=args.db) as session:
            if args.phase == "mapping":
                phase_mapping(session, args.dump_mapping)
            elif args.phase == "convert":
                value_dist = fetch_value_distribution(session)
                mapping = build_mapping(value_dist)
                phase_convert(session, mapping)
            elif args.phase == "cleanup":
                phase_cleanup(session)


if __name__ == "__main__":
    main()
