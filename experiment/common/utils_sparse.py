"""Sparse C2-score evaluation, bit-identical to utils.eval_c2.

The edge similarity matrix is the only thing that changes representation:
instead of a dense |I_E| x |S_E| ndarray it is kept as per-row lists of
(column, similarity) pairs holding non-zero entries only. Everything the
scores are computed from (row maxima, np.mean over the full row-max array,
threshold comparisons, tie-breaking) reproduces utils.py exactly, so all six
score components compare equal with `==` against the dense implementation.

Why the non-zero set is exact and not an approximation: utils.edge_sim
returns 0.0 unless the two edges share the label AND both endpoint label
sets intersect; when all three hold the result is strictly positive. The
candidate index below enumerates precisely the pairs passing those three
checks, so "non-zero entries" == "index hits" by construction.

The node-side matrix stays dense (|I_V| x |S_V| is tiny), mirroring the
node half of utils.create_sim_matrix including its per-column cache.
"""

import time
from collections import defaultdict
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

import numpy as np

from . import utils
from .entity_def import EdgeType, NodeType
from .utils import (calc_coverage, db_exists, dice_sim, flatten_in_memory,
                    get_all_node_and_edge_types_from_instance,
                    get_all_node_and_edge_types_from_schema, node_sim)

# Cache carried across the Con_V / Con_E iterations of one eval call,
# cleared at the start of each eval_c2_sparse / eval_c2_sparse_from_types.
# Keys hash by content (entity_def __hash__), like utils._node_col_cache.
# IMPORTANT: content-keyed lookups pay a NodeType.__eq__ (frozenset
# comparison over property sets of up to ~28k keys on DBpedia), so they
# must happen O(|S_V|) times per matrix build — never once per candidate
# pair. build_edge_sim_sparse therefore resolves each distinct schema node
# OBJECT to its cached similarity column once, then serves per-pair lookups
# by object id + row index.
_node_col_cache: Dict[NodeType, np.ndarray] = {}

# Score-time accumulator for the sparse-side work; utils._score_time_acc
# still accumulates the time spent inside utils.calc_coverage.
_score_time_acc: float = 0.0

_FlattenKey = Tuple[str, str, str, FrozenSet[str], FrozenSet[str]]


def _node_col(s_node: NodeType, i_node_types: List[NodeType],
              label_w, mandatory_w, optional_w) -> np.ndarray:
    """Similarity column of one schema node vs all instance nodes.

    Same values (bit-identical) and same content-keyed cache as the node
    half of utils.create_sim_matrix.
    """
    col = _node_col_cache.get(s_node)
    if col is None:
        col = np.fromiter(
            (node_sim(i_node, s_node, label_w, mandatory_w, optional_w)
             for i_node in i_node_types),
            dtype=float, count=len(i_node_types),
        )
        _node_col_cache[s_node] = col
    return col


def create_node_sim_matrix(i_node_types: List[NodeType],
                           s_node_types: List[NodeType],
                           label_w, mandatory_w, optional_w) -> np.ndarray:
    """Node half of utils.create_sim_matrix, same per-column cache."""
    global _score_time_acc
    _t = time.time()

    n_i_nodes = len(i_node_types)
    n_s_nodes = len(s_node_types)
    if n_i_nodes > 0 and n_s_nodes > 0:
        cols = [_node_col(s_node, i_node_types, label_w, mandatory_w, optional_w)
                for s_node in s_node_types]
        node_sim_matrix = np.column_stack(cols)
    else:
        node_sim_matrix = np.zeros((n_i_nodes, n_s_nodes))

    _score_time_acc += time.time() - _t
    return node_sim_matrix


