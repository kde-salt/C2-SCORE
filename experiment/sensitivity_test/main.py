from ..common import utils
from ..common.entity_def import NodeType, EdgeType
from ..common.eval_f1 import calc_f1_from_types
from datetime import datetime
from typing import Dict, List, Set, Tuple
import itertools
import random
import csv
import os

URI = "bolt://localhost:7687"
AUTH = ("neo4j", "password")

NODE_ERROR_TYPES = (
    "node_type_missing",
    "node_label_missing",
    "node_property_missing",
    "node_duplicate",
)

EDGE_ERROR_TYPES = (
    "edge_type_missing",
    "edge_property_missing",
    "edge_duplicate",
    "edge_direction_swapped",
    "edge_cardinality_error",
)

EDGE_ERROR_TYPES_NO_CARDINALITY = (
    "edge_type_missing",
    "edge_property_missing",
    "edge_duplicate",
    "edge_direction_swapped",
)

ALL_ERROR_TYPES = NODE_ERROR_TYPES + EDGE_ERROR_TYPES

# Property-missing errors are injected by ratio (10%-50% of the schema's total
# property count) instead of a fixed 1-5 count. The `num_errors` value (1-5) is
# treated as the ratio level: level i -> i * 10%.
PROPERTY_ERROR_TYPES = ("node_property_missing", "edge_property_missing")

SCHEMAS = {
    "ldbc-gt": True,
    "mb6-gt": False,
    "northwind-gt": True,
    "spotify-gt": False,
    "steam-gt": False,
    "tpc-h-gt": True,
}


def _build_working(star_node_types: List[NodeType], star_edge_types: List[EdgeType]):
    nodes: Dict[str, dict] = {
        n.node_id: {
            "labels": set(n.labels),
            "mandatory": set(n.mandatory_props),
            "optional": set(n.optional_props),
        }
        for n in star_node_types
    }
    edges: List[dict] = [
        {
            "id": e.edge_id,
            "label": e.label,
            "mandatory": set(e.mandatory_props),
            "optional": set(e.optional_props),
            "src": e.src_node_type.node_id,
            "dst": e.dst_node_type.node_id,
            "has_card": e.has_cardinality_error,
        }
        for e in star_edge_types
    ]
    return nodes, edges


def _materialize(nodes: Dict[str, dict], edges: List[dict]) -> Tuple[List[NodeType], List[EdgeType]]:
    node_objs = {
        nid: NodeType(
            frozenset(d["labels"]),
            frozenset(d["mandatory"]),
            frozenset(d["optional"]),
            nid,
        )
        for nid, d in nodes.items()
    }
    edge_objs = [
        EdgeType(
            e["label"],
            frozenset(e["mandatory"]),
            frozenset(e["optional"]),
            node_objs[e["src"]],
            node_objs[e["dst"]],
            e["id"],
            e["has_card"],
        )
        for e in edges
    ]
    return list(node_objs.values()), edge_objs


