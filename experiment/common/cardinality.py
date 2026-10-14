"""Edge cardinality constraints (paper Def. 3 / 5, Eqs. 10-11, 31-33).

A cardinality bound is a pair ``(c_min, c_max)`` with ``c_min`` a
non-negative int and ``c_max`` a non-negative int or ``STAR`` (unbounded).
An edge type carries two bounds, ``card_out`` / ``card_in``; ``None`` means
the schema gave no bound, which is read as ``UNBOUNDED`` (``0..*``) once
cardinality evaluation is enabled for the schema.

In a schema DB the bounds are stored as the string edge properties
``cardinality_out`` / ``cardinality_in`` written ``n..m`` (paper Fig. 1).
"""

import re
from typing import Dict, Iterable, Optional, Tuple, Union

STAR = "*"
CardValue = Union[int, str]
Bound = Tuple[int, CardValue]

UNBOUNDED: Bound = (0, STAR)

# The four values used for the ground-truth schemas and for perturbation.
FOUR_BOUNDS: Tuple[Bound, ...] = ((0, 1), (0, STAR), (1, 1), (1, STAR))

CARD_OUT_KEY = "cardinality_out"
CARD_IN_KEY = "cardinality_in"
CARD_KEYS = (CARD_OUT_KEY, CARD_IN_KEY)

_BOUND_RE = re.compile(r"^(0|[1-9][0-9]*)\.\.(0|[1-9][0-9]*|\*)$")


def parse_bound(text) -> Bound:
    """Parse ``"n..m"`` into a bound; reject anything outside Def. 3."""
    if not isinstance(text, str):
        raise ValueError(f"cardinality bound must be a string 'n..m', got {text!r}")
    m = _BOUND_RE.match(text)
    if m is None:
        raise ValueError(f"malformed cardinality bound {text!r} (expected 'n..m')")
    lo = int(m.group(1))
    hi: CardValue = STAR if m.group(2) == STAR else int(m.group(2))
    if hi != STAR and lo > hi:
        raise ValueError(f"cardinality bound {text!r} has min > max")
    return (lo, hi)


def format_bound(bound: Bound) -> str:
    return f"{bound[0]}..{bound[1]}"


def bd(x: CardValue, y: CardValue) -> float:
    """Bound similarity of two cardinality values (Eq. 33)."""
    if x == STAR and y == STAR:
        return 1.0
    if x == STAR or y == STAR:
        return 0.0
    return (min(x, y) + 1) / (max(x, y) + 1)


def d_int(c: Bound, c2: Bound) -> float:
    """Similarity of two cardinality bounds (Eq. 32)."""
    return (bd(c[0], c2[0]) + bd(c[1], c2[1])) / 2


def d_card(out1: Optional[Bound], in1: Optional[Bound],
           out2: Optional[Bound], in2: Optional[Bound]) -> float:
    """Cardinality similarity (Eq. 31); a missing bound counts as 0..*."""
    return (d_int(out1 or UNBOUNDED, out2 or UNBOUNDED)
            + d_int(in1 or UNBOUNDED, in2 or UNBOUNDED)) / 2


def schema_has_cardinality(edge_types: Iterable) -> bool:
    """True iff any non-EXTENDS edge type carries a bound (schema-level switch)."""
    return any(e.label != "EXTENDS"
               and (e.card_out is not None or e.card_in is not None)
               for e in edge_types)


def round_to_four(observed: Tuple[int, int]) -> Bound:
    """One of FOUR_BOUNDS from an observed [min, max].

    Used for both sides: the ground-truth schemas and the instance-derived
    schema Abs(G) (min 0 / >= 1 -> 0 / 1, max <= 1 / >= 2 -> 1 / *).
    """
    lo, hi = observed
    return (0 if lo == 0 else 1, 1 if hi <= 1 else STAR)


def aggregate_degree_bounds(
        rows: Iterable[Tuple[Tuple[str, ...], str, Tuple[str, ...], int, int, int]],
        node_counts: Dict[Tuple[str, ...], int],
        anchor: str,
) -> Dict[Tuple[Tuple[str, ...], str, Tuple[str, ...]], Bound]:
    """Eqs. (10)(11): per edge group, [min, max] incidence over the anchor group.

    ``rows`` holds ``(src_labels, rel_type, dst_labels, d_min, d_max, n)``
    where label tuples are sorted, and ``d_min`` / ``d_max`` / ``n`` are taken
    over the anchor-side nodes that have at least one edge of the group
    (``anchor`` is ``"src"`` for out-degrees, ``"dst"`` for in-degrees).
    Rows sharing a key (labels returned in a different order) are merged.
    Nodes of the anchor group without such an edge have degree 0, so the
    minimum drops to 0 when ``n`` is smaller than the group size.
    """
    acc: Dict[Tuple[Tuple[str, ...], str, Tuple[str, ...]], list] = {}
    for src, rel, dst, d_min, d_max, n in rows:
        key = (src, rel, dst)
        if key in acc:
            a = acc[key]
            a[0] = min(a[0], d_min)
            a[1] = max(a[1], d_max)
            a[2] += n
        else:
            acc[key] = [d_min, d_max, n]
    out: Dict[Tuple[Tuple[str, ...], str, Tuple[str, ...]], Bound] = {}
    for key, (d_min, d_max, n) in acc.items():
        group = key[0] if anchor == "src" else key[2]
        if n < node_counts[group]:
            d_min = 0
        out[key] = (d_min, d_max)
    return out