def build_candidate_index(s_edge_types: List[EdgeType]) -> Dict[Tuple[str, str, str], List[int]]:
    """Composite-key buckets over the flattened schema edge types.

    One bucket per (edge label, src node label, dst node label); an edge with
    multi-label endpoints lands in every label combination. Do NOT replace
    this with per-field posting lists + set intersection: copying the posting
    lists dominates and is ~300x slower on Full DBpedia.
    """
    idx: Dict[Tuple[str, str, str], List[int]] = defaultdict(list)
    for j, e in enumerate(s_edge_types):
        label = e.label
        for sl in e.src_node_type.labels:
            for dl in e.dst_node_type.labels:
                idx[(label, sl, dl)].append(j)
    return idx


def build_edge_sim_sparse(i_edge_types: List[EdgeType],
                          s_edge_types: List[EdgeType],
                          i_node_types: List[NodeType],
                          label_w, mandatory_w, optional_w, endpoint_w,
                          cardinality_w=0.0) -> List[List[Tuple[int, float]]]:
    """Sparse edge similarity matrix: rows[i] = [(col_j, sim), ...].

    Row order strictly follows i_edge_types; column indices are positions in
    s_edge_types (the list returned by flatten_in_memory). i_node_types must
    be the eval's instance node list — edge endpoints are resolved to its
    row indices by object identity, so the endpoint node similarities are
    array reads instead of per-pair node_sim calls (the arithmetic mirrors
    utils.edge_sim verbatim and stays bit-identical).
    """
    global _score_time_acc
    _t = time.time()

    idx = build_candidate_index(s_edge_types)

    # Instance endpoint -> row index, by object identity (instance NodeType
    # objects are shared between i_node_types and the edge endpoints).
    inst_row = {id(n): k for k, n in enumerate(i_node_types)}
    # Schema endpoint object -> its similarity column, resolved through the
    # content-keyed cache once per distinct object (NOT once per pair).
    col_by_snode: Dict[int, np.ndarray] = {}

    def _snode_col(s_node: NodeType) -> np.ndarray:
        col = col_by_snode.get(id(s_node))
        if col is None:
            col = _node_col(s_node, i_node_types,
                            label_w, mandatory_w, optional_w)
            col_by_snode[id(s_node)] = col
        return col

    rows: List[List[Tuple[int, float]]] = []
    for ie in i_edge_types:
        sls = ie.src_node_type.labels
        dls = ie.dst_node_type.labels
        if len(sls) == 1 and len(dls) == 1:
            cand = idx.get((ie.label, next(iter(sls)), next(iter(dls))), ())
        else:
            # Union of |sls| x |dls| buckets, deduplicated preserving order.
            seen: Set[int] = set()
            cand = []
            for sl in sls:
                for dl in dls:
                    for j in idx.get((ie.label, sl, dl), ()):
                        if j not in seen:
                            seen.add(j)
                            cand.append(j)
        if not cand:
            rows.append([])
            continue
        src_row = inst_row.get(id(ie.src_node_type))
        dst_row = inst_row.get(id(ie.dst_node_type))
        row = []
        for j in cand:
            se = s_edge_types[j]
            # utils.edge_sim verbatim, with node_sim served from columns.
            if ie.label != se.label:
                row.append((j, 0.0))
                continue
            if not (sls & se.src_node_type.labels):
                row.append((j, 0.0))
                continue
            if not (dls & se.dst_node_type.labels):
                row.append((j, 0.0))
                continue
            if src_row is not None:
                src_node_sim = _snode_col(se.src_node_type)[src_row]
            else:  # endpoint object not in i_node_types (defensive fallback)
                src_node_sim = node_sim(ie.src_node_type, se.src_node_type,
                                        label_w, mandatory_w, optional_w)
            if dst_row is not None:
                dst_node_sim = _snode_col(se.dst_node_type)[dst_row]
            else:
                dst_node_sim = node_sim(ie.dst_node_type, se.dst_node_type,
                                        label_w, mandatory_w, optional_w)
            label_sim = dice_sim({ie.label}, {se.label})
            mandatory_prop_sim = dice_sim(ie.mandatory_props,
                                          se.mandatory_props)
            optional_prop_sim = dice_sim(ie.optional_props, se.optional_props)
            endpoint_sim = (src_node_sim + dst_node_sim) / 2
            edge_attr_sim = label_w * label_sim + mandatory_w * \
                mandatory_prop_sim + optional_w * optional_prop_sim
            cardinality_sim = 0.0 if se.has_cardinality_error else 1.0
            body_w = 1.0 - endpoint_w - cardinality_w
            row.append((j, endpoint_w * endpoint_sim + body_w * edge_attr_sim
                        + cardinality_w * cardinality_sim))
        rows.append(row)

    _score_time_acc += time.time() - _t
    return rows


