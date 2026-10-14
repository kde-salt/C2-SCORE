"""Instance-side perturbations, applied to the Abs(G) counters.

The experiment applies five kinds of irregularity on k = 1, 10, 100 nodes
of one high-frequency label group:

  A1  same-spurious-label     every selected node gets the *same* new label
  A2  unique-spurious-labels  every selected node gets a *different* new label
  B   missing-label           one existing label is dropped from every node
  C1  spurious-property       a new property key is added to every node
  C2  missing-property        one existing property key is dropped

Each perturbation is expressed as "these k nodes end up with this label set
and this property key set", and applied to the counters of
`instance_counters` — the database is only ever read.

Two properties of the update are worth stating because the exactness of the
whole experiment rests on them:

* Deltas are accumulated first and applied once. A label set whose count
  happens to return to its original value therefore keeps its position in the
  dict, so the unchanged part of Abs(G) keeps the reference list order.
* Every edge incident to a selected node is re-keyed from BOTH endpoints, so
  an edge between two selected nodes moves to the pattern that has both new
  label sets. Edges are deduplicated by element id first, which also takes
  care of self-loops.
"""

import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from neo4j import GraphDatabase

from .instance_counters import AUTH, URI, Counters, edge_key, join_ls

# Conditions. Each "same" condition has a "unique/random" counterpart, so
# that B and C get the A1-vs-A2 treatment: hold the perturbed nodes fixed and
# vary only how much type diversity the perturbation introduces.
A1 = "A1_same_spurious_label"
A2 = "A2_unique_spurious_labels"
B = "B_missing_label"                       # B1: the same label for every node
B2 = "B2_random_missing_label"
C_ADD = "C_add_spurious_property"           # C1: the same key for every node
C_ADD2 = "C_add2_unique_spurious_properties"
C_DEL = "C_del_missing_property"            # C1: the same key for every node
C_DEL2 = "C_del2_random_missing_property"
CONDITIONS = (A1, A2, B, B2, C_ADD, C_ADD2, C_DEL, C_DEL2)

# Conditions whose replacement depends on a random draw per node.
RANDOMIZED = (B2, C_DEL2)

# Names injected by the perturbations. Prefixed so that they can never
# collide with a DBpedia label (URI local names) or property key (IRIs).
SPUR_LABEL = "T2SpuriousLabel"
SPUR_LABEL_FMT = "T2SpuriousLabel{:04d}"
SPUR_PROP = "t2SpuriousProperty"
SPUR_PROP_FMT = "t2SpuriousProperty{:04d}"


@dataclass
class NodeCtx:
    """What a selected node contributes to the counters."""

    element_id: str
    labels: Tuple[str, ...]
    keys: Tuple[str, ...]


@dataclass
class EdgeCtx:
    """An edge incident to at least one selected node."""

    element_id: str
    rel_type: str
    src_id: str
    dst_id: str
    src_labels: Tuple[str, ...]
    dst_labels: Tuple[str, ...]
    keys: Tuple[str, ...]


def sample_group_ids(db_name: str, labels: Sequence[str], offsets: Iterable[int],
                     uri: str = URI, auth: Tuple[str, str] = AUTH) -> Dict[int, str]:
    """Element ids of the nodes at the given positions of a label group.

    One streaming scan of the group, keeping only the requested offsets, so
    that sampling 100 nodes out of 1.5M costs one label scan and O(k) memory.
    The scan order is Neo4j's and is stable for a read-only database, which is
    what makes an offset a reproducible way to name a node.
    """
    wanted = sorted(set(offsets))
    if not wanted:
        return {}
    label_pattern = "".join(f":`{lb}`" for lb in labels)
    query = (f"MATCH (n{label_pattern}) WHERE size(labels(n)) = $n_labels "
             f"RETURN elementId(n) AS id")
    picked: Dict[int, str] = {}
    driver = GraphDatabase.driver(uri, auth=auth, database=db_name)
    try:
        with driver.session() as session:
            result = session.run(query, n_labels=len(labels))
            next_i = 0
            for pos, rec in enumerate(result):
                if pos == wanted[next_i]:
                    picked[pos] = rec["id"]
                    next_i += 1
                    if next_i == len(wanted):
                        break
    finally:
        driver.close()
    if len(picked) != len(wanted):
        raise ValueError(
            f"group {labels} yielded {len(picked)} of {len(wanted)} requested "
            f"offsets (max requested {wanted[-1]})")
    return picked


_Q_NODES = """
MATCH (n) WHERE elementId(n) IN $ids
RETURN elementId(n) AS id, labels(n) AS labels, keys(n) AS keys
"""

