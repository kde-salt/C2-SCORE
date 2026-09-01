"""
pg-hive strict txt output → Neo4j schema DB converter.

Input : pg_schema_output_strict.txt (produced by pg-hive PGSchemaExporterStrict)
Output: Neo4j named database "{db_name}-pg-hive" whose nodes/edges follow the
        same convention as lei/schemi/gmmschema so that eval_c2 can evaluate it.

Node format in schema DB
  - Labels: actual instance labels  e.g. :Person  or  :Person:Student
  - Props : mandatory → value 'type'   optional → value 'type?'

Edge format in schema DB
  - MATCH src/dst nodes by their labels, then MERGE the relationship.
"""

import os
import re
import time
from neo4j import GraphDatabase

from experiment.common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

# Create the schema edges with batched UNWIND statements instead of one Cypher
# round trip per (src label set, dst label set, rel type). pg-hive merges many
# rel types into a single edge type -- dbpedia-s has 8 edge type definitions
# carrying 565 rel types between them -- so the per-statement loop issues about
# 700k round trips there, which is why converting dbpedia-s took 4.3 hours
# against 51 seconds for the batched path. Both paths produce the same schema DB
# -- verified on six datasets.
# Set PGHIVE_FAST_CONVERT=0 to fall back to the per-statement path.
FAST_CONVERT = os.environ.get("PGHIVE_FAST_CONVERT", "1") != "0"

# Rows per UNWIND statement, to bound the parameter payload.
WRITE_BATCH = 10_000


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_label_alternatives(label_expr: str):
    """
    Parse a label expression into a list of label sets (the union alternatives).
    '|' separates alternatives; ':' separates multi-labels within one.
      'Neuron:Segment'          -> [['Neuron', 'Segment']]
      'Segment | Neuron:Segment'-> [['Segment'], ['Neuron', 'Segment']]
      'SynapseSet'              -> [['SynapseSet']]
    """
    alternatives = []
    for alt in label_expr.split("|"):
        labels = []
        for lbl in alt.split(":"):
            lbl = lbl.strip()
            if lbl and lbl not in labels:
                labels.append(lbl)
        if labels:
            alternatives.append(labels)
    return alternatives


def _parse_props(props_str: str):
    """
    Parse a props block like:
      'firstName STRING, OPTIONAL birthday DATE, weight DOUBLE'
    Returns (mandatory_props: list[str], optional_props: list[str]).

    Split on ', ' (comma AND space), which is what the pg-hive exporters join
    entries with, not on ',' alone: DBpedia has property keys that contain a
    comma themselves (.../otherTeams,otherYears), and splitting on ',' tore
    them into two nonexistent keys.
    """
    mandatory, optional = [], []
    if not props_str or not props_str.strip():
        return mandatory, optional
    for entry in props_str.split(", "):
        entry = entry.strip()
        if not entry:
            continue
        if entry.upper().startswith("OPTIONAL"):
            name = entry[len("OPTIONAL"):].strip().split()[0]
            optional.append(name)
        else:
            name = entry.split()[0]
            mandatory.append(name)
    return mandatory, optional


def parse_strict_txt(filepath: str):
    """
    Returns:
      node_types : dict  type_name -> {labels:[str], mandatory:[str], optional:[str]}
      edge_types : dict  type_name -> {rel_type:str, mandatory:[str], optional:[str]}
      connections: list  (src_type_names:[str], edge_type_name:str, dst_type_names:[str])
    """
    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    # ---- node type definitions ----
    # CREATE NODE TYPE PersonType : Person {firstName STRING, OPTIONAL birthday DATE};
    # CREATE NODE TYPE Person_StudentType : Person | Student;
    # Type name and label expr are separated by ' : ' (spaces around the colon),
    # which distinguishes it from multi-label colons in 'Neuron:Segment'.
    node_types = {}
    node_pat = re.compile(
        r"CREATE NODE TYPE (.+?)\s+:\s+(.+?)\s*(?:\{(.*?)\})?;",
        re.DOTALL,
    )
    for m in node_pat.finditer(content):
        type_name = m.group(1).strip()
        label_expr = m.group(2).strip()
        alternatives = _parse_label_alternatives(label_expr)
        mandatory, optional = _parse_props(m.group(3) or "")
        node_types[type_name] = {
            "alternatives": alternatives,
            "mandatory": mandatory,
            "optional": optional,
        }

    # ---- edge type definitions ----
    # CREATE EDGE TYPE has_emailType : HAS_EMAIL;
    # CREATE EDGE TYPE weighedType : KNOWS {weight DOUBLE};
    # Type name / rel type may be IRIs (contain ':' '/' '.' '#'), so match
    # non-space tokens and split on the ' : ' separator (spaces around the
    # colon), like the node-type pattern above.
    edge_types = {}
    edge_def_pat = re.compile(
        r"CREATE EDGE TYPE (\S+)\s+:\s+([^{;]+?)\s*(?:\{(.*?)\})?;",
        re.DOTALL,
    )
    for m in edge_def_pat.finditer(content):
        type_name = m.group(1)
        rel_type = m.group(2).strip()
        mandatory, optional = _parse_props(m.group(3) or "")
        edge_types[type_name] = {
            "rel_type": rel_type,
            "mandatory": mandatory,
            "optional": optional,
        }

    # ---- graph type section: connection patterns ----
    # (:PersonType)-[has_emailType]->(:EmailType),
    # (:PersonType|MessageType)-[likeType]->(:PostType),
    connections = []
    graph_m = re.search(
        r"CREATE GRAPH TYPE \w+ STRICT \{(.*?)\}", content, re.DOTALL
    )
    if graph_m:
        # Endpoint type names may contain arbitrary label chars: ':' (multi-
        # label, Neuron:SegmentType), '/' (ORG/GOVType), '&' (App:Animation&
        # ModelingType), etc. Match anything up to the closing ')' so we never
        # have to enumerate special chars; '|' separates alternatives.
        # Edge type names may be IRIs; match anything up to the closing ']'.
        conn_pat = re.compile(r"\(:([^)]+)\)-\[([^\]]+)\]->\(:([^)]+)\)")
        for m in conn_pat.finditer(graph_m.group(1)):
            src_types = m.group(1).split("|")
            edge_type_name = m.group(2)
            dst_types = m.group(3).split("|")
            connections.append((src_types, edge_type_name, dst_types))

    return node_types, edge_types, connections


