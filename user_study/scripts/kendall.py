import re
from typing import Dict, List, Optional, Tuple

import pandas as pd
import statistics as stats
from scipy.stats import chi2, kendalltau

# Column names follow the pattern "Q<group>-<num>-<item>", e.g. "Q1-1-A".
# Each cell holds the rank (1-4) assigned to that item, so a question is a
# mapping {item -> rank} rather than an ordered list of items.
COL_PATTERN = re.compile(r"^(Q\d+-\d+)-([A-Z])$")


def parse_questions(columns: List[str]) -> List[Tuple[str, List[str]]]:
    """
    Group rank columns by question, preserving column order.
    Returns a list of (question_label, [item_columns...]).
    """
    questions: Dict[str, List[str]] = {}
    for col in columns:
        m = COL_PATTERN.match(col)
        if not m:
            continue
        qlabel = m.group(1)
        questions.setdefault(qlabel, []).append(col)
    return list(questions.items())


def extract_ranks(row: pd.Series, item_cols: List[str]) -> Optional[List[float]]:
    """
    Read the rank values for one question from a row, in fixed column order.
    Return None if any item rank is missing (blank cell), so the question is
    skipped for that comparison.
    """
    ranks: List[float] = []
    for col in item_cols:
        val = row[col]
        if pd.isna(val):
            return None
        ranks.append(float(val))
    return ranks


def kendall_tau(rank1: List[float], rank2: List[float]) -> Optional[float]:
    """
    Kendall's tau-b between two rank vectors aligned by item.
    Uses scipy so tied ranks are handled correctly. Returns None when the
    coefficient is undefined (e.g. all ranks tied).
    """
    if len(rank1) != len(rank2) or len(rank1) < 2:
        return None
    tau, _ = kendalltau(rank1, rank2)
    if tau != tau:  # NaN -> undefined
        return None
    return tau


def mean_tau_vs_golden(
    df: pd.DataFrame,
    golden_row: pd.Series,
    questions: List[Tuple[str, List[str]]],
    name: str,
) -> Optional[float]:
    """Mean Kendall's tau between GOLDEN and the row identified by `name`."""
    matches = df[df["name"] == name]
    if matches.empty:
        return None
    row = matches.iloc[0]

    taus: List[float] = []
    for _, item_cols in questions:
        golden_rank = extract_ranks(golden_row, item_cols)
        row_rank = extract_ranks(row, item_cols)
        if golden_rank is None or row_rank is None:
            continue
        tau = kendall_tau(golden_rank, row_rank)
        if tau is not None:
            taus.append(tau)

    if not taus:
        return None
    return stats.mean(taus)


def kendalls_w(rankings: List[List[float]]) -> Optional[float]:
    """
    Kendall's W (coefficient of concordance) with tie correction.
    `rankings` is a list of rank vectors (one per rater), all aligned by item.
    Returns None when fewer than two rankings or W is undefined.
    """
    m = len(rankings)  # raters
    if m < 2:
        return None

    n = len(rankings[0])  # items
    if n < 2 or any(len(r) != n for r in rankings):
        return None

    # Rank sum per item across raters.
    rank_sums = [sum(r[i] for r in rankings) for i in range(n)]
    r_bar = m * (n + 1) / 2
    s = sum((rs - r_bar) ** 2 for rs in rank_sums)

    # Tie-correction term: for each rater, sum over tie groups of (t^3 - t).
    tie_term = 0.0
    for r in rankings:
        counts: Dict[float, int] = {}
        for v in r:
            counts[v] = counts.get(v, 0) + 1
        tie_term += sum(t ** 3 - t for t in counts.values())

    denominator = (m ** 2) * (n ** 3 - n) - m * tie_term
    if denominator == 0:
        return None

    return 12 * s / denominator


def kendalls_w_chi2_pvalue(
    W: Optional[float], n_raters: int, n_items: int
):
    """
    Chi-square significance test for Kendall's W.
    chi2 = raters * (items - 1) * W, df = items - 1.
    Returns (chi2, df, p) or (None, None, None) if W is None.
    """
    if W is None:
        return None, None, None

    chi2_stat = n_raters * (n_items - 1) * W
    df = n_items - 1
    p = chi2.sf(chi2_stat, df)
    return chi2_stat, df, p


def main(path):
    df = pd.read_csv(path)

    golden_matches = df[df["name"] == "GOLDEN"]
    if golden_matches.empty:
        raise ValueError("No GOLDEN row found.")
    golden_row = golden_matches.iloc[0]

    questions = parse_questions([c for c in df.columns if c != "name"])
    if not questions:
        raise ValueError(
            "No question columns matched the 'Q<g>-<n>-<item>' pattern.")

    # --- Kendall's tau: GOLDEN vs PROPOSED ---
    print("Kendall's tau vs GOLDEN (mean across questions):")
    value = mean_tau_vs_golden(df, golden_row, questions, "PROPOSED")
    if value is None:
        print("  GOLDEN vs PROPOSED: N/A")
    else:
        print(f"  GOLDEN vs PROPOSED: {value:.4f}")

    # --- Participants (exclude GOLDEN / PROPOSED) ---
    special = {"GOLDEN", "PROPOSED"}

    participant_taus = []
    for _, row in df.iterrows():
        name = row["name"]
        if name in special:
            continue
        value = mean_tau_vs_golden(df, golden_row, questions, name)
        if value is not None:
            participant_taus.append(value)

    if participant_taus:
        print("\nAnnotators' mean Kendall's tau vs GOLDEN:",
              f"{stats.mean(participant_taus):.4f}",
              f"(n={len(participant_taus)})")
    else:
        print("\nAnnotators' mean Kendall's tau vs GOLDEN: N/A")

    # --- Kendall's W per question (participants only) ---
    n_items = len(questions[0][1])
    rows = []
    valid_ws = []

    for qlabel, item_cols in questions:
        participant_rankings = []
        for _, row in df.iterrows():
            if row["name"] in special:
                continue
            rank = extract_ranks(row, item_cols)
            if rank is not None:
                participant_rankings.append(rank)

        w_value = kendalls_w(participant_rankings)
        count = len(participant_rankings)
        chi2_stat, df_chi2, p_val = kendalls_w_chi2_pvalue(
            w_value, count, n_items
        )
        rows.append(
            {
                "question": qlabel,
                "W": w_value,
                "n_raters": count,
                "chi2": chi2_stat,
                "df": df_chi2,
                "p_value": p_val,
            }
        )
        if w_value is not None:
            valid_ws.append(w_value)

    print("\nKendall's W per question (participants only) with chi-square test:")

    def fmt(x):
        return "None" if x is None else f"{x:.4f}"

    def fmt_p(x):
        return "None" if x is None else f"{x:.4e}"

    formatted = pd.DataFrame(rows)
    formatted["W"] = formatted["W"].apply(fmt)
    formatted["chi2"] = formatted["chi2"].apply(fmt)
    formatted["p_value"] = formatted["p_value"].apply(fmt_p)
    print(formatted.to_string(index=False))

    if valid_ws:
        print("\nMean Kendall's W across questions:",
              f"{stats.mean(valid_ws):.4f}")
    else:
        print("\nMean Kendall's W across questions: N/A")


if __name__ == "__main__":
    main("user_study/results/ranks.csv")