def row_max_array(rows: List[List[Tuple[int, float]]]) -> np.ndarray:
    """Per-row maxima as float64, 0.0 for rows without candidates.

    Equals the dense row maximum: every dense cell outside the candidate set
    is exactly 0.0 and every candidate similarity is > 0 (with
    cardinality_w=0; with cardinality_w>0 it is still >= 0 so max semantics
    are unchanged).
    """
    global _score_time_acc
    _t = time.time()
    arr = np.fromiter(
        (max((s for _, s in row), default=0.0) for row in rows),
        dtype=float, count=len(rows),
    )
    _score_time_acc += time.time() - _t
    return arr


def coverage_sparse(row_max: np.ndarray, num_instance_objects: int,
                    num_schema_objects: int) -> float:
    """utils.calc_coverage on a sparse matrix given its row-max array."""
    global _score_time_acc
    _t = time.time()
    if num_schema_objects == 0 and num_instance_objects > 0:
        _score_time_acc += time.time() - _t
        return 0.0
    elif num_schema_objects == 0 and num_instance_objects == 0:
        _score_time_acc += time.time() - _t
        return 1.0
    elif num_schema_objects > 0 and num_instance_objects == 0:
        _score_time_acc += time.time() - _t
        return 1.0
    coverage = np.mean(row_max)
    _score_time_acc += time.time() - _t
    return coverage