_Q_EDGES = """
MATCH (n)-[r]-(m) WHERE elementId(n) IN $ids
RETURN DISTINCT elementId(r) AS id, type(r) AS rel_type,
       elementId(startNode(r)) AS src_id, labels(startNode(r)) AS src_labels,
       elementId(endNode(r)) AS dst_id, labels(endNode(r)) AS dst_labels,
       keys(r) AS keys
"""


def fetch_context(db_name: str, element_ids: Sequence[str],
                  uri: str = URI, auth: Tuple[str, str] = AUTH
                  ) -> Tuple[Dict[str, NodeCtx], List[EdgeCtx]]:
    """Read the selected nodes and every edge incident to them (read-only)."""
    nodes: Dict[str, NodeCtx] = {}
    edges: List[EdgeCtx] = []
    driver = GraphDatabase.driver(uri, auth=auth, database=db_name)
    try:
        with driver.session() as session:
            for rec in session.run(_Q_NODES, ids=list(element_ids)):
                nodes[rec["id"]] = NodeCtx(rec["id"], tuple(rec["labels"]),
                                           tuple(rec["keys"]))
            for rec in session.run(_Q_EDGES, ids=list(element_ids)):
                edges.append(EdgeCtx(
                    rec["id"], rec["rel_type"],
                    rec["src_id"], rec["dst_id"],
                    tuple(rec["src_labels"]), tuple(rec["dst_labels"]),
                    tuple(rec["keys"])))
    finally:
        driver.close()
    missing = set(element_ids) - set(nodes)
    if missing:
        raise ValueError(f"{len(missing)} selected nodes not found")
    return nodes, edges


def apply_perturbation(base: Counters,
                       nodes: Dict[str, NodeCtx],
                       edges: Sequence[EdgeCtx],
                       new_labels: Dict[str, Tuple[str, ...]],
                       new_keys: Dict[str, Tuple[str, ...]]) -> Counters:
    """Counters of Abs(G') for the given per-node label / key replacements.

    `new_labels` / `new_keys` are keyed by element id; a node missing from
    either map keeps its original labels / keys.
    """
    out = base.copy()

    node_cnt_delta: Dict[str, int] = defaultdict(int)
    node_prop_delta: Dict[str, Dict[str, int]] = defaultdict(
        lambda: defaultdict(int))
    edge_cnt_delta: Dict[str, int] = defaultdict(int)
    edge_prop_delta: Dict[str, Dict[str, int]] = defaultdict(
        lambda: defaultdict(int))

    def labels_of(node_id: str, fallback: Tuple[str, ...]) -> Tuple[str, ...]:
        return new_labels.get(node_id, fallback)

    for node_id, ctx in nodes.items():
        old_ls = join_ls(ctx.labels)
        new_ls = join_ls(labels_of(node_id, ctx.labels))
        old_keys = ctx.keys
        nkeys = new_keys.get(node_id, ctx.keys)

        node_cnt_delta[old_ls] -= 1
        node_cnt_delta[new_ls] += 1
        for key in old_keys:
            node_prop_delta[old_ls][key] -= 1
        for key in nkeys:
            node_prop_delta[new_ls][key] += 1

    seen_edges: Set[str] = set()
    for e in edges:
        if e.element_id in seen_edges:
            continue
        seen_edges.add(e.element_id)
        old_key = edge_key(join_ls(e.src_labels), e.rel_type,
                           join_ls(e.dst_labels))
        new_key = edge_key(join_ls(labels_of(e.src_id, e.src_labels)),
                           e.rel_type,
                           join_ls(labels_of(e.dst_id, e.dst_labels)))
        edge_cnt_delta[old_key] -= 1
        edge_cnt_delta[new_key] += 1
        for key in e.keys:
            edge_prop_delta[old_key][key] -= 1
            edge_prop_delta[new_key][key] += 1

    _apply_deltas(out.node_label_cnt, out.node_label_prop_cnt,
                  node_cnt_delta, node_prop_delta)
    _apply_deltas(out.edge_label_cnt, out.edge_label_prop_cnt,
                  edge_cnt_delta, edge_prop_delta)
    return out


def _apply_deltas(cnt: Dict[str, int], prop_cnt: Dict[str, Dict[str, int]],
                  cnt_delta: Dict[str, int],
                  prop_delta: Dict[str, Dict[str, int]]) -> None:
    """Add the accumulated deltas, dropping groups and keys that reach zero."""
    for group, delta in cnt_delta.items():
        if delta == 0:
            continue
        new_value = cnt.get(group, 0) + delta
        if new_value < 0:
            raise ValueError(f"negative count for {group!r}: {new_value}")
        if new_value == 0:
            cnt.pop(group, None)
        else:
            cnt[group] = new_value

    for group, per_key in prop_delta.items():
        inner = prop_cnt.get(group)
        for key, delta in per_key.items():
            if delta == 0:
                continue
            if inner is None:
                inner = {}
                prop_cnt[group] = inner
            new_value = inner.get(key, 0) + delta
            if new_value < 0:
                raise ValueError(
                    f"negative property count for {group!r}.{key!r}: {new_value}")
            if new_value == 0:
                inner.pop(key, None)
            else:
                inner[key] = new_value
        # A group whose properties all vanished must leave the property map
        # entirely: re-reading the database would not list it in query (2)
        # either, and build_types picks such groups up through its
        # set-difference branch instead.
        if inner is not None and not inner:
            prop_cnt.pop(group, None)


