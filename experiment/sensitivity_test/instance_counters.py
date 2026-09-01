"""Raw Abs(G) aggregation counters, and Abs(G) rebuilt from them.

The instance-irregularity experiment perturbs the *instance* graph G and re-scores C2(G', S) dozens of
times. Writing those perturbations into Neo4j is out of the question: the
target graph is Full DBpedia (19.9M nodes) and it must stay untouched.

The way out is that ``utils._get_all_node_and_edge_types_from_instance``
builds Abs(G) from **four aggregation queries and nothing else**:

  (1) nodes per label set                (2) property occurrences per label set
  (3) edges per (srcLS, relType, dstLS)  (4) property occurrences per edge triple

mandatory / optional is decided purely by "does the occurrence count equal the
group's total". Abs(G) is therefore a pure function of those counters, so a
perturbation can be applied to the counters instead of to the database — the
result is Abs(G') exactly, not an approximation.

``build_types`` below mirrors steps (3)-(10) of utils.py:64-146 verbatim,
including the set-difference iteration that fixes the list order, so that the
unperturbed counters reproduce ``get_all_node_and_edge_types_from_instance``
element for element.
"""

import os
import pickle
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict, Dict, FrozenSet, List, Set, Tuple

from neo4j import GraphDatabase

from ..common.entity_def import EdgeType, NodeType

from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Separator conventions of utils.py: a label set is joined with ":" and an
# edge triple is "<srcLS>::<relType>::<dstLS>". Reused here so that the keys
# are interchangeable with the reference implementation.
LS_SEP = ":"
EDGE_SEP = "::"


def join_ls(labels) -> str:
    """Label set -> the joined key used by utils.py (sorted, ':' separated)."""
    return LS_SEP.join(sorted(labels))


def edge_key(src_ls: str, rel_type: str, dst_ls: str) -> str:
    return src_ls + EDGE_SEP + rel_type + EDGE_SEP + dst_ls


@dataclass
class Counters:
    """The four raw aggregation results, before any mandatory/optional call."""

    node_label_cnt: Dict[str, int] = field(default_factory=dict)
    node_label_prop_cnt: Dict[str, Dict[str, int]] = field(default_factory=dict)
    edge_label_cnt: Dict[str, int] = field(default_factory=dict)
    edge_label_prop_cnt: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def copy(self) -> "Counters":
        """Deep enough copy: the inner per-property dicts are copied too."""
        return Counters(
            node_label_cnt=dict(self.node_label_cnt),
            node_label_prop_cnt={k: dict(v)
                                 for k, v in self.node_label_prop_cnt.items()},
            edge_label_cnt=dict(self.edge_label_cnt),
            edge_label_prop_cnt={k: dict(v)
                                 for k, v in self.edge_label_prop_cnt.items()},
        )

    @property
    def n_label_sets(self) -> int:
        return len(self.node_label_cnt)

    @property
    def n_edge_patterns(self) -> int:
        return len(self.edge_label_cnt)

    @property
    def n_nodes(self) -> int:
        return sum(self.node_label_cnt.values())

    @property
    def n_edges(self) -> int:
        return sum(self.edge_label_cnt.values())


# The four queries are byte-for-byte the ones in utils.py:34-105 so that the
# row order — and hence the dict insertion order build_types depends on — is
# the same as the reference implementation's.
_Q_NODE_CNT = """
        MATCH (n)
        WITH labels(n) AS labelSet, COUNT(n) AS cnt
        RETURN labelSet, cnt
    """
_Q_NODE_PROP = """
        MATCH (n)
        UNWIND keys(n) AS prop
        WITH labels(n) AS labelSet, prop, count(*) AS cnt
        RETURN labelSet, prop, cnt
    """
_Q_EDGE_CNT = """
        MATCH ()-[r]->()
        WITH type(r) AS relType, labels(startNode(r)) AS srcLabelSet, labels(endNode(r)) AS dstLabelSet, COUNT(r) AS cnt
        RETURN srcLabelSet, relType, dstLabelSet, cnt
    """
_Q_EDGE_PROP = """
        MATCH ()-[r]->()
        UNWIND keys(r) AS prop
        WITH type(r) AS relType, labels(startNode(r)) AS srcLabelSet, labels(endNode(r)) AS dstLabelSet, prop, count(*) AS cnt
        RETURN srcLabelSet, relType, dstLabelSet, prop, cnt
    """