def calc_node_concision_sparse(
    instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
    original_node_coverage: float, original_edge_coverage: float, flatten_edge_num: int,
    label_w, mandatory_w, optional_w, endpoint_w, gamma,
    star_node_types: List[NodeType], star_edge_types: List[EdgeType], cardinality_w=0.0,
    base_schema_node_types: Optional[List[NodeType]] = None,
    base_schema_edge_types: Optional[List[EdgeType]] = None,
    base_node_sim_matrix: Optional[np.ndarray] = None,
    base_rows: Optional[List[List[Tuple[int, float]]]] = None,
    base_row_max: Optional[np.ndarray] = None,
):
    """utils.calc_node_concision with the edge matrix held sparse.

    Excluding a node with no EXTENDS descendants leaves every other flattened
    node/edge type untouched (inheritance propagates ancestor -> descendant
    only, and every flatten dedup key removed by the exclusion has the
    excluded node as an endpoint), so its iteration is served from the base
    matrices by column deletion — pure selection plus the same np.mean, no
    new float arithmetic. Nodes that ARE ancestors (a handful) still take the
    verbatim re-flatten path.

    The base_* arguments are the no-exclusion flatten output and matrices the
    caller already built for coverage; omit them and they are recomputed.
    """
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

    if base_schema_node_types is None or base_schema_edge_types is None:
        base_schema_node_types, base_schema_edge_types = flatten_in_memory(
            star_node_types, star_edge_types)
    if base_node_sim_matrix is None:
        base_node_sim_matrix = create_node_sim_matrix(
            instance_node_types, base_schema_node_types,
            label_w, mandatory_w, optional_w)
    if base_rows is None:
        base_rows = build_edge_sim_sparse(
            instance_edge_types, base_schema_edge_types, instance_node_types,
            label_w, mandatory_w, optional_w, endpoint_w, cardinality_w)
    if base_row_max is None:
        base_row_max = row_max_array(base_rows)

    global _score_time_acc
    _t = time.time()

    # Ancestor ids (nodes with at least one EXTENDS descendant): excluding
    # one changes other flattened types, so only these need the full path.
    parents_of: Dict[str, List[str]] = defaultdict(list)
    for e in star_edge_types:
        if e.label == "EXTENDS":
            parents_of[e.src_node_type.node_id].append(e.dst_node_type.node_id)
    ancestor_ids: Set[str] = set()
    for child_id in parents_of:
        queue = list(parents_of[child_id])
        while queue:
            a = queue.pop(0)
            if a not in ancestor_ids:
                ancestor_ids.add(a)
                queue.extend(parents_of.get(a, []))
    # Exactly the nodes having >= 1 EXTENDS descendant (direct parents plus
    # their transitive ancestors).

    n_flat = len(base_schema_edge_types)
    n_base_cols = base_node_sim_matrix.shape[1]

    # Flattened node/edge column positions per node id.
    node_col_of_id: Dict[str, int] = {
        n.node_id: j for j, n in enumerate(base_schema_node_types)}
    edge_cols_of_node: Dict[str, List[int]] = defaultdict(list)
    for j, e in enumerate(base_schema_edge_types):
        sid = e.src_node_type.node_id
        did = e.dst_node_type.node_id
        edge_cols_of_node[sid].append(j)
        if did != sid:
            edge_cols_of_node[did].append(j)
    rows_by_col: List[List[int]] = [[] for _ in range(n_flat)]
    for r, row in enumerate(base_rows):
        for j, _ in row:
            rows_by_col[j].append(r)

    # Per-row top-2 of the base node matrix: deleting column j turns each
    # row max into top1 (when the row's value at j is below top1, ties
    # included) or top2 (when j held the unique max). Selection only.
    if n_base_cols >= 2:
        _part = np.partition(base_node_sim_matrix, (n_base_cols - 2,), axis=1)
        node_top1 = _part[:, -1]
        node_top2 = _part[:, -2]

    cnt = 0
    _n_done = 0
    _n_fallback = 0
    _prog_t0 = time.time()
    _prog_last = _prog_t0
    for node_type in star_node_types:
        node_id = node_type.node_id
        _n_done += 1
        _now = time.time()
        if _now - _prog_last >= 60.0:
            _prog_last = _now
            print(f"[c2-progress] con_v {_n_done}/{num_schema_nodes} "
                  f"(fallback {_n_fallback}/{len(ancestor_ids)}) "
                  f"elapsed={_now - _prog_t0:.0f}s", flush=True)

        if node_id in ancestor_ids:
            _n_fallback += 1
            _score_time_acc += time.time() - _t
            new_schema_node_types, new_schema_edge_types = flatten_in_memory(
                star_node_types, star_edge_types, exclude_node_id=node_id)

            node_sim_matrix = create_node_sim_matrix(
                instance_node_types, new_schema_node_types,
                label_w, mandatory_w, optional_w)
            rows = build_edge_sim_sparse(
                instance_edge_types, new_schema_edge_types, instance_node_types,
                label_w, mandatory_w, optional_w, endpoint_w, cardinality_w)

            # Mirrors calc_node_concision: a 0-column matrix yields 0.0
            # coverage here (not calc_coverage's empty-schema branches).
            new_node_coverage = 0.0 if node_sim_matrix.shape[1] == 0 else calc_coverage(
                node_sim_matrix)
            new_edge_coverage = 0.0 if len(new_schema_edge_types) == 0 else coverage_sparse(
                row_max_array(rows), len(instance_edge_types), len(new_schema_edge_types))
            _t = time.time()
        else:
            # Node side: base matrix minus this node's column.
            jcol = node_col_of_id[node_id]
            if n_base_cols - 1 == 0:
                new_node_coverage = 0.0
            elif num_instance_nodes == 0:
                new_node_coverage = 1.0  # unreachable (guarded above)
            else:
                col = base_node_sim_matrix[:, jcol]
                new_max = np.where(col < node_top1, node_top1, node_top2)
                new_node_coverage = np.mean(new_max)

            # Edge side: base flatten minus the columns touching this node.
            removed = edge_cols_of_node.get(node_id, [])
            if n_flat - len(removed) == 0:
                new_edge_coverage = 0.0
            elif len(instance_edge_types) == 0:
                new_edge_coverage = 1.0
            else:
                arr = base_row_max.copy()
                if removed:
                    removed_set = set(removed)
                    affected: Set[int] = set()
                    for c in removed:
                        affected.update(rows_by_col[c])
                    for r in affected:
                        arr[r] = max((s for j, s in base_rows[r]
                                      if j not in removed_set), default=0.0)
                # Full-array mean every time (pairwise summation), never an
                # incremental update — matches coverage_sparse bit for bit.
                new_edge_coverage = np.mean(arr)

        node_coverage_loss = original_node_coverage - new_node_coverage
        edge_coverage_loss = original_edge_coverage - new_edge_coverage

        if node_coverage_loss < NODE_THETA and edge_coverage_loss < EDGE_THETA:
            cnt += 1

    _score_time_acc += time.time() - _t
    return 1 - cnt / num_schema_nodes


