from neo4j import GraphDatabase
from typing import Tuple, List, DefaultDict, Set, Dict, Any, Optional, FrozenSet
from collections import defaultdict
from .entity_def import NodeType, EdgeType
import numpy as np
import time


def run_write(driver, query, **params):
    """Run a write query inside a managed transaction with automatic retries."""
    with driver.session() as session:
        return session.execute_write(lambda tx: tx.run(query, **params).consume())


# Per-column similarity caches, cleared at the start of each eval_c2 call.
_node_col_cache: Dict[NodeType, np.ndarray] = {}
_edge_col_cache: Dict[EdgeType, np.ndarray] = {}

# Timing accumulators, reset at the start of each eval_c2 call.
_flatten_time_acc: float = 0.0
_score_time_acc: float = 0.0


def get_all_node_and_edge_types_from_instance(db_name: str, uri: str, auth: Tuple[str, str]) -> Tuple[List[NodeType], List[EdgeType]]:
    driver = GraphDatabase.driver(uri, auth=auth, database=db_name)
    try:
        return _get_all_node_and_edge_types_from_instance(driver)
    finally:
        driver.close()


def _get_all_node_and_edge_types_from_instance(driver) -> Tuple[List[NodeType], List[EdgeType]]:
    # (1) Count nodes for each label set
    query1 = """
        MATCH (n)
        WITH labels(n) AS labelSet, COUNT(n) AS cnt
        RETURN labelSet, cnt
    """
    node_label_cnt = defaultdict(int)
    with driver.session() as session:
        result = session.run(query1)
        for record in result:
            label = sorted(list(record["labelSet"]))
            joined_label = ":".join(label)
            node_label_cnt[joined_label] = record["cnt"]

    # (2) Count properties per label set
    query2 = """
        MATCH (n)
        UNWIND keys(n) AS prop
        WITH labels(n) AS labelSet, prop, count(*) AS cnt
        RETURN labelSet, prop, cnt
    """
    node_label_prop_cnt: DefaultDict[str, DefaultDict[str, int]] = defaultdict(
        lambda: defaultdict(int))
    with driver.session() as session:
        result = session.run(query2)
        for record in result:
            label = sorted(list(record["labelSet"]))
            joined_label = ":".join(label)
            prop = record["prop"]
            node_label_prop_cnt[joined_label][prop] = record["cnt"]

    # (3) Identify label sets that have no properties
    no_prop_label: Set[str] = set(
        node_label_cnt.keys()) - set(node_label_prop_cnt.keys())

    # (4) Add those label sets to the property count map
    for label in no_prop_label:
        node_label_prop_cnt[label] = defaultdict(int)

    # (5) Build node types
    node_types: List[NodeType] = []
    for label, prop_dict in node_label_prop_cnt.items():
        labels = frozenset(label.split(":"))
        mandatory_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt == node_label_cnt[label]])
        optional_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt < node_label_cnt[label]])
        node_types.append(NodeType(labels, mandatory_props, optional_props))

    # (6) Count edges per (srcLabel, relType, dstLabel) triple
    query3 = """
        MATCH ()-[r]->()
        WITH type(r) AS relType, labels(startNode(r)) AS srcLabelSet, labels(endNode(r)) AS dstLabelSet, COUNT(r) AS cnt
        RETURN srcLabelSet, relType, dstLabelSet, cnt
    """
    edge_label_cnt = defaultdict(int)
    with driver.session() as session:
        result = session.run(query3)
        for record in result:
            src_label = sorted(list(record["srcLabelSet"]))
            dst_label = sorted(list(record["dstLabelSet"]))
            rel_type = record["relType"]
            joined_label = ":".join(src_label) + "::" + \
                rel_type + "::" + ":".join(dst_label)
            edge_label_cnt[joined_label] = record["cnt"]

    # (7) Count properties per edge triple
    query4 = """
        MATCH ()-[r]->()
        UNWIND keys(r) AS prop
        WITH type(r) AS relType, labels(startNode(r)) AS srcLabelSet, labels(endNode(r)) AS dstLabelSet, prop, count(*) AS cnt
        RETURN srcLabelSet, relType, dstLabelSet, prop, cnt
    """
    edge_label_prop_cnt = defaultdict(lambda: defaultdict(int))
    with driver.session() as session:
        result = session.run(query4)
        for record in result:
            src_label = sorted(list(record["srcLabelSet"]))
            dst_label = sorted(list(record["dstLabelSet"]))
            rel_type = record["relType"]
            joined_label = ":".join(src_label) + "::" + \
                rel_type + "::" + ":".join(dst_label)
            prop = record["prop"]
            edge_label_prop_cnt[joined_label][prop] = record["cnt"]

    # (8) Find edge triples without properties
    no_prop_edge_label = set(edge_label_cnt.keys()) - \
        set(edge_label_prop_cnt.keys())

    # (9) Add them to the property count map
    for label in no_prop_edge_label:
        edge_label_prop_cnt[label] = {}

    # (10) Build edge types
    edge_types: List[EdgeType] = []
    for label, prop_dict in edge_label_prop_cnt.items():
        src_label, rel_type, dst_label = label.split("::")
        src_label = frozenset(src_label.split(":"))
        dst_label = frozenset(dst_label.split(":"))
        mandatory_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt == edge_label_cnt[label]])
        optional_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt < edge_label_cnt[label]])
        src_node_type = next(
            (node_type for node_type in node_types if node_type.labels == src_label), None)
        dst_node_type = next(
            (node_type for node_type in node_types if node_type.labels == dst_label), None)
        if src_node_type is None or dst_node_type is None:
            raise ValueError(
                f"src_node_type or dst_node_type is None: {src_label}::{dst_label}")
        edge_types.append(EdgeType(rel_type, mandatory_props,
                          optional_props, src_node_type, dst_node_type))

    return node_types, edge_types


