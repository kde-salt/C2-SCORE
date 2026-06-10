import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

# Column names follow the pattern "Q<group>-<num>-<item>", e.g. "Q1-1-A".
# Each cell holds the rank (1-4) assigned to that item.
COL_PATTERN = re.compile(r"^(Q\d+-\d+)-([A-Z])$")

# Borda count: rank 1 -> 3 points, rank 2 -> 2, rank 3 -> 1, rank 4 -> 0.
SCORE_PER_RANK = {1: 3, 2: 2, 3: 1, 4: 0}


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


def extract_valid_ranks(row: pd.Series, item_cols: List[str]) -> Optional[List[int]]:
    """
    Read the rank values for one question from a row, in fixed column order.
    Return None for noise rows: any missing cell, or ranks that are not a
    permutation of 1..n (so the question is skipped for that participant).
    """
    ranks: List[int] = []
    for col in item_cols:
        val = row[col]
        if pd.isna(val):
            return None
        ranks.append(int(val))
    if sorted(ranks) != list(range(1, len(item_cols) + 1)):
        return None
    return ranks


def compute_borda_for_question(
    participants: pd.DataFrame, item_cols: List[str]
) -> List[int]:
    """
    Borda count per item (aligned with item_cols) across participants,
    skipping noise rows.
    """
    scores = [0] * len(item_cols)
    for _, row in participants.iterrows():
        ranks = extract_valid_ranks(row, item_cols)
        if ranks is None:
            continue
        for i, rank in enumerate(ranks):
            scores[i] += SCORE_PER_RANK.get(rank, 0)
    return scores


def scores_to_ranks(scores: List[int]) -> List[int]:
    """
    Convert Borda scores to ranks 1..n (higher score -> better rank).
    Ties are broken by column order (A before B), matching the original
    implementation's alphabetical tie-break.
    """
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    ranks = [0] * len(scores)
    for pos, idx in enumerate(order):
        ranks[idx] = pos + 1
    return ranks


def detect_line_terminator(path) -> str:
    """Preserve the file's original line endings (the CSV is CRLF)."""
    with open(path, "rb") as f:
        return "\r\n" if b"\r\n" in f.read() else "\n"


def main(path):
    line_terminator = detect_line_terminator(path)
    df = pd.read_csv(path, dtype={"name": str})

    questions = parse_questions([c for c in df.columns if c != "name"])
    if not questions:
        raise ValueError(
            "No question columns matched the 'Q<g>-<n>-<item>' pattern.")

    # Keep blanks as <NA> (not 1.0/NaN floats) so the rewritten CSV stays
    # byte-compatible with the original integer formatting.
    rank_cols = [c for _, cols in questions for c in cols]
    df[rank_cols] = df[rank_cols].astype("Int64")

    # Participants are the numeric-named rows (001-030).
    participants = df[df["name"].str.fullmatch(r"\d+")]
    if participants.empty:
        raise ValueError("No participant rows (numeric names) found.")

    golden: Dict[str, int] = {}
    for _, item_cols in questions:
        scores = compute_borda_for_question(participants, item_cols)
        ranks = scores_to_ranks(scores)
        for col, rank in zip(item_cols, ranks):
            golden[col] = rank

    golden_index = df.index[df["name"] == "GOLDEN"]
    if golden_index.empty:
        golden_df = pd.DataFrame([{"name": "GOLDEN", **golden}],
                                 columns=df.columns).astype(df.dtypes)
        df = pd.concat([golden_df, df], ignore_index=True)
    else:
        for col, rank in golden.items():
            df.loc[golden_index[0], col] = rank

    df.to_csv(path, index=False, lineterminator=line_terminator)
    print(f"GOLDEN row written to {path} "
          f"(from {len(participants)} participants).")


if __name__ == "__main__":
    main("user_study/results/ranks.csv")