def build_producer_map(node_types: List[NodeType], edge_types: List[EdgeType]
                       ) -> Dict[_FlattenKey, Set[str]]:
    """For each flatten output key, the set of S* edge ids that generate it.

    Retraces flatten_in_memory's four generation rules (seed / flatten2 /
    flatten3 / flatten4) on the full S*. Removing a non-EXTENDS edge X
    removes exactly the columns whose producer set is {X}: exclusion of a
    non-EXTENDS edge changes neither the node set nor the ancestor relation,
    so the surviving keys are those with at least one other producer.
    Keys are (src_id, label, dst_id, mandatory, optional) = utils.py:516.
    """
    extends_edges = [e for e in edge_types if e.label == "EXTENDS"]
    non_extends_edges = [e for e in edge_types if e.label != "EXTENDS"]

    parents_of: Dict[str, List[str]] = defaultdict(list)
    for e in extends_edges:
        parents_of[e.src_node_type.node_id].append(e.dst_node_type.node_id)

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
    descendants_of: Dict[str, List[str]] = defaultdict(list)
    for node_id, ancs in ancestors_of.items():
        for a_id in ancs:
            descendants_of[a_id].append(node_id)

    producers: Dict[_FlattenKey, Set[str]] = defaultdict(set)

    # seed
    for e in non_extends_edges:
        key = (e.src_node_type.node_id, e.label, e.dst_node_type.node_id,
               e.mandatory_props, e.optional_props)
        producers[key].add(e.edge_id)

    # flatten2 (outgoing) + flatten3 (incoming) — skip self-loops on ancestor
    for desc_id, anc_ids in ancestors_of.items():
        for anc_id in anc_ids:
            for e in non_extends_edges:
                src_id = e.src_node_type.node_id
                dst_id = e.dst_node_type.node_id
                if src_id == anc_id and dst_id != anc_id:
                    producers[(desc_id, e.label, dst_id,
                               e.mandatory_props, e.optional_props)].add(e.edge_id)
                if dst_id == anc_id and src_id != anc_id:
                    producers[(src_id, e.label, desc_id,
                               e.mandatory_props, e.optional_props)].add(e.edge_id)

    # flatten4: self-loops on an ancestor propagate to the full clan
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
                    producers[(n1_id, sl.label, n2_id,
                               sl.mandatory_props, sl.optional_props)].add(sl.edge_id)

    return producers