def get_all_node_and_edge_types_from_schema(db_name: str, uri: str, auth: Tuple[str, str]) -> Tuple[List[NodeType], List[EdgeType]]:
    driver = GraphDatabase.driver(uri, auth=auth, database=db_name)
    try:
        return _get_all_node_and_edge_types_from_schema(driver)
    finally:
        driver.close()


def _get_all_node_and_edge_types_from_schema(driver) -> Tuple[List[NodeType], List[EdgeType]]:
    global _flatten_time_acc
    _t = time.time()

    # (1) Fetch all node types
    query1 = """
    MATCH (n)
    WITH n, CASE WHEN size(keys(n)) = 0 THEN [NULL] ELSE keys(n) END AS props
    UNWIND props AS prop
    WITH elementId(n) AS nodeId, labels(n) AS labelSet, prop, n[prop] AS value
    WITH nodeId, labelSet, collect({ prop: prop, isOptional: coalesce((value ENDS WITH '?'), false) }) AS props
    RETURN
    nodeId,
    labelSet,
    [ p IN props WHERE p.isOptional = false | p.prop ] AS mandatoryProperties,
    [ p IN props WHERE p.isOptional = true  | p.prop ] AS optionalProperties
"""
    node_types: List[NodeType] = []
    with driver.session() as session:
        result = session.run(query1)
        for record in result:
            node_id = record["nodeId"]
            labels = frozenset(record["labelSet"])
            # Drop the placeholder NULL injected for property-less nodes.
            mandatory_props = frozenset(
                p for p in record["mandatoryProperties"] if p is not None)
            if "__src_id" in mandatory_props:
                mandatory_props = frozenset(
                    [p for p in mandatory_props if p != "__src_id"])
            optional_props = frozenset(
                p for p in record["optionalProperties"] if p is not None)
            node_types.append(
                NodeType(labels, mandatory_props, optional_props, node_id))

    # (2) Fetch all edge types
    query2 = """
    MATCH ()-[r]->()
    WITH 
        r,
        CASE WHEN size(keys(r)) = 0 THEN [NULL] ELSE keys(r) END AS props
    UNWIND props AS prop
    WITH 
        elementId(r) AS edgeId,
        type(r) AS edgeLabel,
        prop,
        r[prop] AS value,
        elementId(startNode(r)) AS srcNodeId,
        elementId(endNode(r)) AS dstNodeId
    WITH edgeId, edgeLabel, srcNodeId, dstNodeId, collect({ prop: prop, isOptional: coalesce((value ENDS WITH '?'), false) }) AS props
    RETURN
        edgeId,
        srcNodeId,
        dstNodeId,
        edgeLabel,
        [ p IN props WHERE p.isOptional = false | p.prop ] AS mandatoryProperties,
        [ p IN props WHERE p.isOptional = true  | p.prop ] AS optionalProperties
"""
    edge_types: List[EdgeType] = []
    with driver.session() as session:
        result = session.run(query2)
        for record in result:
            edge_id = record["edgeId"]
            src_id = record["srcNodeId"]
            dst_id = record["dstNodeId"]

            edge_label = record["edgeLabel"]
            # Drop the placeholder NULL injected for property-less edges.
            mandatory_props = frozenset(
                p for p in record["mandatoryProperties"] if p is not None)
            if "__src_id" in mandatory_props:
                mandatory_props = frozenset(
                    [p for p in mandatory_props if p != "__src_id"])
            optional_props = frozenset(
                p for p in record["optionalProperties"] if p is not None)
            has_cardinality_error = (
                "cardinality_error" in mandatory_props or "cardinality_error" in optional_props
            )
            mandatory_props = frozenset(
                p for p in mandatory_props if p != "cardinality_error")
            optional_props = frozenset(
                p for p in optional_props if p != "cardinality_error")
            src_node_type = next(
                (node_type for node_type in node_types if node_type.node_id == src_id), None)
            dst_node_type = next(
                (node_type for node_type in node_types if node_type.node_id == dst_id), None)
            if src_node_type is None or dst_node_type is None:
                raise ValueError(
                    f"src_node_type or dst_node_type is None: {src_id}::{dst_id}")
            edge_types.append(EdgeType(
                edge_label, mandatory_props, optional_props, src_node_type, dst_node_type, edge_id,
                has_cardinality_error=has_cardinality_error))

    _flatten_time_acc += time.time() - _t
    return node_types, edge_types