def _apply_error(selected_type: str, nodes: Dict[str, dict], edges: List[dict],
                 used: Set[str], id_counter) -> bool:
    """Apply one error of `selected_type`. Returns False if no candidate exists."""
    if selected_type == "node_type_missing":
        cands = [nid for nid in nodes if nid not in used]
        if not cands:
            return False
        nid = random.choice(cands)
        del nodes[nid]
        edges[:] = [e for e in edges if e["src"] != nid and e["dst"] != nid]
        used.add(nid)
        return True

    if selected_type == "node_label_missing":
        pool = [(nid, l)
                for nid in nodes if nid not in used for l in nodes[nid]["labels"]]
        if not pool:
            return False
        nid, label = random.choice(pool)
        nodes[nid]["labels"].discard(label)
        used.add(nid)
        return True

    if selected_type == "node_property_missing":
        pool = [(nid, p) for nid in nodes if nid not in used
                for p in (nodes[nid]["mandatory"] | nodes[nid]["optional"])]
        if not pool:
            return False
        nid, prop = random.choice(pool)
        nodes[nid]["mandatory"].discard(prop)
        nodes[nid]["optional"].discard(prop)
        used.add(nid)
        return True

    if selected_type == "node_duplicate":
        cands = [nid for nid in nodes if nid not in used]
        if not cands:
            return False
        nid = random.choice(cands)
        new_id = f"dup_node_{next(id_counter)}"
        src = nodes[nid]
        nodes[new_id] = {
            "labels": set(src["labels"]),
            "mandatory": set(src["mandatory"]),
            "optional": set(src["optional"]),
        }
        used.add(nid)
        return True

    if selected_type == "edge_type_missing":
        cands = [e for e in edges if e["id"] not in used]
        if not cands:
            return False
        e = random.choice(cands)
        used.add(e["id"])
        edges.remove(e)
        return True

    if selected_type == "edge_property_missing":
        pool = [(e, p) for e in edges if e["id"] not in used
                for p in (e["mandatory"] | e["optional"])]
        if not pool:
            return False
        e, prop = random.choice(pool)
        e["mandatory"].discard(prop)
        e["optional"].discard(prop)
        used.add(e["id"])
        return True

    if selected_type == "edge_duplicate":
        cands = [e for e in edges if e["id"] not in used]
        if not cands:
            return False
        e = random.choice(cands)
        new = {
            "id": f"dup_edge_{next(id_counter)}",
            "label": e["label"],
            "mandatory": set(e["mandatory"]),
            "optional": set(e["optional"]),
            "src": e["src"],
            "dst": e["dst"],
            "has_card": e["has_card"],
        }
        edges.append(new)
        used.add(e["id"])
        return True

    if selected_type == "edge_direction_swapped":
        cands = [e for e in edges if e["id"] not in used]
        if not cands:
            return False
        e = random.choice(cands)
        e["src"], e["dst"] = e["dst"], e["src"]
        used.add(e["id"])
        return True

    if selected_type == "edge_cardinality_error":
        cands = [e for e in edges if e["id"] not in used]
        if not cands:
            return False
        e = random.choice(cands)
        e["has_card"] = True
        used.add(e["id"])
        return True

    raise NotImplementedError(
        f"Error type '{selected_type}' is not implemented.")


def _remove_properties_by_ratio(items: List[dict], ratio: float) -> None:
    """Remove a ratio of the schema's total property count from `items`.

    Each item is a working dict carrying "mandatory"/"optional" property sets
    (a node or an edge). Every property across all items forms a single pool;
    we drop ``total * ratio`` distinct properties (minimum 1) sampled without
    replacement. Because the pool is per-property, the same item may be chosen
    multiple times, removing several of its properties.

    Rounding is round-half-up (``int(x + 0.5)``) rather than Python's built-in
    ``round`` (banker's rounding), so e.g. 18.5 -> 19.
    """
    pool = [(idx, p) for idx, item in enumerate(items)
            for p in (item["mandatory"] | item["optional"])]
    total = len(pool)
    if total == 0:
        return
    count = min(total, max(1, int(total * ratio + 0.5)))
    for idx, prop in random.sample(pool, count):
        items[idx]["mandatory"].discard(prop)
        items[idx]["optional"].discard(prop)


def insert_errors_in_memory(star_node_types: List[NodeType], star_edge_types: List[EdgeType],
                            num_errors: int, error_type: str,
                            supports_cardinality: bool) -> Tuple[List[NodeType], List[EdgeType]]:
    nodes, edges = _build_working(star_node_types, star_edge_types)

    if error_type == "edge_cardinality_error" and not supports_cardinality:
        return _materialize(nodes, edges)

    if error_type in PROPERTY_ERROR_TYPES:
        # `num_errors` (1-5) selects the ratio level: level i -> i * 10%.
        ratio = num_errors * 0.1
        target = list(
            nodes.values()) if error_type == "node_property_missing" else edges
        _remove_properties_by_ratio(target, ratio)
        return _materialize(nodes, edges)

    edge_random_pool = EDGE_ERROR_TYPES if supports_cardinality else EDGE_ERROR_TYPES_NO_CARDINALITY

    used: Set[str] = set()
    id_counter = itertools.count()
    inserted = 0
    for _ in range(num_errors):
        if error_type == "node_random":
            selected = random.choice(NODE_ERROR_TYPES)
        elif error_type == "edge_random":
            selected = random.choice(edge_random_pool)
        else:
            selected = error_type

        if not _apply_error(selected, nodes, edges, used, id_counter):
            break
        inserted += 1

    return _materialize(nodes, edges)


