from __future__ import annotations
from neo4j import GraphDatabase
import os
import sys
import colorama
from typing import Set, List
import math
import time
from collections import defaultdict


colorama.init(autoreset=True)
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))  # noqa


class Entity():
    def __init__(self, labels: Set[str], props: Set[str]):
        if not isinstance(labels, set):
            raise TypeError(f"labels must be a set, but got {type(labels)}")
        if not isinstance(props, set):
            raise TypeError(f"props must be a set, but got {
                            type(props)}")

        self.labels: frozenset = frozenset(labels)
        self.props: frozenset = frozenset(props)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return self.labels == other.labels and self.props == other.props

    def __hash__(self) -> int:
        return hash((self.labels, self.props))

    def __str__(self) -> str:
        return f"{self.labels}::{self.props}"


class NodeType(Entity):
    def __init__(
            self, labels: Set[str],
            props: Set[str],
            incoming_relationships: Set[Entity],
            outgoing_relationships: Set[Entity]
    ):
        if not isinstance(labels, set):
            raise TypeError("labels must be a set")
        if not isinstance(props, set):
            raise TypeError("props must be a set")
        if not isinstance(incoming_relationships, set):
            raise TypeError("incoming_relationships must be a set")
        if not isinstance(outgoing_relationships, set):
            raise TypeError("outgoing_relationships must be a set")

        super().__init__(labels, props)
        self.incoming_relationships = frozenset(incoming_relationships)
        self.outgoing_relationships = frozenset(outgoing_relationships)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, NodeType):
            raise NotImplementedError(
                "Comparison between NodeType and other types is not implemented")
        return (self.labels == other.labels and
                self.props == other.props and
                self.incoming_relationships == other.incoming_relationships and
                self.outgoing_relationships == other.outgoing_relationships)

    def __hash__(self) -> int:
        return hash((self.labels, self.props, self.incoming_relationships, self.outgoing_relationships))

    def __str__(self):
        labels = set(self.labels)
        props = set(self.props)
        incoming = {str(neighbor)
                    for neighbor in set(self.incoming_relationships)}
        outgoing = {str(neighbor)
                    for neighbor in set(self.outgoing_relationships)}

        ret = f"""
NodeType:
    labels: {labels}
    props: {props}
    incoming_relationships: {incoming}
    outgoing_relationships: {outgoing}
        """
        return ret


class EdgeType(Entity):
    def __init__(self, label: str, props: Set[str], src: Entity, dst: Entity):
        if not isinstance(label, str):
            raise TypeError("label must be a str")
        if not isinstance(props, set):
            raise TypeError("props must be a set")
        if not isinstance(src, Entity):
            raise TypeError("src must be a Entity type")
        if not isinstance(dst, Entity):
            raise TypeError("dst must be a Entity type")

        super().__init__({label}, props)
        self.src = src
        self.dst = dst

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, EdgeType):
            raise NotImplementedError(
                "Comparison between EdgeType and other types is not implemented")

        return self.labels == value.labels and \
            self.props == value.props and \
            self.src == value.src and \
            self.dst == value.dst

    def __hash__(self) -> int:
        return hash((self.labels, self.props, self.src, self.dst))

    def __str__(self):
        return f"""
EdgeType:
    type: {self.labels}
    props: {set(self.props)}
    src: {self.src}
    dst: {self.dst}
        """


def create_node_type(node) -> NodeType:
    node_labels: Set[str] = set(node["labels"])
    node_props: Set[str] = set(node["props"])
    incoming_rels: Set[Entity] = set()
    outgoing_rels: Set[Entity] = set()
    for rel in node["inRels"]:
        # rel = TYPE | TYPE:p1:p2:...:pn
        label_and_props = rel.split(":")
        label = {label_and_props[0]}
        if len(label_and_props) == 1:
            incoming_rels.add(Entity(label, set()))
            continue
        rel_props = set(label_and_props[1:])
        incoming_rels.add(Entity(label, set(rel_props)))
    for rel in node["outRels"]:
        # rel = TYPE | TYPE:p1:p2:...:pn
        label_and_props = rel.split(":")
        label = {label_and_props[0]}
        if len(label_and_props) == 1:
            outgoing_rels.add(Entity(label, set()))
            continue
        rel_props = set(label_and_props[1:])
        outgoing_rels.add(Entity(label, set(rel_props)))
    node_type = NodeType(node_labels, node_props, incoming_rels, outgoing_rels)
    return node_type