def dice_sim(a: Set[str], b: Set[str]) -> float:
    # If both sets are empty, treat them as fully similar
    if len(a) == 0 and len(b) == 0:
        return 1.0
    return 2 * len(a & b) / (len(a) + len(b))


def node_sim(node1: NodeType, node2: NodeType, label_w, mandatory_w, optional_w) -> float:
    label_sim = dice_sim(node1.labels, node2.labels)
    if label_sim == 0.0:
        return 0.0
    mandatory_prop_sim = dice_sim(
        node1.mandatory_props, node2.mandatory_props)
    optional_prop_sim = dice_sim(node1.optional_props, node2.optional_props)
    return label_w * label_sim + mandatory_w * mandatory_prop_sim + optional_w * optional_prop_sim


def edge_sim(edge1: EdgeType, edge2: EdgeType, label_w, mandatory_w, optional_w, endpoint_w, cardinality_w=0.0) -> float:
    if edge1.label != edge2.label:
        return 0.0
    if not (edge1.src_node_type.labels & edge2.src_node_type.labels):
        return 0.0
    if not (edge1.dst_node_type.labels & edge2.dst_node_type.labels):
        return 0.0

    src_node_sim = node_sim(
        edge1.src_node_type, edge2.src_node_type, label_w, mandatory_w, optional_w)
    dst_node_sim = node_sim(
        edge1.dst_node_type, edge2.dst_node_type, label_w, mandatory_w, optional_w)
    label_sim = dice_sim({edge1.label}, {edge2.label})
    mandatory_prop_sim = dice_sim(
        edge1.mandatory_props, edge2.mandatory_props)
    optional_prop_sim = dice_sim(edge1.optional_props, edge2.optional_props)
    endpoint_sim = (src_node_sim + dst_node_sim) / 2
    edge_attr_sim = label_w * label_sim + mandatory_w * \
        mandatory_prop_sim + optional_w * optional_prop_sim
    cardinality_sim = 0.0 if edge2.has_cardinality_error else 1.0
    body_w = 1.0 - endpoint_w - cardinality_w
    return endpoint_w * endpoint_sim + body_w * edge_attr_sim + cardinality_w * cardinality_sim


def create_sim_matrix(i_node_types: List[NodeType], i_edge_types: List[EdgeType],
                      s_node_types: List[NodeType], s_edge_types: List[EdgeType],
                      label_w,
                      mandatory_w,
                      optional_w,
                      endpoint_w,
                      cardinality_w=0.0
                      ) -> Tuple[np.ndarray, np.ndarray]:
    global _score_time_acc, _node_col_cache, _edge_col_cache
    _t = time.time()

    n_i_nodes = len(i_node_types)
    n_s_nodes = len(s_node_types)
    if n_i_nodes > 0 and n_s_nodes > 0:
        cols = []
        for s_node in s_node_types:
            if s_node not in _node_col_cache:
                _node_col_cache[s_node] = np.fromiter(
                    (node_sim(i_node, s_node, label_w, mandatory_w, optional_w)
                     for i_node in i_node_types),
                    dtype=float, count=n_i_nodes,
                )
            cols.append(_node_col_cache[s_node])
        node_sim_matrix = np.column_stack(cols)
    else:
        node_sim_matrix = np.zeros((n_i_nodes, n_s_nodes))

    n_i_edges = len(i_edge_types)
    n_s_edges = len(s_edge_types)
    if n_i_edges > 0 and n_s_edges > 0:
        cols = []
        for s_edge in s_edge_types:
            if s_edge not in _edge_col_cache:
                _edge_col_cache[s_edge] = np.fromiter(
                    (edge_sim(i_edge, s_edge, label_w, mandatory_w, optional_w, endpoint_w, cardinality_w)
                     for i_edge in i_edge_types),
                    dtype=float, count=n_i_edges,
                )
            cols.append(_edge_col_cache[s_edge])
        edge_sim_matrix = np.column_stack(cols)
    else:
        edge_sim_matrix = np.zeros((n_i_edges, n_s_edges))

    _score_time_acc += time.time() - _t
    return node_sim_matrix, edge_sim_matrix