def calc_edge_concision_sparse(
        instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
        original_node_coverage: float, original_edge_coverage: float, flatten_edge_num: int,
        label_w, mandatory_w, optional_w, endpoint_w, gamma,
        star_node_types: List[NodeType], star_edge_types: List[EdgeType],
        schema_edge_types: List[EdgeType],
        rows: List[List[Tuple[int, float]]],
        row_max: np.ndarray,
        cardinality_w=0.0
) -> float:
    """utils.calc_edge_concision on the sparse matrix.

    Takes the flatten output (schema_edge_types) plus the sparse matrix and
    row maxima already computed for coverage, instead of the dense matrix.
    """
    global _score_time_acc
    num_instance_edges = len(instance_edge_types)
    num_schema_edges = len(star_edge_types)
    if num_schema_edges == 0:
        return 1.0
    elif num_schema_edges > 0 and num_instance_edges == 0:
        return 0.0

    EDGE_THETA = 1.0 if flatten_edge_num == 0 else gamma * \
        original_edge_coverage / flatten_edge_num

    n_flat_edges = len(schema_edge_types)

    # rows containing each column, for row-max recomputation after deletion
    def _rows_by_col() -> List[List[int]]:
        by_col: List[List[int]] = [[] for _ in range(n_flat_edges)]
        for r, row in enumerate(rows):
            for j, _ in row:
                by_col[j].append(r)
        return by_col

    # Path 1 — no EXTENDS: delete one flattened column at a time.
    if not any(e.label == "EXTENDS" for e in star_edge_types):
        if n_flat_edges == 0:
            return 1.0

        _t = time.time()
        by_col = _rows_by_col()

        # NOTE: _edge_key deliberately omits properties, exactly like the
        # dense implementation — do not "fix".
        def _edge_key(e: EdgeType) -> Tuple[str, str, str]:
            return (e.src_node_type.node_id, e.label, e.dst_node_type.node_id)

        key_count: Dict[Tuple[str, str, str], int] = {}
        col_of_key: Dict[Tuple[str, str, str], int] = {}
        for e in star_edge_types:
            k = _edge_key(e)
            key_count[k] = key_count.get(k, 0) + 1
            if k not in col_of_key:
                col_of_key[k] = len(col_of_key)

        col_redundant: List[bool] = [False] * n_flat_edges
        for i in range(n_flat_edges):
            if n_flat_edges - 1 == 0:
                new_edge_cov = 0.0
            else:
                arr = row_max.copy()
                for r in by_col[i]:
                    arr[r] = max((s for j, s in rows[r] if j != i), default=0.0)
                # rows > 0 here, so calc_coverage would take the mean branch
                new_edge_cov = np.mean(arr)
            col_redundant[i] = (original_edge_coverage -
                                new_edge_cov < EDGE_THETA)

        cnt = 0
        for e in star_edge_types:
            k = _edge_key(e)
            if key_count[k] > 1 or col_redundant[col_of_key[k]]:
                cnt += 1
        _score_time_acc += time.time() - _t
        return 1 - cnt / len(star_edge_types)

    # Path 2 — EXTENDS present: fold the per-candidate re-flatten into one
    # pass with the producer map.
    candidate_edges = [e for e in star_edge_types if e.label != "EXTENDS"]
    num_candidate_edges = len(candidate_edges)
    if num_candidate_edges == 0:
        return 1.0
    num_star_nodes = len(star_node_types)
    NODE_THETA = gamma * original_node_coverage / \
        num_star_nodes if num_star_nodes > 0 else 1.0

    # The producer-map shortcut relies on the flatten dedup key, which does
    # not include has_cardinality_error (utils.py:516): with a non-zero
    # cardinality weight, deleting the first producer of a shared key could
    # change the surviving edge's cardinality flag and thus its similarity.
    # Refuse loudly instead of silently returning wrong scores.
    assert cardinality_w == 0.0, (
        "sparse EXTENDS path requires cardinality_w == 0.0 "
        f"(got {cardinality_w})")

    # Excluding a non-EXTENDS edge never changes the flattened node set
    # (extends_edges and node_types are untouched), so the node-side
    # coverage loss is exactly 0.0. Verify on one sample instead of assuming.
    sample = flatten_in_memory(star_node_types, star_edge_types,
                               exclude_edge_id=candidate_edges[0].edge_id)[0]
    full_nodes = {n.node_id: n for n in flatten_in_memory(
        star_node_types, star_edge_types)[0]}
    assert len(sample) == len(full_nodes) and all(
        full_nodes[n.node_id] == n for n in sample), (
        "flattened node set changed when excluding a non-EXTENDS edge")
    node_cond = (original_node_coverage - original_node_coverage) < NODE_THETA

    _t = time.time()
    producers = build_producer_map(star_node_types, star_edge_types)
    col_of_key: Dict[_FlattenKey, int] = {
        (e.src_node_type.node_id, e.label, e.dst_node_type.node_id,
         e.mandatory_props, e.optional_props): j
        for j, e in enumerate(schema_edge_types)}
    assert set(producers.keys()) == set(col_of_key.keys()), (
        "producer map keys do not match flatten_in_memory columns "
        f"({len(producers)} vs {len(col_of_key)})")

    # Columns whose sole producer is edge X, per X.
    sole_cols: Dict[str, List[int]] = defaultdict(list)
    for key, prods in producers.items():
        if len(prods) == 1:
            sole_cols[next(iter(prods))].append(col_of_key[key])

    by_col = _rows_by_col()

    cnt = 0
    _n_done = 0
    _prog_t0 = time.time()
    _prog_last = _prog_t0
    for edge_type in candidate_edges:
        _n_done += 1
        _now = time.time()
        if _now - _prog_last >= 60.0:
            _prog_last = _now
            print(f"[c2-progress] con_e {_n_done}/{num_candidate_edges} "
                  f"elapsed={_now - _prog_t0:.0f}s", flush=True)
        removed = sole_cols.get(edge_type.edge_id, [])
        if n_flat_edges - len(removed) == 0:
            new_edge_coverage = 0.0
        else:
            arr = row_max.copy()
            if removed:
                removed_set = set(removed)
                affected: Set[int] = set()
                for c in removed:
                    affected.update(by_col[c])
                for r in affected:
                    arr[r] = max((s for j, s in rows[r]
                                  if j not in removed_set), default=0.0)
            # Recompute the mean over the full array every time (pairwise
            # summation), never update it incrementally (pitfall 4).
            new_edge_coverage = np.mean(arr)
        if node_cond and original_edge_coverage - new_edge_coverage < EDGE_THETA:
            cnt += 1
    _score_time_acc += time.time() - _t

    return 1 - cnt / num_candidate_edges


