"""Instance-side irregularity (EQ1, Section 5.1, Figure 4).

The schema-side study perturbs the candidate schema. This one asks the
opposite question: what happens to Abs(G) and to C2 when the *input graph*
carries a handful of irregularities — a node with a spurious extra label, a
node missing a label it should have, a node with an odd property?

So the schema S is held fixed (SchemI's output on Full DBpedia) and only G is
perturbed, under the following conditions:

  A1 / A2  k nodes of one high-frequency label group get a spurious label —
           the same one (A1) or a different one each (A2). Comparing the two
           isolates the effect of the *number of label sets* from the effect
           of the number of irregular nodes.
  B        k nodes of a multi-label group lose one existing label.
  C        k nodes gain a spurious property (C_add) or lose an existing
           mandatory one (C_del); their label sets stay put.

The graph is never written to. Perturbations are applied to the Abs(G)
aggregation counters (see instance_counters), which reproduces Abs(G')
exactly, and all conditions are scored in one sweep (see batch_eval).

Usage:
    python -m experiment.sensitivity_test.instance_irregularity \
        --instance dbpedia --schema dbpedia-schemi --k 1,10,100 --trials 3
"""

import argparse
import csv
import os
import random
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from ..common import utils
from ..common.entity_def import NodeType
from . import batch_eval as be
from . import instance_counters as ic
from . import instance_perturb as ip

# Same weights as every other C2 experiment in this repository
# (eval_c2.py:34-36, scalability_test/main.py:82-84).
ALPHA, BETA, GAMMA = 0.5, 0.5, 0.15
WEIGHTS = dict(label_w=ALPHA, mandatory_w=(1 - ALPHA) / 2,
               optional_w=(1 - ALPHA) / 2, endpoint_w=BETA, gamma=GAMMA)

RESULTS_DIR = ic.RESULTS_DIR

CSV_HEADER = [
    "timestamp", "instance_db", "schema_db", "eval_mode",
    "condition", "k", "trial", "seed", "target_label_set", "detail",
    "n_label_sets", "n_node_types", "n_edge_patterns",
    "Cov_V", "Cov_E", "Con_V", "Con_E", "node_c2", "edge_c2", "c2",
    "batch_wall_sec", "cov_pass_sec", "con_v_sec", "con_e_sec", "notes",
]

# One population for A, B and C, so that every condition perturbs the same
# nodes and only the injected irregularity differs (owner's call).
#
# It has to be a multi-label group or B could not remove a label at all, and
# among those this is the one with the most labels, which sets how far B2 can
# push the label-set count (its ceiling is |L|, unlike A2's, which has none).
# Every multi-label group in DBpedia carries exactly two mandatory properties
# (IRI, label_name) and no rare ones, so no choice of group makes the property
# deletions unbounded.
# Keys are the ':'-joined SORTED label set, as instance_counters builds them.
DEFAULT_GROUP = {"dbpedia": "Activity:D0Activity:Q1914636:Q194189:Sales:Thing"}


def _derive_seed(base_seed: int, k: int, trial: int) -> int:
    """Deterministic per-(k, trial) seed, independent of PYTHONHASHSEED."""
    return base_seed * 1_000_003 + k * 10_007 + trial


def pick_multi_label_group(counters: ic.Counters, min_size: int) -> str:
    """Largest multi-label group with at least `min_size` nodes."""
    candidates = [(cnt, ls) for ls, cnt in counters.node_label_cnt.items()
                  if ic.LS_SEP in ls and cnt >= min_size]
    if not candidates:
        raise ValueError(f"no multi-label group with >= {min_size} nodes")
    return max(candidates)[1]


def _node_type_of(node_types: Sequence[NodeType], label_set: str) -> NodeType:
    labels = frozenset(label_set.split(ic.LS_SEP))
    for nt in node_types:
        if nt.labels == labels:
            return nt
    raise ValueError(f"label set {label_set} not present in Abs(G)")


def mandatory_properties(counters: ic.Counters, label_set: str) -> List[str]:
    """Property keys every node of the group carries."""
    props = counters.node_label_prop_cnt.get(label_set, {})
    total = counters.node_label_cnt[label_set]
    return sorted(k for k, cnt in props.items() if cnt == total)


def pick_target_property(counters: ic.Counters, label_set: str) -> Tuple[str, str]:
    """A property key to delete in C_del, plus a note on how it was chosen.

    Preference goes to a mandatory property (every node of the group has it),
    because deleting it from a single node demotes it to optional for the
    whole node type — the sharpest contrast against the label perturbations.
    """
    props = counters.node_label_prop_cnt.get(label_set, {})
    if not props:
        raise ValueError(f"group {label_set} has no properties to delete")
    total = counters.node_label_cnt[label_set]
    mandatory = mandatory_properties(counters, label_set)
    if mandatory:
        return mandatory[0], "mandatory property of the group"
    best = max(props.items(), key=lambda kv: (kv[1], kv[0]))
    return best[0], (f"no mandatory property; most frequent optional one "
                     f"({best[1]}/{total} nodes)")