def copy_graph(from_db_name: str, to_db_name: str, uri: str, auth: Tuple[str, str]) -> None:
    # Recreate the target database via DDL.
    with GraphDatabase.driver(uri, auth=auth) as system_driver:
        with system_driver.session(database="system") as session:
            session.run(  # type: ignore[arg-type]
                f"CREATE OR REPLACE DATABASE {to_db_name} WAIT").consume()

    with GraphDatabase.driver(uri, auth=auth, database=from_db_name) as source_driver, \
            GraphDatabase.driver(uri, auth=auth, database=to_db_name) as target_driver:

        nodes: List[dict] = []
        # Copy nodes while keeping source IDs in __src_id
        with source_driver.session() as s:
            query_get_nodes = """
                MATCH (n)
                RETURN elementId(n) AS src_id, labels(n) AS labels, properties(n) AS props
            """
            for record in s.run(query_get_nodes):
                labels: List[str] = record["labels"]
                props: Dict[str, str] = record["props"]
                src_id = record["src_id"]
                props["__src_id"] = src_id
                n: Dict[str, Any] = {
                    "labels": labels,
                    "props": props
                }
                nodes.append(n)
        query_node_copy = """
        UNWIND $nodes AS n
        CALL apoc.create.node(n.labels, n.props) YIELD node
        RETURN COUNT(node)
        """
        run_write(target_driver, query_node_copy, nodes=nodes)

        rels: List[dict] = []
        with source_driver.session() as s:
            query_rels = """
                MATCH (a)-[r]->(b)
                RETURN
                    elementId(a) AS start_id,
                    elementId(b) AS end_id,
                    elementId(r) AS rel_id,
                    type(r) AS rel_type,
                    properties(r) AS rel_props
            """
            for record in s.run(query_rels):
                record["rel_props"]["__src_id"] = record["rel_id"]
                rels.append({
                    "start_id": record["start_id"],
                    "end_id": record["end_id"],
                    "rel_type": record["rel_type"],
                    "rel_props": record["rel_props"]
                })

        if rels:
            run_write(target_driver, """
            UNWIND $rels AS rel
            MATCH (start {__src_id: rel.start_id}), (end {__src_id: rel.end_id})
            CALL apoc.create.relationship(start, rel.rel_type, rel.rel_props, end) YIELD rel as r
            RETURN count(r)
            """, rels=rels)


def calc_coverage(sim_matrix: np.ndarray) -> float:
    global _score_time_acc
    _t = time.time()

    num_instance_objects = sim_matrix.shape[0]
    num_schema_objects = sim_matrix.shape[1]
    if num_schema_objects == 0 and num_instance_objects > 0:
        _score_time_acc += time.time() - _t
        return 0.0
    elif num_schema_objects == 0 and num_instance_objects == 0:
        _score_time_acc += time.time() - _t
        return 1.0
    elif num_schema_objects > 0 and num_instance_objects == 0:
        _score_time_acc += time.time() - _t
        return 1.0

    instance_object_matchings = []
    for i in range(sim_matrix.shape[0]):
        j = np.argmax(sim_matrix[i])
        instance_object_matchings.append(sim_matrix[i, j])

    coverage = np.mean(instance_object_matchings)
    _score_time_acc += time.time() - _t
    return coverage


