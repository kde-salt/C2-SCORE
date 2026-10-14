""" Script to create a Neo4j graph with """

# Imports
import csv
import os
import sys

# Neo4j imports
from neo4j import GraphDatabase

from . import PROP_SEP

# Write the schema graph with batched UNWIND statements instead of one Cypher
# round trip per schema type / EXTENDS edge / instance edge signature. Both
# paths produce the same graph -- verified against the committed implementation
# on six datasets, schema DBs identical and the mid-table CSV byte-identical.
# Set GMMSCHEMA_FAST_WRITE=0 to
# fall back to the per-statement path.
FAST_WRITE = os.environ.get("GMMSCHEMA_FAST_WRITE", "1") != "0"

# Rows per UNWIND statement, to bound the parameter payload on the large
# variants (dbpedia-dl reaches ~140k edge signatures).
WRITE_BATCH = 10_000

# A single CSV field holds every property key of a node type joined together;
# with IRI keys (dblp / dbpedia) this exceeds the csv module's 128KiB default.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def bq(name):
    """ Quote a Cypher identifier (label / property key / relationship type)
    so IRI names containing ':', '/', '.', '#' stay syntactically valid. """
    return "`" + name.replace("`", "``") + "`"


def create_neo4j_graph(
    driver2,
    uri,
    user,
    passwd,
    db_name,
    mid_table_path
):
    """ Create a Neo4j graph

    Parameters
    ----------
    driver2 : GraphDatabase.driver object
        Driver used to access the PG stored in a Neo4j database.
    edges : Boolean.
        If edges is set at True by default.
        When edges is at True, add all edges to the Neo4j graph.
        When edges is at False, only add edges SUBTYPE_OF.

    Returns
    -------
    A Neo4j graph representation of the inferred schema
    """

    with driver2.session() as session:
        query = "MATCH (n)-[r]->(m) \
            RETURN DISTINCT labels(n),keys(n),type(r),labels(m),keys(m)"
        edge_types = session.run(query)

        all_labels_n = []
        all_keys_n = []
        all_type_r = []
        all_keys_m = []
        all_labels_m = []

        for edge_type in edge_types:
            all_labels_n.append(
                ":".join(bq(label) for label in sorted(
                    edge_type["labels(n)"]))
            )
            all_keys_n.append(PROP_SEP.join(sorted(edge_type["keys(n)"])))
            all_type_r.append(edge_type["type(r)"])
            all_labels_m.append(
                ":".join(bq(label) for label in sorted(
                    edge_type["labels(m)"]))
            )
            all_keys_m.append(PROP_SEP.join(sorted(edge_type["keys(m)"])))

    driver = GraphDatabase.driver(uri, database=f"{db_name}-gmmschema",
                                  auth=(user, passwd), encrypted=False)

    with driver.session() as session:
        query = "MATCH (n) DETACH DELETE n"
        session.run(query)

        with open(mid_table_path) as csv_file:
            lines = csv.reader(csv_file, delimiter=',')
            # skip header
            next(lines)

            id_elementId_dict = {}
            # (labels, props) -> element ids of every schema node carrying that
            # pair of helper properties. The edge phase below matches on exactly
            # those two properties, and they are set here at creation and not
            # touched again until they are removed at the end, so this mirrors
            # what the per-signature MATCH would find.
            sig_elementIds = {}
            extends_pairs = []
            for row in lines:
                if row[5] == "yes" and row[2] == "":
                    continue

                # Optional markers ("?") are stripped from the label string but
                # deliberately KEPT in the property string below. The upstream
                # implementation keeps them in both; dropping them here lets a
                # type whose optional labels are all present match a real node
                # signature and receive its edges. Measured impact of this
                # asymmetry across all 15 datasets: exactly one type
                # (wordnet `Resource`:`ontolex__LexicalSense`, 20 edges).
                # Aligning either way changes the results without moving closer
                # to the original paper, so it is left as is on purpose.
                node_id = row[0]
                node_labels = ":".join(
                    bq(label) for label in sorted(row[1].split(":"))
                ).replace("?", "")
                joined_props = PROP_SEP.join(sorted(row[2].split(PROP_SEP)))
                props = row[2].split(PROP_SEP)
                combined_props = ""
                for prop in props:
                    if prop == "":
                        continue
                    if "?" in prop:
                        prop = prop.replace("?", "")
                        combined_props += f"{bq(prop)}:\"type?\","
                    else:
                        combined_props += f"{bq(prop)}:\"type\","
                if combined_props == "":
                    combined_props = "{labels:$labels,props:$props}"
                else:
                    combined_props = "{labels:$labels,props:$props," + \
                        combined_props[:-1] + "}"
                query = f"MERGE (n:{node_labels} {combined_props}) RETURN elementId(n)"
                result = session.run(query, labels=node_labels,
                                     props=joined_props)
                element_id = result.single()[0]
                id_elementId_dict[node_id] = element_id
                # MERGE returns the existing node when two rows describe the
                # same type, so guard against registering an id twice.
                ids_for_sig = sig_elementIds.setdefault(
                    (node_labels, joined_props), [])
                if element_id not in ids_for_sig:
                    ids_for_sig.append(element_id)

                # for base type
                if row[5] == "yes":
                    continue

                parent_id = row[3]
                parent_element_id = id_elementId_dict.get(parent_id)
                if parent_element_id is None:
                    continue

                # neo4j node creation query
                if FAST_WRITE:
                    # Deferred to one UNWIND below. CREATE, not MERGE, so a
                    # repeated pair must stay a repeated edge -- do not dedupe.
                    extends_pairs.append(
                        {"p": parent_element_id, "c": element_id})
                else:
                    query2 = f"""
                    MATCH (parent),(child) \
                    WHERE elementId(parent) = \"{str(parent_element_id)}\" \
                            AND elementId(child) = \"{str(element_id)}\"
                    CREATE (child)-[:EXTENDS]->(parent)
                    """
                    session.run(query2)

        if FAST_WRITE and extends_pairs:
            extends_q = """
            UNWIND $pairs AS pair
            MATCH (parent) WHERE elementId(parent) = pair.p
            MATCH (child)  WHERE elementId(child)  = pair.c
            CREATE (child)-[:EXTENDS]->(parent)
            """
            for start in range(0, len(extends_pairs), WRITE_BATCH):
                session.run(extends_q,
                            pairs=extends_pairs[start:start + WRITE_BATCH])

    # Edge types are created only where a schema type's (labels, props) string
    # is EXACTLY equal to an instance node signature -- the upstream behaviour
    # (pg-schemainference, infer.py:88-98). Consequence: a type carrying any
    # optional property can never receive an edge, and the paper's rule that a
    # subtype inherits its parent's edge types (EDBT'22 §4, Example 4.1) is not
    # implemented. This is why dblp yields zero edge types.
    with driver.session() as session:
        if FAST_WRITE:
            # One statement per relationship type instead of one per instance
            # edge signature. The signature loop below resolves each endpoint
            # with an unindexed MATCH(n),(m) over the schema graph, which is
            # what makes this phase dominate the run time on the DBpedia
            # variants (55,766 signatures = 55,766 round trips = ~25 min).
            # sig_elementIds holds the very nodes that MATCH would return, so
            # the pair set -- and hence the merged edge set -- is unchanged.
            pairs_by_type = {}
            for i in range(len(all_labels_n)):
                src_ids = sig_elementIds.get(
                    (all_labels_n[i].replace("?", ""), all_keys_n[i]))
                dst_ids = sig_elementIds.get((all_labels_m[i], all_keys_m[i]))
                if not src_ids or not dst_ids:
                    continue
                pairs = pairs_by_type.setdefault(all_type_r[i], [])
                for src_id in src_ids:
                    for dst_id in dst_ids:
                        pairs.append({"n": src_id, "m": dst_id})

            for type_r, pairs in pairs_by_type.items():
                # MERGE deduplicates, so identical pairs coming from different
                # signatures collapse exactly as they did one query at a time.
                query = f"""
                UNWIND $pairs AS pair
                MATCH (n) WHERE elementId(n) = pair.n
                MATCH (m) WHERE elementId(m) = pair.m
                MERGE (n)-[r:{bq(type_r)}]->(m)
                """
                for start in range(0, len(pairs), WRITE_BATCH):
                    session.run(query, pairs=pairs[start:start + WRITE_BATCH])
        else:
            for i in range(len(all_labels_n)):
                labels_n = all_labels_n[i].replace("?", "")
                keys_n = all_keys_n[i]
                type_r = all_type_r[i]
                labels_m = all_labels_m[i]
                keys_m = all_keys_m[i]

                query = "MATCH(n),(m) WHERE n.labels=$labels_n AND n.props=$keys_n" \
                    " AND m.labels=$labels_m AND m.props=$keys_m" \
                    f" MERGE (n)-[r:{bq(type_r)}]->(m)"
                session.run(query, labels_n=labels_n, keys_n=keys_n,
                            labels_m=labels_m, keys_m=keys_m)

    # remove the helper properties used for edge creation
    with driver.session() as session:
        query = "MATCH (n) REMOVE n.props"
        session.run(query)
        query = "MATCH (n) REMOVE n.labels"
        session.run(query)