def _eval_c2_sparse_core(
    instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
    star_node_types: List[NodeType], star_edge_types: List[EdgeType],
    label_w, mandatory_w, optional_w, eff_endpoint_w, gamma, eff_cardinality_w,
    timings: Optional[Dict[str, float]] = None,
):
    """Shared scoring pipeline; returns the six score components."""
    _t0 = time.time()
    schema_node_types, schema_edge_types = flatten_in_memory(
        star_node_types, star_edge_types)
    print(f"[c2-progress] flatten done: {len(schema_node_types)} node types, "
          f"{len(schema_edge_types)} edge types ({time.time() - _t0:.0f}s)",
          flush=True)

    node_sim_matrix = create_node_sim_matrix(
        instance_node_types, schema_node_types,
        label_w, mandatory_w, optional_w)
    rows = build_edge_sim_sparse(
        instance_edge_types, schema_edge_types, instance_node_types,
        label_w, mandatory_w, optional_w, eff_endpoint_w, eff_cardinality_w)
    row_max = row_max_array(rows)
    print(f"[c2-progress] similarity matrices built ({time.time() - _t0:.0f}s)",
          flush=True)

    node_coverage = calc_coverage(node_sim_matrix)
    edge_coverage = coverage_sparse(
        row_max, len(instance_edge_types), len(schema_edge_types))

    # == dense edge_sim_matrix.shape[1]: np.zeros((n_i, n_s)) keeps n_s cols
    # even when there are no instance edges.
    flatten_edge_num = len(schema_edge_types)
    if timings is not None:
        timings["cov_pass"] = time.time() - _t0

    _t1 = time.time()
    print("[c2-progress] coverage done, starting con_v", flush=True)
    node_concision = calc_node_concision_sparse(
        instance_node_types, instance_edge_types,
        node_coverage, edge_coverage, flatten_edge_num,
        label_w, mandatory_w, optional_w, eff_endpoint_w, gamma,
        star_node_types, star_edge_types, cardinality_w=eff_cardinality_w,
        base_schema_node_types=schema_node_types,
        base_schema_edge_types=schema_edge_types,
        base_node_sim_matrix=node_sim_matrix,
        base_rows=rows,
        base_row_max=row_max)
    if timings is not None:
        timings["con_v"] = time.time() - _t1
    print(f"[c2-progress] con_v done ({time.time() - _t1:.0f}s), "
          "starting con_e", flush=True)

    _t2 = time.time()
    edge_concision = calc_edge_concision_sparse(
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
        schema_edge_types=schema_edge_types,
        rows=rows,
        row_max=row_max,
        cardinality_w=eff_cardinality_w)
    if timings is not None:
        timings["con_e"] = time.time() - _t2
    print(f"[c2-progress] con_e done ({time.time() - _t2:.0f}s)", flush=True)

    node_c2 = 2 * (node_coverage * node_concision) / (node_coverage +
                                                      node_concision) if (node_coverage + node_concision) > 0 else 0.0
    edge_c2 = 2 * (edge_coverage * edge_concision) / (edge_coverage +
                                                      edge_concision) if (edge_coverage + edge_concision) > 0 else 0.0

    return (node_coverage, edge_coverage, node_concision, edge_concision,
            node_c2, edge_c2)