def flatten_in_memory(
    node_types: List[NodeType],
    edge_types: List[EdgeType],
    exclude_node_id: str = None,
    exclude_edge_id: str = None,
) -> Tuple[List[NodeType], List[EdgeType]]:
    global _flatten_time_acc
    _t = time.time()

    if exclude_node_id is not None:
        node_types = [n for n in node_types if n.node_id != exclude_node_id]
        edge_types = [e for e in edge_types
                      if e.src_node_type.node_id != exclude_node_id
                      and e.dst_node_type.node_id != exclude_node_id]
    if exclude_edge_id is not None:
        edge_types = [e for e in edge_types if e.edge_id != exclude_edge_id]

    extends_edges = [e for e in edge_types if e.label == "EXTENDS"]
    non_extends_edges = [e for e in edge_types if e.label != "EXTENDS"]

    # Build parent map: "A EXTENDS B" → parents_of[A.node_id] = [B.node_id, ...]
    parents_of: Dict[str, List[str]] = defaultdict(list)
    for e in extends_edges:
        parents_of[e.src_node_type.node_id].append(e.dst_node_type.node_id)

    # BFS to collect all transitive ancestors for each node
    def _bfs_ancestors(node_id: str) -> List[str]:
        result: List[str] = []
        queue = list(parents_of.get(node_id, []))
        visited: Set[str] = set()
        while queue:
            a = queue.pop(0)
            if a not in visited:
                visited.add(a)
                result.append(a)
                queue.extend(parents_of.get(a, []))
        return result

    ancestors_of: Dict[str, List[str]] = {
        n.node_id: _bfs_ancestors(n.node_id) for n in node_types}

    # Inverse: descendants of each node
    descendants_of: Dict[str, List[str]] = defaultdict(list)
    for node_id, ancs in ancestors_of.items():
        for a_id in ancs:
            descendants_of[a_id].append(node_id)

    # Propagate labels and properties from ancestors to descendants.
    labels_of: Dict[str, set] = {n.node_id: set(n.labels) for n in node_types}
    mandatory_of: Dict[str, set] = {n.node_id: set(
        n.mandatory_props) for n in node_types}
    optional_of: Dict[str, set] = {n.node_id: set(
        n.optional_props) for n in node_types}

    for node_id, anc_ids in ancestors_of.items():
        for anc_id in anc_ids:
            labels_of[node_id] |= labels_of[anc_id]
            existing = mandatory_of[node_id] | optional_of[node_id]
            for prop in mandatory_of[anc_id]:
                if prop not in existing:
                    mandatory_of[node_id].add(prop)
                    existing.add(prop)
            for prop in optional_of[anc_id]:
                if prop not in existing:
                    optional_of[node_id].add(prop)
                    existing.add(prop)

    new_node_by_id: Dict[str, NodeType] = {
        n.node_id: NodeType(
            frozenset(labels_of[n.node_id]),
            frozenset(mandatory_of[n.node_id]),
            frozenset(optional_of[n.node_id]),
            n.node_id,
        )
        for n in node_types
    }

    # Propagate edges from ancestors to descendants. The dedup key includes
    # properties so edges sharing (src, label, dst) but differing in properties
    # stay distinct.
    seen: Set[Tuple[str, str, str, FrozenSet[str], FrozenSet[str]]] = set()
    new_edges: List[EdgeType] = []

    def _add_edge(label: str, mandatory, optional, src_id: str, dst_id: str, has_cardinality_error: bool = False) -> None:
        m = frozenset(mandatory)
        o = frozenset(optional)
        key = (src_id, label, dst_id, m, o)
        if key not in seen:
            seen.add(key)
            new_edges.append(EdgeType(
                label, m, o,
                new_node_by_id[src_id], new_node_by_id[dst_id],
                has_cardinality_error=has_cardinality_error,
            ))

    # Seed with the original non-EXTENDS edges.
    for e in non_extends_edges:
        _add_edge(e.label, e.mandatory_props, e.optional_props,
                  e.src_node_type.node_id, e.dst_node_type.node_id, e.has_cardinality_error)

    # flatten2 (outgoing) + flatten3 (incoming) — skip self-loops on ancestor
    for desc_id, anc_ids in ancestors_of.items():
        for anc_id in anc_ids:
            for e in non_extends_edges:
                src_id = e.src_node_type.node_id
                dst_id = e.dst_node_type.node_id
                if src_id == anc_id and dst_id != anc_id:
                    _add_edge(e.label, e.mandatory_props, e.optional_props,
                              desc_id, dst_id, e.has_cardinality_error)
                if dst_id == anc_id and src_id != anc_id:
                    _add_edge(e.label, e.mandatory_props, e.optional_props,
                              src_id, desc_id, e.has_cardinality_error)

    # flatten4: propagate self-loops from ancestors to the full clan
    for n in node_types:
        anc_id = n.node_id
        if not descendants_of[anc_id]:
            continue
        self_loops = [e for e in non_extends_edges
                      if e.src_node_type.node_id == anc_id and e.dst_node_type.node_id == anc_id]
        if not self_loops:
            continue
        clan = descendants_of[anc_id] + [anc_id]
        for sl in self_loops:
            for n1_id in clan:
                for n2_id in clan:
                    _add_edge(sl.label, sl.mandatory_props, sl.optional_props,
                              n1_id, n2_id, sl.has_cardinality_error)

    _flatten_time_acc += time.time() - _t
    return list(new_node_by_id.values()), new_edges