def create_edge_type(edge) -> EdgeType:
    edge_label: str = edge["label"]
    edge_props: Set[str] = set(edge["props"])
    src_labels: Set[str] = set(edge["srcLabels"])
    src_props: Set[str] = set(edge["srcProps"])
    dst_labels: Set[str] = set(edge["dstLabels"])
    dst_props: Set[str] = set(edge["dstProps"])

    src_node = Entity(src_labels, src_props)
    dst_node = Entity(dst_labels, dst_props)

    edge_type = EdgeType(edge_label, edge_props, src_node, dst_node)
    return edge_type


def get_all_node_types(tx) -> Set[NodeType]:
    node_types: Set[NodeType] = set()
    query = """
    MATCH (n)
    WITH
        apoc.coll.sort(labels(n)) AS nodeLabels,
        apoc.coll.sort(keys(n)) AS nodeProps,
        apoc.coll.sort(
            apoc.coll.toSet(
                [ (n)<-[r]-() | apoc.text.join([type(r)] + apoc.coll.sort(keys(r)), ':') ]
            )
        ) AS inRels,
        apoc.coll.sort(
            apoc.coll.toSet(
                [ (n)-[r]->() | apoc.text.join([type(r)] + apoc.coll.sort(keys(r)), ':') ]
            )
        ) AS outRels
    WITH
        nodeLabels, nodeProps, inRels, outRels,
        apoc.hashing.fingerprint(nodeLabels+nodeProps+inRels+outRels) AS sig
    RETURN
        sig AS signature,
        nodeLabels AS labels,
        nodeProps AS props,
        inRels,
        outRels
    """

    res = tx.run(query)

    for record in res:
        node_types.add(create_node_type(record))

    return node_types


def get_all_edge_types(tx) -> Set[EdgeType]:
    edge_types: Set[EdgeType] = set()

    query = """
    MATCH (src)-[r]->(dst)
    WITH
        type(r) AS relType,
        apoc.coll.sort(keys(r)) AS relProps,
        apoc.coll.sort(labels(src)) AS srcLabels,
        apoc.coll.sort(keys(src)) AS srcProps,
        apoc.coll.sort(labels(dst)) AS dstLabels,
        apoc.coll.sort(keys(dst)) AS dstProps
    WITH
        relType, relProps, srcLabels, srcProps, dstLabels, dstProps,
        apoc.hashing.fingerprint(
            [relType] +
            relProps +
            srcLabels + srcProps +
            dstLabels + dstProps
        ) AS sig
    RETURN
        sig AS signature,
        relType AS label,
        relProps AS props,
        srcLabels, srcProps,
        dstLabels, dstProps
    """

    res = tx.run(query)

    for record in res:
        edge_types.add(create_edge_type(record))

    return edge_types


def count_attribute_freq(node_types, edge_types):
    label_freq = {}
    prop_freq = {}
    for node_type in node_types:
        for label in node_type.labels:
            if label in label_freq:
                label_freq[label] += 1
            else:
                label_freq[label] = 1
        for prop in node_type.props:
            if prop in prop_freq:
                prop_freq[prop] += 1
            else:
                prop_freq[prop] = 1

    for edge_type in edge_types:
        for label in edge_type.labels:
            if label in label_freq:
                label_freq[label] += 1
            else:
                label_freq[label] = 1
        for prop in edge_type.props:
            if prop in prop_freq:
                prop_freq[prop] += 1
            else:
                prop_freq[prop] = 1
    return label_freq, prop_freq


def calc_weighted_jaccard_sim(set1, set2, attr_freq_dict):
    intersection = set1 & set2
    union = set1 | set2
    if len(union) == 0:
        return 1
    numerator = 0
    denominator = 0
    for attr in intersection:
        numerator += 1 / math.sqrt(attr_freq_dict[attr])
    for attr in union:
        denominator += 1 / math.sqrt(attr_freq_dict[attr])
    sim = numerator / denominator
    if 1 < sim < 1.0001:
        sim = 1
    assert 0 <= sim <= 1, f"Similarity must be in [0, 1], but got {sim}"
    return sim