def build_conditions(instance_db: str, counters: ic.Counters,
                     conditions: Sequence[str], ks: Sequence[int],
                     trials: int, base_seed: int, group: str,
                     remove_label: Optional[str],
                     uri: str, auth: Tuple[str, str],
                     verbose: bool = True) -> List[be.Condition]:
    """Baseline plus one Condition per (condition, k, trial)."""
    base_nodes, base_edges = ic.build_types(counters)
    out: List[be.Condition] = [be.Condition(
        name="baseline", node_types=base_nodes, edge_types=base_edges,
        meta=dict(condition="baseline", k=0, trial=0, seed="",
                  target_label_set="", detail="unperturbed",
                  notes="reference point for every other row"))]

    labels = group.split(ic.LS_SEP)

    if remove_label is None:
        remove_label = sorted(labels)[0]
    if remove_label not in labels:
        raise ValueError(f"--remove-label {remove_label} is not in {group}")
    target_prop, prop_note = pick_target_property(counters, group)
    if verbose:
        print(f"[setup] group {group} "
              f"({counters.node_label_cnt[group]} nodes, "
              f"{len(labels)} labels, "
              f"{len(counters.node_label_prop_cnt.get(group, {}))} property "
              f"keys of which {len(mandatory_properties(counters, group))} "
              f"mandatory)")
        print(f"[setup] B removes {remove_label}; B2 removes a random one of "
              f"{labels}")
        print(f"[setup] C_del removes {target_prop} ({prop_note}); "
              f"C_del2 removes a random one of each node's own keys")

    # Offsets are drawn per (k, trial) and SHARED by every condition, so any
    # two conditions differ only in what is injected, never in which nodes
    # were picked.
    size = counters.node_label_cnt[group]
    offsets: Dict[Tuple[int, int], List[int]] = {}
    for k in ks:
        if k > size:
            raise ValueError(f"k={k} exceeds group {group} size {size}")
        for trial in range(trials):
            rng = random.Random(_derive_seed(base_seed, k, trial))
            offsets[(k, trial)] = rng.sample(range(size), k)

    # One scan resolves every offset any condition needs.
    wanted = sorted({off for offs in offsets.values() for off in offs})
    t0 = time.time()
    ids_at = ip.sample_group_ids(
        instance_db, labels, wanted, uri=uri, auth=auth)
    if verbose:
        print(f"[setup] sampled {len(wanted)} nodes of {group} "
              f"({time.time() - t0:.1f}s)")

    for condition in conditions:
        for k in ks:
            for trial in range(trials):
                element_ids = [ids_at[off] for off in offsets[(k, trial)]]
                nodes, edges = ip.fetch_context(
                    instance_db, element_ids, uri=uri, auth=auth)
                selected = [nodes[eid] for eid in element_ids]
                # A separate, reproducible stream for the per-node draw of
                # the randomized conditions; the node sample itself is still
                # shared across every condition on this group.
                draw_rng = random.Random(
                    _derive_seed(base_seed, k, trial) * 31
                    + ip.CONDITIONS.index(condition))
                new_labels, new_keys, detail = ip.build_replacement(
                    condition, selected,
                    target_label=remove_label if condition == ip.B else None,
                    target_prop=target_prop if condition == ip.C_DEL else None,
                    rng=draw_rng)
                perturbed = ip.apply_perturbation(
                    counters, nodes, edges, new_labels, new_keys)
                node_types, edge_types = ic.build_types(perturbed)

                notes = _describe(condition, counters, perturbed, group,
                                  new_labels, edges)
                out.append(be.Condition(
                    name=f"{condition}_k{k}_t{trial}",
                    node_types=node_types, edge_types=edge_types,
                    meta=dict(condition=condition, k=k, trial=trial,
                              seed=_derive_seed(base_seed, k, trial),
                              target_label_set=group, detail=detail,
                              notes=notes)))
        if verbose:
            print(f"[setup] built {len(ks) * trials} conditions for {condition}")

    return out