def calc_node_concision(
    instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
    original_node_coverage: float, original_edge_coverage: float, flatten_edge_num: int,
    label_w, mandatory_w, optional_w, endpoint_w, gamma,
    star_node_types: List[NodeType], star_edge_types: List[EdgeType], cardinality_w=0.0
):
    num_instance_nodes = len(instance_node_types)
    num_schema_nodes = len(star_node_types)
    if num_schema_nodes == 0:
        return 1.0
    elif num_schema_nodes > 0 and num_instance_nodes == 0:
        return 0.0

    NODE_THETA = gamma * original_node_coverage / num_schema_nodes
    if flatten_edge_num == 0:
        EDGE_THETA = 1.0
    else:
        EDGE_THETA = gamma * original_edge_coverage / flatten_edge_num
    cnt = 0
    for node_type in star_node_types:
        node_id = node_type.node_id
        new_schema_node_types, new_schema_edge_types = flatten_in_memory(
            star_node_types, star_edge_types, exclude_node_id=node_id)

        node_sim_matrix, new_schema_edge_types = create_sim_matrix(
            instance_node_types, instance_edge_types, new_schema_node_types, new_schema_edge_types,
            label_w, mandatory_w, optional_w, endpoint_w, cardinality_w,
        )

        new_node_coverage = 0.0 if node_sim_matrix.shape[1] == 0 else calc_coverage(
            node_sim_matrix)
        new_edge_coverage = 0.0 if new_schema_edge_types.shape[1] == 0 else calc_coverage(
            new_schema_edge_types)

        node_coverage_loss = original_node_coverage - new_node_coverage
        edge_coverage_loss = original_edge_coverage - new_edge_coverage

        if node_coverage_loss < NODE_THETA and edge_coverage_loss < EDGE_THETA:
            cnt += 1

    return 1 - cnt / num_schema_nodes