def calc_attr_sim_matrix(
    node_types: Set[NodeType],
    edge_types: Set[EdgeType],
    label_freq: dict,
    prop_freq: dict,
    label_weight,
    prop_weight
):
    def calc_sim_matrix(entities: Set[Entity], label_freq, prop_freq, label_weight, prop_weight, entity_name="Entities"):
        sim_matrix = defaultdict(lambda: defaultdict(float))
        entity_list = list(entities)
        total = len(entity_list)
        progress_interval = max(1, total // 100)

        for i, entity1 in enumerate(entity_list):
            sim_matrix[entity1][entity1] = 1.0

            for entity2 in entity_list[i+1:]:
                label_sim = calc_weighted_jaccard_sim(
                    entity1.labels, entity2.labels, label_freq)
                prop_sim = calc_weighted_jaccard_sim(
                    entity1.props, entity2.props, prop_freq)

                sim = label_weight * label_sim + prop_weight * prop_sim

                sim_matrix[entity1][entity2] = sim
                sim_matrix[entity2][entity1] = sim

            if (i + 1) % progress_interval == 0 or i + 1 == total:
                print(
                    f"{entity_name} similarity calculation progress: {((i + 1)/total)*100:.0f}% ({i + 1}/{total})")

        return sim_matrix

    node_sim_matrix = calc_sim_matrix(
        node_types, label_freq, prop_freq, label_weight, prop_weight, entity_name="Node")

    edge_sim_matrix = calc_sim_matrix(
        edge_types, label_freq, prop_freq, label_weight, prop_weight, entity_name="Edge")

    return node_sim_matrix, edge_sim_matrix


def calc_node_topology_sim(node_type1, node_type2, label_freq, prop_freq) -> float:
    inc1 = node_type1.incoming_relationships
    out1 = node_type1.outgoing_relationships
    inc2 = node_type2.incoming_relationships
    out2 = node_type2.outgoing_relationships

    inc_sim1 = 0
    for i1 in inc1:
        maximum = 0
        for i2 in inc2:
            sim = calc_weighted_jaccard_sim(i1.labels, i2.labels, label_freq) + \
                calc_weighted_jaccard_sim(
                i1.props, i2.props, prop_freq)
            sim /= 2
            if sim > maximum:
                maximum = sim
        assert 0 <= maximum <= 1, f"Similarity must be in [0, 1], but got {
            maximum}"
        inc_sim1 += maximum
    if len(inc1) == 0:
        inc_sim1 = 0
    else:
        inc_sim1 /= len(inc1)
    assert 0 <= inc_sim1 <= 1, f"Similarity must be in [0, 1], but got {
        inc_sim1}"

    inc_sim2 = 0
    for i2 in inc2:
        maximum = 0
        for i1 in inc1:
            sim = calc_weighted_jaccard_sim(i1.labels, i2.labels, label_freq) + \
                calc_weighted_jaccard_sim(
                i1.props, i2.props, prop_freq)
            sim /= 2
            if sim > maximum:
                maximum = sim
        assert 0 <= maximum <= 1, f"Similarity must be in [0, 1], but got {
            maximum}"
        inc_sim2 += maximum
    if len(inc2) == 0:
        inc_sim2 = 0
    else:
        inc_sim2 /= len(inc2)
    assert 0 <= inc_sim2 <= 1, f"Similarity must be in [0, 1], but got {
        inc_sim2}"

    out_sim1 = 0
    for o1 in out1:
        maximum = 0
        for o2 in out2:
            sim = calc_weighted_jaccard_sim(o1.labels, o2.labels, label_freq) +\
                calc_weighted_jaccard_sim(
                o1.props, o2.props, prop_freq)
            sim /= 2
            if sim > maximum:
                maximum = sim
        assert 0 <= maximum <= 1, f"Similarity must be in [0, 1], but got {
            maximum}"
        out_sim1 += maximum
    if len(out1) == 0:
        out_sim1 = 0
    else:
        out_sim1 /= len(out1)
    assert 0 <= out_sim1 <= 1, f"Similarity must be in [0, 1], but got {
        out_sim1}"

    out_sim2 = 0
    for o2 in out2:
        maximum = 0
        for o1 in out1:
            sim = calc_weighted_jaccard_sim(o1.labels, o2.labels, label_freq) +\
                calc_weighted_jaccard_sim(o1.props, o2.props, prop_freq)
            sim /= 2
            if sim > maximum:
                maximum = sim
        assert 0 <= maximum <= 1, f"Similarity must be in [0, 1], but got {
            maximum}"
        out_sim2 += maximum
    if len(out2) == 0:
        out_sim2 = 0
    else:
        out_sim2 /= len(out2)
    assert 0 <= out_sim2 <= 1, f"Similarity must be in [0, 1], but got {
        out_sim2}"

    inc_sim = min(inc_sim1, inc_sim2)
    out_sim = min(out_sim1, out_sim2)
    result = (inc_sim + out_sim) / 2
    assert 0 <= result <= 1
    return result


