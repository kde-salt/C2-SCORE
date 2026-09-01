import itertools
from neo4j import GraphDatabase
import colorama
from collections import defaultdict

import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))  # noqa

from schema_extraction.progress import Progress  # noqa: E402

# Mapping from Cypher valueType() names to the Python type names the original
# implementation recorded. The original serialized every property through
# json.dump(default=str) and re-loaded it before applying type(value).__name__,
# so JSON-native types kept their Python names while everything else collapsed:
# temporal values became "str" (via default=str) and Duration / Point became
# "list" (both are tuple subclasses, so json.dump encoded them as arrays
# without ever calling default=). This table reproduces that behavior exactly.
_VALUE_TYPE_MAP = {
    "INTEGER": "int",
    "FLOAT": "float",
    "STRING": "str",
    "BOOLEAN": "bool",
    "DATE": "str",
    "LOCAL TIME": "str",
    "ZONED TIME": "str",
    "LOCAL DATETIME": "str",
    "ZONED DATETIME": "str",
    "DURATION": "list",
    "POINT": "list",
}


def _map_value_type(value_type: str) -> str:
    vt = value_type.removesuffix(" NOT NULL")
    if vt.startswith("LIST<"):
        return "list"
    try:
        return _VALUE_TYPE_MAP[vt]
    except KeyError:
        # Refuse to guess: an unmapped type would silently change the schema.
        raise ValueError(
            f"unmapped Cypher valueType {value_type!r}; extend _VALUE_TYPE_MAP "
            "after checking how json.dump(default=str) serialized it")


def aggregate_node_schema(driver):
    """Server-side replacement for get_all_nodes + extract_schema (nodes).

    Returns the same 3-level structure as the previous client-side reduction:
    {labels_key: {prop_key: {type_name: count}}}, where labels_key is the
    ':'-joined sorted label set (empty string for label-less nodes).
    """
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    with driver.session() as session:
        # Label sets first, so property-less label sets are still represented.
        progress = Progress("schemi:aggregate-node-labels")
        result = session.run("MATCH (n) RETURN labels(n) AS ls, count(n) AS cnt")
        for record in result:
            labels_key = ":".join(sorted(record["ls"]))
            grouped[labels_key]  # touch: creates the (possibly empty) entry
            progress.tick()
        progress.done()

        progress = Progress("schemi:aggregate-node-props")
        result = session.run("""
            MATCH (n)
            UNWIND keys(n) AS k
            RETURN labels(n) AS ls, k, valueType(n[k]) AS vt, count(*) AS cnt
        """)
        for record in result:
            labels_key = ":".join(sorted(record["ls"]))
            type_name = _map_value_type(record["vt"])
            grouped[labels_key][record["k"]][type_name] += record["cnt"]
            progress.tick()
        progress.done()
    return dict(grouped)


def aggregate_edge_schema(driver):
    """Server-side replacement for get_all_edges + extract_schema (edges).

    Keys have the same 'src::type::dst' shape as the old serialized_labels.
    """
    grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    with driver.session() as session:
        progress = Progress("schemi:aggregate-edge-patterns")
        result = session.run("""
            MATCH (src)-[e]->(dst)
            RETURN labels(src) AS sl, type(e) AS t, labels(dst) AS dl, count(e) AS cnt
        """)
        for record in result:
            key = (":".join(sorted(record["sl"])) + "::" + record["t"]
                   + "::" + ":".join(sorted(record["dl"])))
            grouped[key]
            progress.tick()
        progress.done()

        progress = Progress("schemi:aggregate-edge-props")
        result = session.run("""
            MATCH (src)-[e]->(dst)
            UNWIND keys(e) AS k
            RETURN labels(src) AS sl, type(e) AS t, labels(dst) AS dl,
                   k, valueType(e[k]) AS vt, count(*) AS cnt
        """)
        for record in result:
            key = (":".join(sorted(record["sl"])) + "::" + record["t"]
                   + "::" + ":".join(sorted(record["dl"])))
            type_name = _map_value_type(record["vt"])
            grouped[key][record["k"]][type_name] += record["cnt"]
            progress.tick()
        progress.done()
    return dict(grouped)