def calc_edge_concision(
        instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
        original_node_coverage: float, original_edge_coverage: float, flatten_edge_num: int,
        label_w, mandatory_w, optional_w, endpoint_w, gamma,
        star_node_types: List[NodeType], star_edge_types: List[EdgeType],
        flatten_edge_sim_matrix: np.ndarray, cardinality_w=0.0
) -> float:
    global _score_time_acc
    num_instance_edges = len(instance_edge_types)
    num_schema_edges = len(star_edge_types)
    if num_schema_edges == 0:
        return 1.0
    elif num_schema_edges > 0 and num_instance_edges == 0:
        return 0.0

    EDGE_THETA = 1.0 if flatten_edge_num == 0 else gamma * \
        original_edge_coverage / flatten_edge_num

    # No EXTENDS edges: removing an edge cannot change node types, so coverage
    # after removal is read off the already-flattened edge similarity matrix.
    # Duplicate S* edges (same (src, label, dst)) collapse on flatten and are
    # redundant by definition; unique edges defer to the column-deletion result.
    if not any(e.label == "EXTENDS" for e in star_edge_types):
        full_edge_mat = flatten_edge_sim_matrix
        n_flat_edges = full_edge_mat.shape[1]
        if n_flat_edges == 0:
            return 1.0

        def _edge_key(e: EdgeType) -> Tuple[str, str, str]:
            return (e.src_node_type.node_id, e.label, e.dst_node_type.node_id)

        # How many S* edges map to each flattened key, and each key's column
        # index (first occurrence in star order = flatten's column order).
        key_count: Dict[Tuple[str, str, str], int] = {}
        col_of_key: Dict[Tuple[str, str, str], int] = {}
        for e in star_edge_types:
            k = _edge_key(e)
            key_count[k] = key_count.get(k, 0) + 1
            if k not in col_of_key:
                col_of_key[k] = len(col_of_key)

        # Redundancy of each flattened column: does deleting it keep coverage?
        col_redundant: List[bool] = [False] * n_flat_edges
        for i in range(n_flat_edges):
            _t = time.time()
            reduced = np.delete(full_edge_mat, i, axis=1)
            _score_time_acc += time.time() - _t
            new_edge_cov = 0.0 if reduced.shape[1] == 0 else calc_coverage(
                reduced)
            col_redundant[i] = (original_edge_coverage -
                                new_edge_cov < EDGE_THETA)

        cnt = 0
        for e in star_edge_types:
            k = _edge_key(e)
            if key_count[k] > 1 or col_redundant[col_of_key[k]]:
                cnt += 1
        return 1 - cnt / len(star_edge_types)

    # EXTENDS path: re-flatten per iteration to capture inheritance cascades.
    # EXTENDS edges are structural, so they are excluded from concision entirely.
    candidate_edges = [e for e in star_edge_types if e.label != "EXTENDS"]
    num_candidate_edges = len(candidate_edges)
    if num_candidate_edges == 0:
        return 1.0
    num_star_nodes = len(star_node_types)
    NODE_THETA = gamma * original_node_coverage / \
        num_star_nodes if num_star_nodes > 0 else 1.0
    cnt = 0
    for edge_type in candidate_edges:
        new_schema_node_types, new_schema_edge_types = flatten_in_memory(
            star_node_types, star_edge_types, exclude_edge_id=edge_type.edge_id)
        node_sim_matrix, edge_sim_matrix = create_sim_matrix(
            instance_node_types, instance_edge_types, new_schema_node_types, new_schema_edge_types,
            label_w, mandatory_w, optional_w, endpoint_w, cardinality_w,
        )
        new_node_coverage = calc_coverage(node_sim_matrix)
        new_edge_coverage = 0.0 if edge_sim_matrix.shape[1] == 0 else calc_coverage(
            edge_sim_matrix)
        if original_node_coverage - new_node_coverage < NODE_THETA and original_edge_coverage - new_edge_coverage < EDGE_THETA:
            cnt += 1

    return 1 - cnt / num_candidate_edges


def log_error(log_filename, timestamp, instance_db_name, method, alpha, beta, gamma, err_msg):
    with open(log_filename, "a") as f:
        f.write(
            f"{timestamp},{instance_db_name},{method},{alpha},{beta},{gamma},{err_msg}\n")


def db_exists(uri, auth, db_name):
    with GraphDatabase.driver(uri, auth=auth) as driver:
        with driver.session(database="system") as session:
            result = session.run("SHOW DATABASES")
            db_list = [record["name"] for record in result]
            return db_name in db_list


def eval_c2(uri, auth, instance_db_name, schema_db_name, label_w, mandatory_w, optional_w, endpoint_w, gamma, include_cardinality=False):
    global _flatten_time_acc, _score_time_acc
    assert label_w + mandatory_w + optional_w == 1
    assert 0.0 <= endpoint_w <= 1.0

    _flatten_time_acc = 0.0
    _score_time_acc = 0.0
    _node_col_cache.clear()
    _edge_col_cache.clear()

    eff_endpoint_w = 1 / 3 if include_cardinality else endpoint_w
    eff_cardinality_w = 1 / 3 if include_cardinality else 0.0

    t0 = time.time()
    instance_node_types, instance_edge_types = get_all_node_and_edge_types_from_instance(
        instance_db_name, uri, auth)
    abs_time = time.time() - t0
    t1 = time.time()

    if not db_exists(uri, auth, schema_db_name):
        print(f"Database {schema_db_name} does not exist.")
        return (None, None, None, None, None, None,
                abs_time, None, None, None)

    star_node_types, star_edge_types = get_all_node_and_edge_types_from_schema(
        schema_db_name, uri, auth)
    schema_node_types, schema_edge_types = flatten_in_memory(
        star_node_types, star_edge_types)

    node_sim_matrix, edge_sim_matrix = create_sim_matrix(
        instance_node_types, instance_edge_types, schema_node_types, schema_edge_types,
        label_w, mandatory_w, optional_w, eff_endpoint_w, eff_cardinality_w)

    node_coverage = calc_coverage(node_sim_matrix)
    edge_coverage = calc_coverage(edge_sim_matrix)

    flatten_edge_num = edge_sim_matrix.shape[1]

    node_concision = calc_node_concision(
        instance_node_types, instance_edge_types,
        node_coverage, edge_coverage, flatten_edge_num,
        label_w, mandatory_w, optional_w, eff_endpoint_w, gamma,
        star_node_types, star_edge_types, cardinality_w=eff_cardinality_w)

    edge_concision = calc_edge_concision(
        instance_node_types=instance_node_types,
        instance_edge_types=instance_edge_types,
        original_node_coverage=node_coverage,
        original_edge_coverage=edge_coverage,
        flatten_edge_num=flatten_edge_num,
        label_w=label_w,
        mandatory_w=mandatory_w,
        optional_w=optional_w,
        endpoint_w=eff_endpoint_w,
        gamma=gamma,
        star_node_types=star_node_types,
        star_edge_types=star_edge_types,
        flatten_edge_sim_matrix=edge_sim_matrix,
        cardinality_w=eff_cardinality_w)

    node_c2 = 2 * (node_coverage * node_concision) / (node_coverage +
                                                      node_concision) if (node_coverage + node_concision) > 0 else 0.0
    edge_c2 = 2 * (edge_coverage * edge_concision) / (edge_coverage +
                                                      edge_concision) if (edge_coverage + edge_concision) > 0 else 0.0

    phase2_time = time.time() - t1
    other_time = phase2_time - _flatten_time_acc - _score_time_acc

    return (node_coverage, edge_coverage, node_concision, edge_concision,
            node_c2, edge_c2, abs_time,
            _flatten_time_acc, _score_time_acc, other_time)