def build_replacement(condition: str, selected: List[NodeCtx],
                      target_label: Optional[str] = None,
                      target_prop: Optional[str] = None,
                      candidate_props: Optional[Sequence[str]] = None,
                      rng: Optional[random.Random] = None
                      ) -> Tuple[Dict[str, Tuple[str, ...]], Dict[str, Tuple[str, ...]], str]:
    """Per-node label / key replacements for one condition.

    Returns (new_labels, new_keys, detail) where `detail` names what was
    injected or removed, for the CSV. `rng` is required by the randomized
    conditions and must be seeded by the caller so the draw is reproducible;
    `candidate_props` lists the properties C_DEL2 may pick from.
    """
    new_labels: Dict[str, Tuple[str, ...]] = {}
    new_keys: Dict[str, Tuple[str, ...]] = {}
    if condition in RANDOMIZED and rng is None:
        raise ValueError(f"condition {condition} needs an rng")

    if condition == A1:
        for ctx in selected:
            new_labels[ctx.element_id] = ctx.labels + (SPUR_LABEL,)
        detail = f"+label {SPUR_LABEL}"

    elif condition == A2:
        for i, ctx in enumerate(selected):
            new_labels[ctx.element_id] = ctx.labels + \
                (SPUR_LABEL_FMT.format(i),)
        detail = (f"+label {SPUR_LABEL_FMT.format(0)}.."
                  f"{SPUR_LABEL_FMT.format(len(selected) - 1)}")

    elif condition == B:
        if target_label is None:
            raise ValueError("condition B needs target_label")
        for ctx in selected:
            if target_label not in ctx.labels:
                raise ValueError(
                    f"node {ctx.element_id} has no label {target_label}")
            new_labels[ctx.element_id] = tuple(
                lb for lb in ctx.labels if lb != target_label)
        detail = f"-label {target_label}"

    elif condition == B2:
        # Each node drops a label drawn from its own label set, so the number
        # of resulting label sets is capped by |L| however large k gets —
        # unlike A2, where a fresh label can always be invented.
        drops: Set[str] = set()
        for ctx in selected:
            drop = rng.choice(sorted(ctx.labels))
            drops.add(drop)
            new_labels[ctx.element_id] = tuple(
                lb for lb in ctx.labels if lb != drop)
        detail = f"-label random of {{{', '.join(sorted(drops))}}}"

    elif condition == C_ADD:
        for ctx in selected:
            new_keys[ctx.element_id] = ctx.keys + (SPUR_PROP,)
        detail = f"+prop {SPUR_PROP}"

    elif condition == C_ADD2:
        for i, ctx in enumerate(selected):
            new_keys[ctx.element_id] = ctx.keys + (SPUR_PROP_FMT.format(i),)
        detail = (f"+prop {SPUR_PROP_FMT.format(0)}.."
                  f"{SPUR_PROP_FMT.format(len(selected) - 1)}")

    elif condition == C_DEL2:
        # Draws from everything the node carries, mandatory or optional
        # (owner's call). Dropping an optional key usually leaves the node
        # type untouched, so the visible effect concentrates on the mandatory
        # ones — which is exactly the asymmetry the condition is meant to show.
        removed: Set[str] = set()
        for ctx in selected:
            if not ctx.keys:
                raise ValueError(f"node {ctx.element_id} has no property")
            available = ([p for p in candidate_props if p in ctx.keys]
                         if candidate_props else list(ctx.keys))
            drop = rng.choice(sorted(available))
            removed.add(drop)
            new_keys[ctx.element_id] = tuple(
                k for k in ctx.keys if k != drop)
        detail = f"-prop random ({len(removed)} distinct keys hit)"

    elif condition == C_DEL:
        if target_prop is None:
            raise ValueError("condition C_DEL needs target_prop")
        for ctx in selected:
            if target_prop not in ctx.keys:
                raise ValueError(
                    f"node {ctx.element_id} has no property {target_prop}")
            new_keys[ctx.element_id] = tuple(
                k for k in ctx.keys if k != target_prop)
        detail = f"-prop {target_prop}"

    else:
        raise ValueError(f"unknown condition {condition!r}")

    return new_labels, new_keys, detail