def judge_mandatory_properties(map_reduced_data):
    res = defaultdict(lambda: defaultdict(str))
    for labels, properties in map_reduced_data.items():
        if len(properties) == 0:
            res[labels] = {}
            continue
        prop_key_count = defaultdict(int)
        for key, data_type_dct in properties.items():
            prop_key_count[key] = sum(data_type_dct.values())
        max_freq_count = max(prop_key_count.values())
        for key, data_type_dct in properties.items():
            data_types_list = list(data_type_dct.keys())
            data_types_list.sort()
            assert len(data_types_list) >= 1
            if len(data_types_list) >= 2:
                combined_data_type = f"({'+'.join(data_types_list)})"
            else:
                combined_data_type = data_types_list[0]
            if prop_key_count[key] != max_freq_count:
                combined_data_type += "?"
            res[labels][key] = combined_data_type
    return res


def reset_schema(tx):
    query = """
    MATCH (n)
    DETACH DELETE n;
    """
    tx.run(query)


def commit_node_types(tx, schema):
    node_list = []
    for labels, prop in schema.items():
        label_list = sorted(labels.split(":"))
        node_list.append({
            "labels": label_list,
            "props": prop
        })

    print(f"Total nodes to create: {len(node_list)}")

    query = """
UNWIND $nodes AS node
CALL apoc.create.node(node.labels, node.props) YIELD node AS n
RETURN count(n)
"""
    tx.run(query, nodes=node_list)

    created_labels_escaped = {
        ":".join(f"`{l}`" for l in n["labels"]) for n in node_list}
    return created_labels_escaped


def commit_edge_types(tx, schema):
    edge_list = []
    for src_type_dst, rel_prop in schema.items():
        src, edge_type, dst = src_type_dst.split("::")
        src_labels = sorted(src.split(":"))
        dst_labels = sorted(dst.split(":"))
        src_label_len = len(src_labels)
        dst_label_len = len(dst_labels)
        edge_list.append({
            "src_labels": src_labels,
            "dst_labels": dst_labels,
            "src_label_len": src_label_len,
            "dst_label_len": dst_label_len,
            "edge_type": edge_type,
            "props": rel_prop
        })

    print(f"Total edges to process: {len(edge_list)}")

    query = """
    UNWIND $edges AS edge
    MATCH (src)
    WHERE all(lbl IN edge.src_labels WHERE lbl IN labels(src))
    AND size(labels(src)) = edge.src_label_len
    MATCH (dst)
    WHERE all(lbl IN edge.dst_labels WHERE lbl IN labels(dst))
    AND size(labels(dst)) = edge.dst_label_len
    CALL apoc.create.relationship(src, edge.edge_type, edge.props, dst) YIELD rel
    RETURN count(rel)
    """
    tx.run(query, edges=edge_list)