def eval_c2_sparse(uri, auth, instance_db_name, schema_db_name,
                   label_w, mandatory_w, optional_w, endpoint_w, gamma,
                   include_cardinality=False):
    """Drop-in replacement for utils.eval_c2 (same signature, same 10-tuple)."""
    global _score_time_acc
    assert label_w + mandatory_w + optional_w == 1
    assert 0.0 <= endpoint_w <= 1.0

    utils._flatten_time_acc = 0.0
    utils._score_time_acc = 0.0
    _score_time_acc = 0.0
    _node_col_cache.clear()

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

    scores = _eval_c2_sparse_core(
        instance_node_types, instance_edge_types,
        star_node_types, star_edge_types,
        label_w, mandatory_w, optional_w, eff_endpoint_w, gamma,
        eff_cardinality_w)

    phase2_time = time.time() - t1
    score_time = utils._score_time_acc + _score_time_acc
    other_time = phase2_time - utils._flatten_time_acc - score_time

    return scores + (abs_time, utils._flatten_time_acc, score_time, other_time)


def eval_c2_sparse_from_types(
    instance_node_types: List[NodeType], instance_edge_types: List[EdgeType],
    star_node_types: List[NodeType], star_edge_types: List[EdgeType],
    label_w, mandatory_w, optional_w, endpoint_w, gamma, include_cardinality=False,
    timings: Optional[Dict[str, float]] = None,
):
    """Sparse counterpart of utils.eval_c2_from_types (six scores, no DB).

    `timings`, when given, receives the cov_pass / con_v / con_e wall times
    (used by the Full-DBpedia benchmark).
    """
    global _score_time_acc
    assert label_w + mandatory_w + optional_w == 1
    assert 0.0 <= endpoint_w <= 1.0

    _score_time_acc = 0.0
    _node_col_cache.clear()

    eff_endpoint_w = 1 / 3 if include_cardinality else endpoint_w
    eff_cardinality_w = 1 / 3 if include_cardinality else 0.0

    return _eval_c2_sparse_core(
        instance_node_types, instance_edge_types,
        star_node_types, star_edge_types,
        label_w, mandatory_w, optional_w, eff_endpoint_w, gamma,
        eff_cardinality_w, timings=timings)