def calc_edge_topology_sim(edge_type1, edge_type2, label_freq, prop_freq) -> float:
    src1 = edge_type1.src
    dst1 = edge_type1.dst
    src2 = edge_type2.src
    dst2 = edge_type2.dst

    src_sim = calc_weighted_jaccard_sim(src1.labels, src2.labels, label_freq) + calc_weighted_jaccard_sim(
        src1.props, src2.props, prop_freq)
    dst_sim = calc_weighted_jaccard_sim(dst1.labels, dst2.labels, label_freq) + calc_weighted_jaccard_sim(
        dst1.props, dst2.props, prop_freq)
    result = (src_sim + dst_sim) / 4
    assert 0 <= result <= 1
    return result


def calc_topology_sim_matrix(node_types, edge_types, label_freq, prop_freq, topology_weight):
    node_topology_sim_matrix = defaultdict(lambda: defaultdict(float))
    for node_type1 in node_types:
        for node_type2 in node_types:
            if node_type1 == node_type2:
                node_topology_sim_matrix[node_type1][node_type2] = topology_weight * 1
            else:
                node_topology_sim_matrix[node_type1][node_type2] = topology_weight * calc_node_topology_sim(
                    node_type1, node_type2, label_freq, prop_freq)

    edge_topology_sim_matrix = defaultdict(lambda: defaultdict(float))
    for edge_type1 in edge_types:
        for edge_type2 in edge_types:
            if edge_type1 == edge_type2:
                edge_topology_sim_matrix[edge_type1][edge_type2] = topology_weight * 1
            else:
                edge_topology_sim_matrix[edge_type1][edge_type2] = topology_weight * calc_edge_topology_sim(
                    edge_type1, edge_type2, label_freq, prop_freq)
    return node_topology_sim_matrix, edge_topology_sim_matrix


def create_partition(sim_matrix, theta):
    partitions = []

    for entity in sim_matrix:
        if len(partitions) == 0:
            partitions.append({entity})
        else:
            for partition in partitions:
                if any(sim_matrix[entity][entity2] >= theta for entity2 in partition):
                    partition.add(entity)
                    break
            else:
                partitions.append({entity})
    return partitions


def reset_schema(tx):
    query = """
MATCH(n)
DETACH DELETE n
"""
    tx.run(query)


def commit_schema(tx, node_partitions, edge_partitions, db_name):
    for partition in node_partitions:
        all_labels = set()
        all_props = set()
        random_node_type = next(iter(partition))
        mandatory_labels = set(random_node_type.labels)
        mandatory_props = set(random_node_type.props)

        for node_type in partition:
            all_labels = all_labels | node_type.labels
            all_props = all_props | node_type.props
            mandatory_labels = mandatory_labels & node_type.labels
            mandatory_props = mandatory_props & node_type.props

        combined_labels = ":".join(
            f"`{label}`" for label in sorted(all_labels))
        optional_props = all_props - \
            mandatory_props if mandatory_props else set()

        combined_props = ""
        if len(all_props) == 0:
            combined_props = "{}"
        else:
            combined_props = "{"
            for prop in mandatory_props:
                combined_props += f"`{prop}`: 'type', "
            for prop in optional_props:
                combined_props += f"`{prop}`: 'type?', "
            combined_props = combined_props[:-2] + "}"

        query = f"CREATE (n:{combined_labels} {combined_props})"

        tx.run(query)

    for edge_partition in edge_partitions:
        random_edge_type = next(iter(edge_partition))
        all_props = set(random_edge_type.props)
        mandatory_props = set(random_edge_type.props)

        for edge_type in edge_partition:
            all_props = all_props | edge_type.props
            mandatory_props = mandatory_props & edge_type.props

        for edge_type in edge_partition:
            combined_src_labels = ":".join(
                f"`{label}`" for label in sorted(edge_type.src.labels))
            len_src_labels = len(edge_type.src.labels)
            combined_dst_labels = ":".join(
                f"`{label}`" for label in sorted(edge_type.dst.labels))
            len_dst_labels = len(edge_type.dst.labels)
            rel_type = ":".join(sorted(edge_type.labels))

            combined_props = ""
            if len(all_props) == 0:
                combined_props = "{}"
            else:
                combined_props = "{"
                for prop in mandatory_props:
                    combined_props += f"{prop}: 'type', "
                for prop in all_props - mandatory_props:
                    combined_props += f"{prop}: 'type?', "
                combined_props = combined_props[:-2] + "}"

            query = f"""
MATCH(src: {combined_src_labels}), (dst: {combined_dst_labels})
WHERE size(labels(src)) = {len_src_labels} AND size(labels(dst)) = {len_dst_labels}
MERGE(src)-[:`{rel_type}` {combined_props}] -> (dst)
"""
            tx.run(query)

            query = """
MATCH (nt:NodeType)
DETACH DELETE nt
"""
            tx.run(query)