def eval_c2_from_types(
    instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
    star_node_types: List[NodeType], star_edge_types: List[EdgeType],
    label_w, mandatory_w, optional_w, endpoint_w, gamma, include_cardinality=False,
):
    """DB-free variant of eval_c2.

    Both the instance types and the schema S* are supplied as pre-loaded
    Python objects, so this performs no database access. Used by experiment 2,
    which reads instance/GT once per dataset and mutates S* in memory per trial.
    Returns the six scores only (no timing breakdown).
    """
    assert label_w + mandatory_w + optional_w == 1
    assert 0.0 <= endpoint_w <= 1.0

    _node_col_cache.clear()
    _edge_col_cache.clear()

    eff_endpoint_w = 1 / 3 if include_cardinality else endpoint_w
    eff_cardinality_w = 1 / 3 if include_cardinality else 0.0

    schema_node_types, schema_edge_types = flatten_in_memory(
        star_node_types, star_edge_types)

    node_sim_matrix, edge_sim_matrix = create_sim_matrix(
        instance_node_types, instance_edge_types, schema_node_types, schema_edge_types,
        label_w, mandatory_w, optional_w, eff_endpoint_w, eff_cardinality_w)

    node_coverage = calc_coverage(node_sim_matrix)
    edge_coverage = calc_coverage(edge_sim_matrix)

    flatten_edge_num = edge_sim_matrix.shape[1]

    node_concision = calc_node_concision(
        instance_node_types, instance_edge_types,
        node_coverage, edge_coverage, flatten_edge_num,
        label_w, mandatory_w, optional_w, eff_endpoint_w, gamma,
        star_node_types, star_edge_types, cardinality_w=eff_cardinality_w)

    edge_concision = calc_edge_concision(
        instance_node_types=instance_node_types,
        instance_edge_types=instance_edge_types,
        original_node_coverage=node_coverage,
        original_edge_coverage=edge_coverage,
        flatten_edge_num=flatten_edge_num,
        label_w=label_w,
        mandatory_w=mandatory_w,
        optional_w=optional_w,
        endpoint_w=eff_endpoint_w,
        gamma=gamma,
        star_node_types=star_node_types,
        star_edge_types=star_edge_types,
        flatten_edge_sim_matrix=edge_sim_matrix,
        cardinality_w=eff_cardinality_w)

    node_c2 = 2 * (node_coverage * node_concision) / (node_coverage +
                                                      node_concision) if (node_coverage + node_concision) > 0 else 0.0
    edge_c2 = 2 * (edge_coverage * edge_concision) / (edge_coverage +
                                                      edge_concision) if (edge_coverage + edge_concision) > 0 else 0.0

    return (node_coverage, edge_coverage, node_concision, edge_concision, node_c2, edge_c2)


def exec_cypher_query(uri: str, auth: Tuple[str, str], db_name: str, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    results = []
    with GraphDatabase.driver(uri, auth=auth, database=db_name) as driver:
        with driver.session() as session:
            result = session.run(query, parameters=params or {})
            for record in result:
                results.append(record.data())
    return results