# ---------------------------------------------------------------------------
# Neo4j writer
# ---------------------------------------------------------------------------

def _ensure_db(driver, schema_db_name: str):
    with driver.session(database="system") as s:
        s.run(f"CREATE DATABASE `{schema_db_name}` IF NOT EXISTS")
    time.sleep(3)


def _labels_cypher(labels: list[str]) -> str:
    return ":".join(f"`{lbl}`" for lbl in labels)


def _props_cypher(mandatory: list[str], optional: list[str]) -> str:
    parts = [f"`{p}`: 'type'" for p in mandatory]
    parts += [f"`{p}`: 'type?'" for p in optional]
    return "{" + ", ".join(parts) + "}" if parts else "{}"


_ABSTRACT = ("ABSTRACT_SRC", "ABSTRACT_DST", "OPEN")


def _is_abstract(labels: list[str]) -> bool:
    return not labels or any(lbl in _ABSTRACT for lbl in labels)


def _alt_type_name(labels: list[str]) -> str:
    """
    Reconstruct the pg-hive type-name reference for a single label set, e.g.
    ['Organisation', 'University'] -> 'Organisation:UniversityType'. This matches
    the per-alternative names used inside the GRAPH TYPE connection patterns.
    """
    return ":".join(labels) + "Type"


def plan_schema(node_types: dict):
    """
    Decide which nodes to store and how each pg-hive type name maps to the stored
    node(s) for edge attachment.

    Each '|'-separated alternative becomes its OWN node. A pg-hive 'union' type
    like 'Organisation:Company | Place:City | Tag' is split into one node per
    alternative ({Organisation, Company}, {Place, City}, {Tag}), each carrying
    the union type's properties. No inheritance (EXTENDS) is inferred.

    When the same label set is described by SEVERAL types (pg-hive emits
    overlapping union types when the graph has few labels: DBpedia yields 17
    types over 5 labels), their property sets are aggregated rather than
    keeping whichever type came first in the file:

      mandatory = intersection of the competing types' mandatory sets
      optional  = union of all their properties, minus the mandatory ones

    This reconstructs what pg-hive stated about that label set without loss.
    Keeping only the first occurrence dropped 139 of 216 property keys on
    dbpedia-a (754 of 958 on dbpedia-b1) and cost 0.15 node-C2.

    Returns:
      nodes   : dict  frozenset(labels) -> {labels, mandatory, optional}
      resolve : dict  type_name -> list[frozenset] endpoints to attach edges to
    """
    collected: dict = {}
    resolve: dict = {}

    for type_name, info in node_types.items():
        endpoints = []
        for alt in info["alternatives"]:
            if _is_abstract(alt):
                continue
            fs = frozenset(alt)
            if fs:
                entry = collected.setdefault(
                    fs, {"labels": list(alt), "mandatory_sets": [],
                         "all_props": set()})
                entry["mandatory_sets"].append(set(info["mandatory"]))
                entry["all_props"] |= set(info["mandatory"]) | set(info["optional"])
            if fs not in endpoints:
                endpoints.append(fs)
            # Each alternative is also referenced by its own reconstructed type
            # name in the GRAPH TYPE connection patterns (e.g. TagType), so map
            # that name to this node too.
            resolve.setdefault(_alt_type_name(alt), []).append(fs)
        # The full (union) type name resolves to all of its alternatives.
        resolve[type_name] = endpoints

    nodes: dict = {}
    for fs, entry in collected.items():
        mandatory = set.intersection(*entry["mandatory_sets"])
        nodes[fs] = {
            "labels": entry["labels"],
            "mandatory": sorted(mandatory),
            "optional": sorted(entry["all_props"] - mandatory),
        }

    return nodes, resolve


