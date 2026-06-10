"""F1-score schema evaluation (previous-method baseline).

For each ``(schema_db, gt_db)`` pair both schema graphs are flattened and their
node / edge types are compared by exact set matching to obtain precision /
recall / F1. Properties are merged into a single set per type (mandatory and
optional are not distinguished), matching the previous method.
"""

from typing import FrozenSet, List, Set, Tuple

from . import utils
from .entity_def import EdgeType, NodeType

# Comparison keys merge mandatory and optional into one property set, so two
# types match iff they share the same labels and the same overall property set.
NodeKey = Tuple[FrozenSet[str], FrozenSet[str]]
EdgeKey = Tuple[str, FrozenSet[str], NodeKey, NodeKey]


def _node_key(n: NodeType) -> NodeKey:
    return (n.labels, n.mandatory_props | n.optional_props)


def _edge_key(e: EdgeType) -> EdgeKey:
    return (
        e.label,
        e.mandatory_props | e.optional_props,
        _node_key(e.src_node_type),
        _node_key(e.dst_node_type),
    )


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)
          ) if (precision + recall) > 0 else 0.0
    return precision, recall, f1


def calc_f1_from_types(
    pred_node_types: List[NodeType], pred_edge_types: List[EdgeType],
    gt_node_types: List[NodeType], gt_edge_types: List[EdgeType],
):
    """DB-free F1: predicted schema S* vs ground-truth schema S* (both authored).

    Both schemas are flattened with ``flatten_in_memory`` before matching, then
    node and edge types are compared by exact set matching with all properties
    merged into one set per type (mandatory/optional are not distinguished).
    Returns ``(node_precision, node_recall, node_f1, edge_precision,
    edge_recall, edge_f1)``.
    """
    pred_node_types, pred_edge_types = utils.flatten_in_memory(
        pred_node_types, pred_edge_types)
    gt_node_types, gt_edge_types = utils.flatten_in_memory(
        gt_node_types, gt_edge_types)

    pred_nodes: Set[NodeKey] = {_node_key(n) for n in pred_node_types}
    gt_nodes: Set[NodeKey] = {_node_key(n) for n in gt_node_types}
    pred_edges: Set[EdgeKey] = {_edge_key(e) for e in pred_edge_types}
    gt_edges: Set[EdgeKey] = {_edge_key(e) for e in gt_edge_types}

    node_tp = len(pred_nodes & gt_nodes)
    node_fp = len(pred_nodes - gt_nodes)
    node_fn = len(gt_nodes - pred_nodes)
    edge_tp = len(pred_edges & gt_edges)
    edge_fp = len(pred_edges - gt_edges)
    edge_fn = len(gt_edges - pred_edges)

    node_precision, node_recall, node_f1 = _prf(node_tp, node_fp, node_fn)
    edge_precision, edge_recall, edge_f1 = _prf(edge_tp, edge_fp, edge_fn)

    return (node_precision, node_recall, node_f1,
            edge_precision, edge_recall, edge_f1)


def calc_f1(uri, auth, schema_db_name: str, gt_db_name: str):
    """Compute node/edge precision, recall and F1 for one schema vs its GT.

    Reads both schema graphs from Neo4j. Returns ``None`` when either database
    is missing.
    """
    if not utils.db_exists(uri, auth, schema_db_name):
        print(f"Database {schema_db_name} does not exist.")
        return None
    if not utils.db_exists(uri, auth, gt_db_name):
        print(f"Ground-truth database {gt_db_name} does not exist.")
        return None

    pred_star_nodes, pred_star_edges = utils.get_all_node_and_edge_types_from_schema(
        schema_db_name, uri, auth)
    gt_star_nodes, gt_star_edges = utils.get_all_node_and_edge_types_from_schema(
        gt_db_name, uri, auth)

    result = calc_f1_from_types(
        pred_star_nodes, pred_star_edges, gt_star_nodes, gt_star_edges)
    (node_precision, node_recall, node_f1,
     edge_precision, edge_recall, edge_f1) = result

    print("     | Precision | Recall | F1")
    print(
        f"Node |   {node_precision:.2f}    |  {node_recall:.2f}  | {node_f1:.2f}")
    print(
        f"Edge |   {edge_precision:.2f}    |  {edge_recall:.2f}  | {edge_f1:.2f}")

    return result