def main(uri, user, pw, db_name, label_weight, prop_weight, topology_weight, theta):

    print("---------------------------------")
    print("Target DB: ", db_name)
    print("l:p:t = ", label_weight, prop_weight, topology_weight)
    print("---------------------------------")

    total_weight = label_weight + prop_weight + topology_weight
    label_weight /= total_weight
    prop_weight /= total_weight
    topology_weight /= total_weight
    assert 1-1e-9 <= label_weight + prop_weight + topology_weight <= 1+1e-9
    assert 0 <= theta <= 1
    data_driver = GraphDatabase.driver(
        uri, auth=(user, pw), database=db_name)

    start = time.time()
    with data_driver.session() as session:
        node_types = session.execute_read(get_all_node_types)
        edge_types = session.execute_read(get_all_edge_types)
    data_driver.close()
    end = time.time()
    print(f"Data loading took {end - start:.2f} seconds.")

    print("Data Loaded.")
    print("Number of Node Types: ", len(node_types))
    print("Number of Edge Types: ", len(edge_types))
    print("---------------------------------")

    label_freq, prop_freq = count_attribute_freq(
        node_types, edge_types)
    node_attr_sim_matrix, edge_attr_sim_matrix = calc_attr_sim_matrix(node_types, edge_types, label_freq,
                                                                      prop_freq, label_weight, prop_weight)

    if topology_weight != 0:
        node_topology_sim_matrix, edge_topology_sim_matrix = calc_topology_sim_matrix(
            node_types, edge_types, label_freq, prop_freq, topology_weight)

    print("Creating Node Sim Matrix...")
    node_sim_matrix = defaultdict(lambda: defaultdict(float))
    for node_type in node_types:
        for node_type2 in node_types:
            if topology_weight == 0:
                node_sim_matrix[node_type][node_type2] = node_attr_sim_matrix[node_type][node_type2]
            else:
                node_sim_matrix[node_type][node_type2] = node_attr_sim_matrix[node_type][node_type2] \
                    + node_topology_sim_matrix[node_type][node_type2]
    print("Done!")
    print("Creating Edge Sim Matrix...")

    edge_sim_matrix = {}
    for edge_type in edge_types:
        edge_sim_matrix[edge_type] = {}
        for edge_type2 in edge_types:
            if topology_weight == 0:
                edge_sim_matrix[edge_type][edge_type2] = edge_attr_sim_matrix[edge_type][edge_type2]
            else:
                edge_sim_matrix[edge_type][edge_type2] = edge_attr_sim_matrix[edge_type][edge_type2] + \
                    edge_topology_sim_matrix[edge_type][edge_type2]

    print("Done!")

    print("Creating Partitions...")

    node_partitions = create_partition(node_sim_matrix, theta)
    edge_partitions = create_partition(edge_sim_matrix, theta)

    print(f"Number of Node Partitions: {len(node_partitions)}")
    print(f"Number of Edge Partitions: {len(edge_partitions)}")

    print("---------------------------------")
    print("Committing Schema...")

    schema_data_driver = GraphDatabase.driver(uri, auth=(user, pw),
                                              database=f"{db_name}-lei")
    with schema_data_driver.session() as session:
        session.execute_write(reset_schema)
        session.execute_write(
            commit_schema, node_partitions, edge_partitions, db_name)
    schema_data_driver.close()

    print("Done!")


if __name__ == "__main__":
    uri = "bolt://localhost:7689"
    user = "neo4j"
    pw = "password"
    db_name = "pokec"
    label_weight = 1
    prop_weight = 1
    topology_weight = 0
    theta = 0.8
    main(uri, user, pw, db_name, label_weight,
         prop_weight, topology_weight, theta)
