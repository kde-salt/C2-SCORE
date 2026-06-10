import itertools
from neo4j import GraphDatabase
import colorama
import json
import dask.bag as db
from collections import defaultdict
from typing import Set, Tuple

import sys
import os
import math

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))  # noqa


class CombinedNodeLabel:
    def __init__(label_set):
        pass


def get_all_nodes(tx):
    q = "MATCH(n) RETURN count(n) as count"
    result = tx.run(q)
    count = result.single()["count"]

    batch_size = 100000
    iterations = math.ceil(count / batch_size)
    all_nodes = []
    for i in range(iterations):
        skip = i * batch_size
        limit = batch_size
        print(f"Extracting nodes... {i + 1}/{iterations}")
        query = """
        MATCH (n)
        RETURN n
        SKIP $skip
        LIMIT $limit
        """
        result = tx.run(query, skip=skip, limit=limit)
        for record in result:
            node = record["n"]
            labels = node.labels
            labels = sorted(labels)
            labels = ":".join(labels)
            properties = node._properties

            all_nodes.append({labels: properties})

    with open("all_nodes.json", "w") as f:
        json.dump(all_nodes, f, indent=4, default=str)


def get_all_edges(tx):
    q = "MATCH ()-[e]->() RETURN count(e) as count"
    result = tx.run(q)
    count = result.single()["count"]
    batch_size = 100000
    iterations = math.ceil(count / batch_size)
    all_edges = []
    for i in range(iterations):
        skip = i * batch_size
        limit = batch_size
        print(f"Extracting edges... {i + 1}/{iterations}")

        query = """
        MATCH (src)-[e]->(dst)
        RETURN src, e, dst
        SKIP $skip
        LIMIT $limit
        """
        result = tx.run(query, skip=skip, limit=limit)
        for record in result:
            src = record["src"]
            dst = record["dst"]
            edge = record["e"]
            src_labels = src.labels
            dst_labels = dst.labels
            src_labels = sorted(src_labels)
            dst_labels = sorted(dst_labels)
            src_labels = ":".join(src_labels)
            dst_labels = ":".join(dst_labels)
            edge_type = edge.type
            serialized_labels = src_labels + "::" + edge_type + "::" + dst_labels
            edge_properties = edge._properties
            all_edges.append({serialized_labels: edge_properties})

    with open("all_edges.json", "w") as f:
        json.dump(all_edges, f, indent=4, default=str)


def load_json(filename):
    with open(filename, 'r') as f:
        data = json.load(f)
    return data


def map_to_type(record):
    def convert_value(value):
        if isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        else:
            return type(value).__name__

    return {key: convert_value(value) for key, value in record.items()}


def reduce_to_type_group(records):
    grouped_data = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    all_labels = set()
    for record in records:
        for labels, properties in record.items():
            all_labels.add(labels)
            for key, data_type in properties.items():
                grouped_data[labels][key][data_type] += 1
    for labels in all_labels:
        if labels not in grouped_data.keys():
            grouped_data[labels] = defaultdict(lambda: defaultdict(int))
    return dict(grouped_data)


def aggregate_partitions(partitions):
    grouped_data = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    all_labels = set()
    for partition in partitions:
        for labels, properties in partition.items():
            all_labels.add(labels)
            for key, data_type_dct in properties.items():
                for data_type, count in data_type_dct.items():
                    grouped_data[labels][key][data_type] += count
    for labels in all_labels:
        if labels not in grouped_data.keys():
            grouped_data[labels] = defaultdict(lambda: defaultdict(int))

    return dict(grouped_data)


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


def extract_schema(json_data):
    bag = db.from_sequence(json_data)
    mapped = bag.map(map_to_type)
    reduced = mapped.reduction(
        perpartition=lambda records: reduce_to_type_group(records),
        aggregate=lambda partitions: aggregate_partitions(partitions)
    )
    result = reduced.compute()
    schema = judge_mandatory_properties(result)
    return schema


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


def main(uri, user, password, database_name):
    colorama.init(autoreset=True)

    driver = GraphDatabase.driver(uri, auth=(
        user, password), database=database_name)

    with driver.session() as session:
        print("Extracting all nodes...")
        session.execute_read(get_all_nodes)
        print("Extracting all edges...")
        session.execute_read(get_all_edges)
    driver.close()

    nodes = load_json('all_nodes.json')
    edges = load_json('all_edges.json')
    print("Extracteing node schema...")
    node_schema = extract_schema(nodes)
    print("Extracting edge schema...")
    edge_schema = extract_schema(edges)

    driver2 = GraphDatabase.driver(uri, auth=(
        user, password), database=f"{database_name}-schemi")

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

    os.remove('all_nodes.json')
    os.remove('all_edges.json')

    print("Done!")


if __name__ == "__main__":
    BOLT_URI = "bolt://localhost:7689"
    USER_NAME = "neo4j"
    PASSWORD = "password"
    DB_NAME = "sample"

    main(BOLT_URI, USER_NAME, PASSWORD, DB_NAME)