def fetch_counters(db_name: str, uri: str = URI, auth: Tuple[str, str] = AUTH,
                   cache: bool = True, verbose: bool = True) -> Counters:
    """Run the four aggregation queries against `db_name` (read-only).

    Roughly 90 s on Full DBpedia, so the result is pickled next to the other
    results and reused across every condition of the experiment.
    """
    cache_path = os.path.join(RESULTS_DIR, f"counters_{db_name}.pkl")
    if cache and os.path.exists(cache_path):
        with open(cache_path, "rb") as f:
            counters = pickle.load(f)
        if verbose:
            print(f"[counters] loaded cache {cache_path} "
                  f"({counters.n_label_sets} label sets, "
                  f"{counters.n_edge_patterns} edge patterns)")
        return counters

    t0 = time.time()
    counters = Counters()
    driver = GraphDatabase.driver(uri, auth=auth, database=db_name)
    try:
        with driver.session() as session:
            for rec in session.run(_Q_NODE_CNT):
                counters.node_label_cnt[join_ls(rec["labelSet"])] = rec["cnt"]
        with driver.session() as session:
            for rec in session.run(_Q_NODE_PROP):
                key = join_ls(rec["labelSet"])
                counters.node_label_prop_cnt.setdefault(
                    key, {})[rec["prop"]] = rec["cnt"]
        with driver.session() as session:
            for rec in session.run(_Q_EDGE_CNT):
                key = edge_key(join_ls(rec["srcLabelSet"]), rec["relType"],
                               join_ls(rec["dstLabelSet"]))
                counters.edge_label_cnt[key] = rec["cnt"]
        with driver.session() as session:
            for rec in session.run(_Q_EDGE_PROP):
                key = edge_key(join_ls(rec["srcLabelSet"]), rec["relType"],
                               join_ls(rec["dstLabelSet"]))
                counters.edge_label_prop_cnt.setdefault(
                    key, {})[rec["prop"]] = rec["cnt"]
    finally:
        driver.close()

    if verbose:
        print(f"[counters] {db_name}: {counters.n_nodes} nodes / "
              f"{counters.n_edges} edges / {counters.n_label_sets} label sets / "
              f"{counters.n_edge_patterns} edge patterns "
              f"({time.time() - t0:.1f}s)")
    if cache:
        os.makedirs(RESULTS_DIR, exist_ok=True)
        with open(cache_path, "wb") as f:
            pickle.dump(counters, f, protocol=pickle.HIGHEST_PROTOCOL)
    return counters


def build_types(counters: Counters) -> Tuple[List[NodeType], List[EdgeType]]:
    """Abs(G) from the counters — utils.py:64-146 with the DB reads removed.

    Kept step-for-step identical (including the `set` difference in step 3,
    whose iteration order decides where the property-less label sets land in
    the list) so that the output list order matches the reference, not just
    the multiset of types.
    """
    node_label_cnt = counters.node_label_cnt
    node_label_prop_cnt: DefaultDict[str, Dict[str, int]] = defaultdict(dict)
    node_label_prop_cnt.update(counters.node_label_prop_cnt)

    # (3)(4) label sets whose nodes carry no property at all
    no_prop_label: Set[str] = set(
        node_label_cnt.keys()) - set(node_label_prop_cnt.keys())
    for label in no_prop_label:
        node_label_prop_cnt[label] = {}

    # (5) Build node types
    node_types: List[NodeType] = []
    for label, prop_dict in node_label_prop_cnt.items():
        labels = frozenset(label.split(LS_SEP))
        mandatory_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt == node_label_cnt[label]])
        optional_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt < node_label_cnt[label]])
        node_types.append(NodeType(labels, mandatory_props, optional_props))

    edge_label_cnt = counters.edge_label_cnt
    edge_label_prop_cnt: DefaultDict[str, Dict[str, int]] = defaultdict(dict)
    edge_label_prop_cnt.update(counters.edge_label_prop_cnt)

    # (8)(9) edge triples without properties
    no_prop_edge_label = set(edge_label_cnt.keys()) - \
        set(edge_label_prop_cnt.keys())
    for label in no_prop_edge_label:
        edge_label_prop_cnt[label] = {}

    # (10) Build edge types. utils.py resolves the endpoints with a linear
    # scan over node_types; an index by label set is used here instead, which
    # returns the very same objects (endpoint identity is what
    # utils_sparse.build_edge_sim_sparse keys its row lookups on).
    node_by_labels: Dict[FrozenSet[str], NodeType] = {}
    for nt in node_types:
        if nt.labels not in node_by_labels:
            node_by_labels[nt.labels] = nt

    edge_types: List[EdgeType] = []
    for label, prop_dict in edge_label_prop_cnt.items():
        src_label, rel_type, dst_label = label.split(EDGE_SEP)
        src_labels = frozenset(src_label.split(LS_SEP))
        dst_labels = frozenset(dst_label.split(LS_SEP))
        mandatory_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt == edge_label_cnt[label]])
        optional_props = frozenset(
            [prop for prop, cnt in prop_dict.items() if cnt < edge_label_cnt[label]])
        src_node_type = node_by_labels.get(src_labels)
        dst_node_type = node_by_labels.get(dst_labels)
        if src_node_type is None or dst_node_type is None:
            raise ValueError(
                f"src_node_type or dst_node_type is None: {src_label}::{dst_label}")
        edge_types.append(EdgeType(rel_type, mandatory_props,
                                   optional_props, src_node_type, dst_node_type))

    return node_types, edge_types