def _describe(condition: str, base: ic.Counters, perturbed: ic.Counters,
              group: str, new_labels: Dict[str, Tuple[str, ...]],
              edges) -> str:
    """Short note on what the perturbation did to the counters."""
    d_ls = perturbed.n_label_sets - base.n_label_sets
    d_ep = perturbed.n_edge_patterns - base.n_edge_patterns
    parts = [f"label sets {d_ls:+d}", f"edge patterns {d_ep:+d}",
             f"touched edges {len({e.element_id for e in edges})}"]
    if condition in (ip.B, ip.B2) and new_labels:
        merged = [ic.join_ls(v) for v in new_labels.values()
                  if ic.join_ls(v) in base.node_label_cnt]
        parts.append("resulting label set already existed"
                     if merged else "resulting label set is new")
    return "; ".join(parts)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--conditions", default=",".join(ip.CONDITIONS))
    parser.add_argument("--k", default="1,10,100")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260816)
    parser.add_argument("--group", default=None,
                        help="':'-joined label set every condition perturbs "
                             "(default: dataset-specific, else the largest "
                             "multi-label group). Must be multi-label so that "
                             "B can remove a label")
    parser.add_argument("--remove-label", default=None,
                        help="label removed in condition B "
                             "(default: alphabetically first of the group)")
    parser.add_argument("--reference", action="store_true",
                        help="score one condition at a time with "
                             "eval_c2_sparse_from_types instead of the batch "
                             "sweep (slow; for regression checks)")
    parser.add_argument("--dry-run", action="store_true",
                        help="build the conditions and report their Abs(G') "
                             "sizes without scoring anything")
    parser.add_argument("--out", default=None)
    parser.add_argument("--no-cache", action="store_true",
                        help="re-run the Abs(G) aggregation queries")
    args = parser.parse_args(argv)

    if os.environ.get("PYTHONHASHSEED") != "0":
        print("warning: PYTHONHASHSEED is not 0; Cov_E can differ in its "
              "last bit between processes",
              file=sys.stderr)

    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    unknown = set(conditions) - set(ip.CONDITIONS)
    if unknown:
        parser.error(f"unknown conditions: {sorted(unknown)}")
    ks = [int(x) for x in args.k.split(",") if x.strip()]

    counters = ic.fetch_counters(args.instance, cache=not args.no_cache)
    group = (args.group
             or DEFAULT_GROUP.get(args.instance)
             or pick_multi_label_group(counters, max(ks)))

    cond_objs = build_conditions(
        args.instance, counters, conditions, ks, args.trials, args.seed,
        group, args.remove_label, ic.URI, ic.AUTH)

    if args.dry_run:
        print(f"\n{'condition':<32} {'k':>4} {'trial':>5} "
              f"{'|V(S_G)|':>9} {'|E(S_G)|':>9}  notes")
        for cond in cond_objs:
            m = cond.meta
            print(f"{m['condition']:<32} {m['k']:>4} {m['trial']:>5} "
                  f"{len(cond.node_types):>9} {len(cond.edge_types):>9}  "
                  f"{m['notes']}")
        return 0

    star_nodes, star_edges = utils.get_all_node_and_edge_types_from_schema(
        args.schema, ic.URI, ic.AUTH)
    print(f"[setup] schema {args.schema}: {len(star_nodes)} node types / "
          f"{len(star_edges)} edge types")

    timings: Dict[str, float] = {}
    t0 = time.time()
    if args.reference:
        scores = be.eval_conditions_reference(
            cond_objs, star_nodes, star_edges, **WEIGHTS)
    else:
        scores = be.eval_conditions(
            cond_objs, star_nodes, star_edges, timings=timings, **WEIGHTS)
    wall = time.time() - t0
    print(f"[done] {len(cond_objs)} conditions in {wall:.1f}s")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = args.out or os.path.join(
        RESULTS_DIR,
        f"instance_irregularity_{datetime.now():%Y-%m-%d_%H-%M-%S}.csv")
    write_csv(out_path, args, cond_objs, scores, wall, timings)
    print(f"[done] wrote {out_path}")
    return 0


def write_csv(path: str, args, conditions: Sequence[be.Condition],
              scores: Sequence[be.Scores], wall: float,
              timings: Dict[str, float]) -> None:
    exists = os.path.exists(path)
    with open(path, "a", newline="") as f:
        writer = csv.writer(f)
        if not exists:
            writer.writerow(CSV_HEADER)
        stamp = datetime.now().isoformat(timespec="seconds")
        for cond, sc in zip(conditions, scores):
            m = cond.meta
            c2 = (sc.node_c2 + sc.edge_c2) / 2
            writer.writerow([
                stamp, args.instance, args.schema,
                "reference" if args.reference else "batch",
                m.get("condition", ""), m.get("k", ""), m.get("trial", ""),
                m.get("seed", ""), m.get("target_label_set", ""),
                m.get("detail", ""),
                len({frozenset(n.labels) for n in cond.node_types}),
                len(cond.node_types), len(cond.edge_types),
                f"{sc.node_coverage:.10f}", f"{sc.edge_coverage:.10f}",
                f"{sc.node_concision:.10f}", f"{sc.edge_concision:.10f}",
                f"{sc.node_c2:.10f}", f"{sc.edge_c2:.10f}", f"{c2:.10f}",
                f"{wall:.1f}",
                f"{timings.get('cov_pass', float('nan')):.1f}",
                f"{timings.get('con_v', float('nan')):.1f}",
                f"{timings.get('con_e', float('nan')):.1f}",
                m.get("notes", ""),
            ])


if __name__ == "__main__":
    raise SystemExit(main())
