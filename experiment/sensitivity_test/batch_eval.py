"""Score many perturbed instances against ONE fixed schema in a single sweep.

`utils_sparse.eval_c2_sparse_from_types` costs ~29 min per call on Full
DBpedia, and ~95% of that is the Con_V loop
(`utils_sparse.calc_node_concision_sparse`): for each of the 446 schema nodes
it re-flattens S* (1.58 s) and rebuilds the edge similarity matrix (2.16 s).

The irregularity experiment evaluates dozens of perturbed instances against
the *same* schema, so both
halves of that loop are being repeated 46 times over:

* the re-flatten depends on the schema only — it is literally the same work;
* a matrix row depends only on its own instance edge type and the schema, and
  a perturbation moves a few hundred of the 178,786 rows. The rest are
  identical across conditions.

So the loops are inverted: the schema sweep runs once, the matrix is built
once per sweep step over the *union* of every condition's instance edge types
(equal contents collapse to one row, which is the row diff without having to
track a diff), and each condition then reads back only its own rows.

Everything numeric comes from the audited functions in `utils` / `utils_sparse`,
which are not modified. What keeps the result bit-identical to the per-call
path is that each condition's row-maximum array is materialised in that
condition's own order before `np.mean` runs over it — `np.mean` sums pairwise,
so order and length must match, while the values themselves are per-row and
order-independent.
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..common import utils, utils_sparse
from ..common.entity_def import EdgeType, NodeType
from ..common.utils import calc_coverage, flatten_in_memory


@dataclass
class Condition:
    """One instance to score, i.e. one Abs(G')."""

    name: str
    node_types: List[NodeType]
    edge_types: List[EdgeType]
    meta: dict = field(default_factory=dict)


@dataclass
class Scores:
    node_coverage: float
    edge_coverage: float
    node_concision: float
    edge_concision: float
    node_c2: float
    edge_c2: float

    def as_tuple(self) -> Tuple[float, float, float, float, float, float]:
        return (self.node_coverage, self.edge_coverage,
                self.node_concision, self.edge_concision,
                self.node_c2, self.edge_c2)


def _intern(conditions: Sequence[Condition]
            ) -> Tuple[List[NodeType], List[EdgeType],
                       List[np.ndarray], List[np.ndarray]]:
    """Union of every condition's types, plus each condition's row indices.

    Node types are interned by content; edge types are then interned by
    (label, src row, dst row, properties), i.e. with the endpoints already
    reduced to integers.

    Keying the edges by the EdgeType objects themselves would be the obvious
    thing to do and is a trap: every lookup that hits pays `EdgeType.__eq__`,
    which compares both endpoints' property sets element by element (up to
    28k keys on DBpedia). At 46 conditions x 178,786 edge types that is over
    an hour. This is the same pitfall utils_sparse:36-41 documents for its
    node column cache.

    The union edge endpoints are rewired to the interned node objects because
    `utils_sparse.build_edge_sim_sparse` resolves endpoints to row numbers by
    object identity.
    """
    union_nodes: List[NodeType] = []
    node_pos: Dict[NodeType, int] = {}
    union_edges: List[EdgeType] = []
    edge_pos: Dict[Tuple, int] = {}
    node_idx: List[np.ndarray] = []
    edge_idx: List[np.ndarray] = []

    for cond in conditions:
        rows = np.empty(len(cond.node_types), dtype=np.intp)
        # Object identity -> union row, so the edge loop below never has to
        # hash a NodeType again.
        row_of_obj: Dict[int, int] = {}
        for i, nt in enumerate(cond.node_types):
            pos = node_pos.get(nt)
            if pos is None:
                pos = len(union_nodes)
                union_nodes.append(nt)
                node_pos[nt] = pos
            rows[i] = pos
            row_of_obj[id(nt)] = pos
        node_idx.append(rows)

        rows = np.empty(len(cond.edge_types), dtype=np.intp)
        for i, et in enumerate(cond.edge_types):
            src_row = row_of_obj.get(id(et.src_node_type))
            dst_row = row_of_obj.get(id(et.dst_node_type))
            if src_row is None:
                src_row = node_pos[et.src_node_type]
            if dst_row is None:
                dst_row = node_pos[et.dst_node_type]
            key = (et.label, src_row, dst_row,
                   et.mandatory_props, et.optional_props)
            pos = edge_pos.get(key)
            if pos is None:
                src = union_nodes[src_row]
                dst = union_nodes[dst_row]
                if src is et.src_node_type and dst is et.dst_node_type:
                    canonical = et
                else:
                    canonical = EdgeType(
                        et.label, et.mandatory_props, et.optional_props,
                        src, dst, et.edge_id, et.has_cardinality_error)
                pos = len(union_edges)
                union_edges.append(canonical)
                edge_pos[key] = pos
            rows[i] = pos
        edge_idx.append(rows)

    return union_nodes, union_edges, node_idx, edge_idx


def _row_max_of_matrix(mat: np.ndarray) -> np.ndarray:
    """Per-row best match of a dense matrix, as utils.calc_coverage takes it.

    calc_coverage picks `sim_matrix[i, np.argmax(sim_matrix[i])]` per row and
    averages the resulting list. A row's maximum does not depend on which
    other rows are present, so it can be taken once for the union and then
    read back per condition.
    """
    return np.fromiter(
        (mat[i, np.argmax(mat[i])] for i in range(mat.shape[0])),
        dtype=float, count=mat.shape[0])


def _coverage(row_max: np.ndarray, idx: np.ndarray,
              num_schema_objects: int) -> float:
    """utils.calc_coverage / utils_sparse.coverage_sparse for one condition.

    `row_max[idx]` is a fresh contiguous array in the condition's own order,
    so np.mean reproduces the per-call path exactly.
    """
    num_instance_objects = len(idx)
    if num_schema_objects == 0 and num_instance_objects > 0:
        return 0.0
    elif num_schema_objects == 0 and num_instance_objects == 0:
        return 1.0
    elif num_schema_objects > 0 and num_instance_objects == 0:
        return 1.0
    return np.mean(row_max[idx])


def eval_conditions(conditions: Sequence[Condition],
                    star_node_types: List[NodeType],
                    star_edge_types: List[EdgeType],
                    label_w: float, mandatory_w: float, optional_w: float,
                    endpoint_w: float, gamma: float,
                    include_cardinality: bool = False,
                    timings: Optional[Dict[str, float]] = None,
                    verbose: bool = True) -> List[Scores]:
    """Six score components per condition, all against the same S*."""
    assert label_w + mandatory_w + optional_w == 1
    assert 0.0 <= endpoint_w <= 1.0
    if not conditions:
        return []

    utils._flatten_time_acc = 0.0
    utils._score_time_acc = 0.0
    utils_sparse._score_time_acc = 0.0
    utils_sparse._node_col_cache.clear()

    eff_endpoint_w = 1 / 3 if include_cardinality else endpoint_w
    eff_cardinality_w = 1 / 3 if include_cardinality else 0.0

    t_intern = time.time()
    union_nodes, union_edges, node_idx, edge_idx = _intern(conditions)
    if verbose:
        print(f"[batch] {len(conditions)} conditions | union "
              f"{len(union_nodes)} node types / {len(union_edges)} edge types "
              f"({time.time() - t_intern:.1f}s)")

    # ---- Coverage pass (once for the whole batch) ----------------------
    t0 = time.time()
    flat_nodes, flat_edges = flatten_in_memory(star_node_types, star_edge_types)
    node_mat = utils_sparse.create_node_sim_matrix(
        union_nodes, flat_nodes, label_w, mandatory_w, optional_w)
    rows = utils_sparse.build_edge_sim_sparse(
        union_edges, flat_edges, union_nodes,
        label_w, mandatory_w, optional_w, eff_endpoint_w, eff_cardinality_w)
    row_max = utils_sparse.row_max_array(rows)
    node_row_max = (_row_max_of_matrix(node_mat) if node_mat.shape[1] > 0
                    else np.zeros(node_mat.shape[0]))

    flatten_edge_num = len(flat_edges)
    node_cov = [_coverage(node_row_max, node_idx[i], node_mat.shape[1])
                for i in range(len(conditions))]
    edge_cov = [_coverage(row_max, edge_idx[i], flatten_edge_num)
                for i in range(len(conditions))]
    if timings is not None:
        timings["cov_pass"] = time.time() - t0
    if verbose:
        print(f"[batch] coverage pass done ({time.time() - t0:.1f}s), "
              f"flatten cols {flatten_edge_num}")

    # ---- Con_V: one schema sweep shared by every condition -------------
    t1 = time.time()
    num_schema_nodes = len(star_node_types)
    cnt = [0] * len(conditions)
    if num_schema_nodes > 0:
        node_theta = [gamma * node_cov[i] / num_schema_nodes
                      for i in range(len(conditions))]
        edge_theta = [1.0 if flatten_edge_num == 0
                      else gamma * edge_cov[i] / flatten_edge_num
                      for i in range(len(conditions))]
        for step, node_type in enumerate(star_node_types):
            new_s_nodes, new_s_edges = flatten_in_memory(
                star_node_types, star_edge_types,
                exclude_node_id=node_type.node_id)
            nm = utils_sparse.create_node_sim_matrix(
                union_nodes, new_s_nodes, label_w, mandatory_w, optional_w)
            sub_rows = utils_sparse.build_edge_sim_sparse(
                union_edges, new_s_edges, union_nodes,
                label_w, mandatory_w, optional_w, eff_endpoint_w,
                eff_cardinality_w)
            sub_row_max = utils_sparse.row_max_array(sub_rows)
            sub_node_row_max = (_row_max_of_matrix(nm) if nm.shape[1] > 0
                                else np.zeros(nm.shape[0]))

            for i in range(len(conditions)):
                # Mirrors calc_node_concision_sparse: an empty schema side
                # yields 0.0 here, not calc_coverage's empty-schema branches.
                new_node_cov = 0.0 if nm.shape[1] == 0 else _coverage(
                    sub_node_row_max, node_idx[i], nm.shape[1])
                new_edge_cov = 0.0 if len(new_s_edges) == 0 else _coverage(
                    sub_row_max, edge_idx[i], len(new_s_edges))
                if (node_cov[i] - new_node_cov < node_theta[i]
                        and edge_cov[i] - new_edge_cov < edge_theta[i]):
                    cnt[i] += 1

            if verbose and (step + 1) % 50 == 0:
                elapsed = time.time() - t1
                print(f"[batch] Con_V {step + 1}/{num_schema_nodes} "
                      f"({elapsed:.0f}s, "
                      f"eta {elapsed / (step + 1) * (num_schema_nodes - step - 1):.0f}s)")
    if timings is not None:
        timings["con_v"] = time.time() - t1

    # ---- Con_E: per condition, on the shared full-flatten matrix -------
    t2 = time.time()
    results: List[Scores] = []
    for i, cond in enumerate(conditions):
        if num_schema_nodes == 0:
            node_concision = 1.0
        elif len(cond.node_types) == 0:
            node_concision = 0.0
        else:
            node_concision = 1 - cnt[i] / num_schema_nodes

        cond_rows = [rows[j] for j in edge_idx[i]]
        cond_row_max = row_max[edge_idx[i]]
        edge_concision = utils_sparse.calc_edge_concision_sparse(
            instance_node_types=cond.node_types,
            instance_edge_types=cond.edge_types,
            original_node_coverage=node_cov[i],
            original_edge_coverage=edge_cov[i],
            flatten_edge_num=flatten_edge_num,
            label_w=label_w, mandatory_w=mandatory_w, optional_w=optional_w,
            endpoint_w=eff_endpoint_w, gamma=gamma,
            star_node_types=star_node_types, star_edge_types=star_edge_types,
            schema_edge_types=flat_edges,
            rows=cond_rows, row_max=cond_row_max,
            cardinality_w=eff_cardinality_w)

        nc, ec = node_cov[i], edge_cov[i]
        node_c2 = (2 * (nc * node_concision) / (nc + node_concision)
                   if (nc + node_concision) > 0 else 0.0)
        edge_c2 = (2 * (ec * edge_concision) / (ec + edge_concision)
                   if (ec + edge_concision) > 0 else 0.0)
        results.append(Scores(nc, ec, node_concision, edge_concision,
                              node_c2, edge_c2))
    if timings is not None:
        timings["con_e"] = time.time() - t2
    if verbose:
        print(f"[batch] Con_V {t2 - t1:.0f}s, Con_E {time.time() - t2:.0f}s")

    return results


def eval_conditions_reference(conditions: Sequence[Condition],
                              star_node_types: List[NodeType],
                              star_edge_types: List[EdgeType],
                              label_w: float, mandatory_w: float,
                              optional_w: float, endpoint_w: float,
                              gamma: float,
                              include_cardinality: bool = False,
                              verbose: bool = True) -> List[Scores]:
    """The slow path: one `eval_c2_sparse_from_types` call per condition.

    Available through instance_irregularity's `--reference` flag for spot
    checks against the batch sweep.
    """
    results: List[Scores] = []
    for cond in conditions:
        t0 = time.time()
        scores = utils_sparse.eval_c2_sparse_from_types(
            cond.node_types, cond.edge_types,
            star_node_types, star_edge_types,
            label_w, mandatory_w, optional_w, endpoint_w, gamma,
            include_cardinality=include_cardinality)
        results.append(Scores(*scores))
        if verbose:
            print(f"[reference] {cond.name}: c2_v={scores[4]:.6f} "
                  f"c2_e={scores[5]:.6f} ({time.time() - t0:.1f}s)")
    return results