def write_to_neo4j(
    uri: str,
    auth,
    schema_db_name: str,
    node_types: dict,
    edge_types: dict,
    connections: list,
):
    nodes, resolve = plan_schema(node_types)

    driver = GraphDatabase.driver(uri, auth=auth)
    _ensure_db(driver, schema_db_name)

    with driver.session(database=schema_db_name) as s:
        s.run("MATCH (n) DETACH DELETE n")

        # -- NodeType nodes --
        # One node per label set, so a label set identifies its node uniquely.
        # The fast path records that node's element id here and reuses it below
        # instead of re-resolving the same MATCH for every edge.
        node_ids: dict = {}
        for fs, info in nodes.items():
            combined = _labels_cypher(info["labels"])
            props = _props_cypher(info["mandatory"], info["optional"])
            if FAST_CONVERT:
                node_ids[fs] = s.run(
                    f"CREATE (n:{combined} {props}) RETURN elementId(n) AS id"
                ).single()["id"]
            else:
                s.run(f"CREATE (n:{combined} {props})")

        # -- EdgeType relationships --
        # (rel type, edge props) -> endpoint element id pairs, for the fast path
        pending: dict = {}
        for src_types, edge_type_name, dst_types in connections:
            edge_info = edge_types.get(edge_type_name, {})
            raw_rel_type = edge_info.get("rel_type", edge_type_name)
            edge_props = _props_cypher(
                edge_info.get("mandatory", []), edge_info.get("optional", []))

            # pg-hive may merge multiple rel types: "PURCHASED | SUPPLIES"
            # Neo4j requires exactly one rel type, so create one MERGE per type
            rel_types = [rt.strip() for rt in raw_rel_type.split("|")]

            # Resolve type names to their stored node(s) (label sets); each name
            # may expand to several alternatives. De-duplicate so repeated names
            # MERGE once.
            src_sets = set()
            for t in src_types:
                src_sets.update(resolve.get(t) or [])
            dst_sets = set()
            for t in dst_types:
                dst_sets.update(resolve.get(t) or [])

            for src_fs in src_sets:
                if src_fs not in nodes:
                    continue
                src_cypher = _labels_cypher(nodes[src_fs]["labels"])
                for dst_fs in dst_sets:
                    if dst_fs not in nodes:
                        continue
                    dst_cypher = _labels_cypher(nodes[dst_fs]["labels"])
                    for rel_type in rel_types:
                        if FAST_CONVERT:
                            # The MATCH below selects the node whose label set
                            # is exactly src_fs / dst_fs -- and exactly one node
                            # was created per label set -- so its element id
                            # identifies the same node the MATCH would find.
                            # Deferred to one UNWIND per (rel type, props).
                            pending.setdefault(
                                (rel_type, edge_props), []).append(
                                    {"s": node_ids[src_fs],
                                     "d": node_ids[dst_fs]})
                        else:
                            s.run(
                                f"MATCH (src:{src_cypher}), (dst:{dst_cypher}) "
                                f"WHERE size(labels(src)) = {len(src_fs)} "
                                f"AND size(labels(dst)) = {len(dst_fs)} "
                                f"MERGE (src)-[:`{rel_type}` {edge_props}]->(dst)"
                            )

        if FAST_CONVERT:
            # MERGE deduplicates per row exactly as it did one statement at a
            # time, so the resulting edge set is unchanged.
            for (rel_type, edge_props), pairs in pending.items():
                query = (
                    "UNWIND $pairs AS pair "
                    "MATCH (src) WHERE elementId(src) = pair.s "
                    "MATCH (dst) WHERE elementId(dst) = pair.d "
                    f"MERGE (src)-[:`{rel_type}` {edge_props}]->(dst)"
                )
                for start in range(0, len(pairs), WRITE_BATCH):
                    s.run(query, pairs=pairs[start:start + WRITE_BATCH])

    driver.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(db_name: str, txt_path: str):
    schema_db_name = f"{db_name}-pg-hive"
    print(f"Parsing: {txt_path}")
    node_types, edge_types, connections = parse_strict_txt(txt_path)
    print(f"  Node types : {len(node_types)}")
    print(f"  Edge types : {len(edge_types)}")
    print(f"  Connections: {len(connections)}")

    print(f"Writing to Neo4j database '{schema_db_name}' ...")
    write_to_neo4j(URI, AUTH, schema_db_name, node_types, edge_types, connections)
    print("Done.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python convert.py <db_name> <txt_path>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