def commit_super_node_types(tx, node_schema, created_node_labels_escaped):
    label_keys = list(node_schema.keys())
    label_pairs = list(itertools.combinations(label_keys, 2))
    total_pairs = len(label_pairs)
    print(f"Total label pairs to process: {total_pairs}")

    contain_list = []
    parent_exist_list = []
    parent_not_exist_list = []

    cnt = 0
    for label1, label2 in label_pairs:
        cnt += 1
        if total_pairs >= 1000 and cnt % (total_pairs // 100) == 0:
            percent = cnt / total_pairs * 100
            print(f"{percent:.0f}% processed ({cnt}/{total_pairs})")

        set1 = set(label1.split(":"))
        set2 = set(label2.split(":"))
        intersection = set1 & set2
        if not intersection:
            continue

        # A. one label set contains the other
        if set1 < set2 or set1 > set2:
            if set1 < set2:
                src_labels = sorted(set2)
                dst_labels = sorted(set1)
            else:
                src_labels = sorted(set1)
                dst_labels = sorted(set2)
            contain_list.append({
                "src_labels": src_labels,
                "dst_labels": dst_labels,
                "src_len": len(src_labels),
                "dst_len": len(dst_labels),
            })
            continue

        # B. label sets overlap but neither contains the other
        parent_labels = sorted(intersection)
        label1_labels = sorted(set1)
        label2_labels = sorted(set2)
        parent_label_escaped = ":".join(f"{l}" for l in parent_labels)
        record = {
            "child1_labels": label1_labels,
            "child2_labels": label2_labels,
            "child1_len": len(label1_labels),
            "child2_len": len(label2_labels),
            "parent_labels": parent_labels,
            "parent_len": len(parent_labels),
        }
        if parent_label_escaped in created_node_labels_escaped:
            parent_exist_list.append(record)
        else:
            created_node_labels_escaped.add(parent_label_escaped)
            parent_not_exist_list.append(record)

    # UNWIND query for the containment case
    query_contain = """
    UNWIND $pairs AS pair
    MATCH (src)
    WHERE all(lbl IN pair.src_labels WHERE lbl IN labels(src)) AND size(labels(src)) = pair.src_len
    MATCH (dst)
    WHERE all(lbl IN pair.dst_labels WHERE lbl IN labels(dst)) AND size(labels(dst)) = pair.dst_len
    AND src <> dst
    MERGE (src)-[:EXTENDS]->(dst)
"""
    if contain_list:
        tx.run(query_contain, pairs=contain_list)

    # UNWIND query when the parent node does not yet exist
    query_parent_not_exist = """
    UNWIND $pairs AS pair
    MATCH (child1)
    WHERE all(lbl IN pair.child1_labels WHERE lbl IN labels(child1)) AND size(labels(child1)) = pair.child1_len
    MATCH (child2)
    WHERE all(lbl IN pair.child2_labels WHERE lbl IN labels(child2)) AND size(labels(child2)) = pair.child2_len
    CREATE (parent)
    WITH child1, child2, parent, pair
    CALL apoc.create.addLabels(parent, pair.parent_labels) YIELD node AS parent2
    WITH parent2 AS parent, child1, child2, pair
    WHERE child1 <> parent AND child2 <> parent
    MERGE (child1)-[:EXTENDS]->(parent)
    MERGE (child2)-[:EXTENDS]->(parent)
"""
    if parent_not_exist_list:
        tx.run(query_parent_not_exist, pairs=parent_not_exist_list)

    # UNWIND query when the parent node already exists
    query_parent_exist = """
    UNWIND $pairs AS pair
    MATCH (child1)
    WHERE all(lbl IN pair.child1_labels WHERE lbl IN labels(child1)) AND size(labels(child1)) = pair.child1_len
    MATCH (child2)
    WHERE all(lbl IN pair.child2_labels WHERE lbl IN labels(child2)) AND size(labels(child2)) = pair.child2_len
    MATCH (parent)
    WHERE all(lbl IN pair.parent_labels WHERE lbl IN labels(parent)) AND size(labels(parent)) = pair.parent_len
    AND child1 <> parent AND child2 <> parent
    MERGE (child1)-[:EXTENDS]->(parent)
    MERGE (child2)-[:EXTENDS]->(parent)
"""
    if parent_exist_list:
        tx.run(query_parent_exist, pairs=parent_exist_list)

    # query to remove redundant labels
    query_remove = """
    MATCH (child)-[:EXTENDS]->(parent)
    WITH child, labels(parent) AS labelsToRemove, keys(parent) AS propsToRemove
    CALL apoc.create.removeLabels(child, labelsToRemove) YIELD node
    FOREACH (key IN propsToRemove | REMOVE node[key])
    RETURN node
    """
    tx.run(query_remove)


def ensure_schema_db(uri, user, password, schema_db_name):
    """Create the output schema DB if it does not exist yet (same pattern as
    pg_hive/convert.py and import_dumps.sh)."""
    with GraphDatabase.driver(uri, auth=(user, password)) as driver:
        with driver.session(database="system") as session:
            session.run(
                f"CREATE DATABASE `{schema_db_name}` IF NOT EXISTS WAIT").consume()


def main(uri, user, password, database_name, schema_db_name=None):
    colorama.init(autoreset=True)
    if schema_db_name is None:
        schema_db_name = f"{database_name}-schemi"

    driver = GraphDatabase.driver(uri, auth=(
        user, password), database=database_name)

    print("Aggregating node schema...")
    node_type_counts = aggregate_node_schema(driver)
    print("Aggregating edge schema...")
    edge_type_counts = aggregate_edge_schema(driver)
    driver.close()

    node_schema = judge_mandatory_properties(node_type_counts)
    edge_schema = judge_mandatory_properties(edge_type_counts)

    ensure_schema_db(uri, user, password, schema_db_name)
    driver2 = GraphDatabase.driver(uri, auth=(
        user, password), database=schema_db_name)

    with driver2.session() as session:
        session.execute_write(reset_schema)
        print("Creating node types...")
        created_node_labels_escaped = session.execute_write(
            commit_node_types, node_schema)
        print("Creating edge types...")
        session.execute_write(commit_edge_types, edge_schema)
        session.execute_write(commit_super_node_types,
                              node_schema, created_node_labels_escaped)
    driver2.close()

    print("Done!")