def insert_errors_and_evaluate(star_node_types: List[NodeType], star_edge_types: List[EdgeType],
                               instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
                               num_errors: int, error_type: str, supports_cardinality: bool = False):
    mutated_node_types, mutated_edge_types = insert_errors_in_memory(
        star_node_types, star_edge_types, num_errors, error_type, supports_cardinality)

    node_coverage, edge_coverage, node_concision, edge_concision, node_c2, edge_c2 = \
        utils.eval_c2_from_types(
            instance_node_types, instance_edge_types,
            mutated_node_types, mutated_edge_types,
            label_w=0.5, mandatory_w=0.25, optional_w=0.25, endpoint_w=0.5, gamma=0.15,
            include_cardinality=supports_cardinality)

    # F1 (previous method): the error-injected schema vs the original GT schema
    # S*. Exact set matching after flattening both, all properties merged.
    (node_precision, node_recall, node_f1,
     edge_precision, edge_recall, edge_f1) = calc_f1_from_types(
        mutated_node_types, mutated_edge_types,
        star_node_types, star_edge_types)

    return {
        "node_coverage": node_coverage,
        "edge_coverage": edge_coverage,
        "node_concision": node_concision,
        "edge_concision": edge_concision,
        "node_c2": node_c2,
        "edge_c2": edge_c2,
        "node_precision": node_precision,
        "node_recall": node_recall,
        "node_f1": node_f1,
        "edge_precision": edge_precision,
        "edge_recall": edge_recall,
        "edge_f1": edge_f1,
    }


RANDOM_SEED = 42


def main():
    random.seed(RANDOM_SEED)

    header = [
        "timestamp",
        "dataset",
        "has_cardinality",
        "error_type",
        "num_errors",
        "node_coverage",
        "edge_coverage",
        "node_concision",
        "edge_concision",
        "node_c2",
        "edge_c2",
        "node_precision",
        "node_recall",
        "node_f1",
        "edge_precision",
        "edge_recall",
        "edge_f1",
    ]
    errors = [
        "node_type_missing",
        "node_label_missing",
        "node_property_missing",
        "node_duplicate",
        "node_random",
        "edge_type_missing",
        "edge_property_missing",
        "edge_duplicate",
        "edge_direction_swapped",
        "edge_cardinality_error",
        "edge_random"
    ]

    for gt_schema_db, supports_cardinality in SCHEMAS.items():
        print(f"Processing dataset: {gt_schema_db}")

        # Read instance types and the GT schema S* once per dataset; both are
        # constant across the thousands of trials below.
        instance_db_name = gt_schema_db[:-3]
        instance_node_types, instance_edge_types = utils.get_all_node_and_edge_types_from_instance(
            instance_db_name, URI, AUTH)
        star_node_types, star_edge_types = utils.get_all_node_and_edge_types_from_schema(
            gt_schema_db, URI, AUTH)

        total_node_props = sum(len(n.mandatory_props) + len(n.optional_props)
                               for n in star_node_types)
        total_edge_props = sum(len(e.mandatory_props) + len(e.optional_props)
                               for e in star_edge_types)
        print(f"  Total node properties: {total_node_props}, "
              f"total edge properties: {total_edge_props}")

        results_dir = "./experiment/sensitivity_test/results"
        os.makedirs(results_dir, exist_ok=True)
        csv_file_name = f"{results_dir}/results_{gt_schema_db[:-3]}_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.csv"
        with open(csv_file_name, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(header)
        for error_type in errors:
            if error_type == "edge_cardinality_error" and not supports_cardinality:
                continue
            print(f"  Inserting error type: {error_type}")
            for num_errors in range(1, 6):
                print(f"    Number of errors: {num_errors}")
                rows = []
                for _ in range(100):
                    result = insert_errors_and_evaluate(
                        star_node_types, star_edge_types,
                        instance_node_types, instance_edge_types,
                        num_errors, error_type, supports_cardinality)

                    dct = {
                        "has_cardinality": supports_cardinality,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "dataset": gt_schema_db[:-3],
                        "num_errors": num_errors,
                        "error_type": error_type,
                        **result
                    }
                    rows.append([dct[h] for h in header])

                if rows:
                    with open(csv_file_name, "a", newline="") as csvfile:
                        writer = csv.writer(csvfile)
                        writer.writerows(rows)


if __name__ == "__main__":

    main()
    print("Experiment completed.")
