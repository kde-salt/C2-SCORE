#!/usr/bin/env python
"""Reconstruct node-type information in the 2GNF-normalized DBpedia graph.

The Egger et al. artifact stores node types in the ordinary attribute
`~label`, so its GNF1 step (extraction of multi-valued / node-valued
attributes into edges) also decomposes *type information* into structure:

  - 34 "type nodes" (one per extracted type URI, `~label` = '~label',
    the type URI kept in the `IRI` property), and
  - 1,170,172 edges of type `~label` from a node to the type node(s) that
    represent its original type(s).  Affected source nodes are left with the
    default `~label` = 'NODE' (or, for 1,159 nodes hit by the artifact's
    alias handling, an attribute-IRI value).

Which nodes are affected depends on unordered-map iteration order, i.e. it
is nondeterministic across runs.  Because the normalization experiment needs a paired
original-vs-normalized comparison where type information is represented as
real Neo4j labels on BOTH sides (the original `dbpedia` DB was converted
with convert_labels.py), this script undoes exactly the `~label`
*type-to-structure* decomposition -- and nothing else -- before
convert_labels.py is applied:

  1. reconstruct: for every node with outgoing `~label` edges, set its
     `~label` property to the collected type URIs (list if >= 2).
     Verified lossless: the edge-derived type sets of 'NODE'-valued nodes
     match the original DB's label sets exactly.
  2. prune: delete all `~label` edges, then the (now isolated) 34 type
     nodes.  Aborts if a type node still has any other relationship.

Usage (in this order; each phase is idempotent and re-runnable):

  python -m dataset_preparation.reconstruct_2gnf_labels --phase reconstruct
  python -m dataset_preparation.reconstruct_2gnf_labels --phase prune

Known, accepted discrepancy: 1,159 resource nodes whose
graph-structural role was taken over by a literal-value node (artifact
alias bug) remain as isolated 'NODE' (-> Untyped) shells, so the final
Untyped count is 13,156,995 + 1,159 = 13,158,154.
"""

import argparse
import sys

from neo4j import GraphDatabase


from experiment.common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

DB = "dbpedia-2gnf"

BATCH_SIZE = 10_000

TYPE_NODE_COUNT = 34
LABEL_EDGE_COUNT = 1_170_172


def run_iterate(session, outer, inner, desc, batch_size=BATCH_SIZE):
    result = session.run(
        "CALL apoc.periodic.iterate($outer, $inner, "
        "{batchSize: $batchSize, parallel: false}) "
        "YIELD batches, total, failedBatches, failedOperations, errorMessages "
        "RETURN batches, total, failedBatches, failedOperations, errorMessages",
        outer=outer,
        inner=inner,
        batchSize=batch_size,
    )
    rec = result.single()
    print(
        f"{desc}: total={rec['total']} batches={rec['batches']} "
        f"failedBatches={rec['failedBatches']} failedOperations={rec['failedOperations']}"
    )
    if rec["failedBatches"] or rec["failedOperations"]:
        print(f"ERRORS: {rec['errorMessages']}")
        sys.exit(1)


def phase_reconstruct(session):
    run_iterate(
        session,
        "MATCH (n) WHERE EXISTS { (n)-[:`~label`]->() } RETURN n",
        "MATCH (n)-[:`~label`]->(t) "
        "WITH n, collect(t.IRI) AS ts "
        # defensively keep an existing real type value (empirically none)
        "WITH n, apoc.coll.toSet("
        "  ts + CASE WHEN n.`~label` STARTS WITH ':' THEN [n.`~label`] ELSE [] END"
        ") AS vals "
        "SET n.`~label` = CASE WHEN size(vals) = 1 THEN vals[0] ELSE vals END",
        "reconstruct ~label from edges",
    )


def phase_prune(session):
    run_iterate(
        session,
        "MATCH ()-[r:`~label`]->() RETURN r",
        "DELETE r",
        "delete ~label edges",
        batch_size=50_000,
    )
    stray = session.run(
        "MATCH (t) WHERE t.`~label` = '~label' AND COUNT { (t)--() } > 0 "
        "RETURN count(t) AS c"
    ).single()["c"]
    if stray:
        print(f"ERROR: {stray} type nodes still have relationships; not deleting")
        sys.exit(1)
    deleted = session.run(
        "MATCH (t) WHERE t.`~label` = '~label' DELETE t RETURN count(*) AS c"
    ).single()["c"]
    print(f"type nodes deleted: {deleted} (expected {TYPE_NODE_COUNT} on first run)")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", required=True, choices=["reconstruct", "prune"]
    )
    args = parser.parse_args()

    with GraphDatabase.driver(URI, auth=AUTH) as driver:
        with driver.session(database=DB) as session:
            if args.phase == "reconstruct":
                phase_reconstruct(session)
            elif args.phase == "prune":
                phase_prune(session)


if __name__ == "__main__":
    main()
