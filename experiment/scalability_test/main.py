import csv
from ..common import utils
from ..common import utils_sparse
import traceback
import os
import time
from datetime import datetime


DATASETS = [
    ("ldbc", "ldbc-schemi"),
    ("ldbc-sf0.1", "ldbc-schemi"),
    ("ldbc-sf0.3", "ldbc-schemi"),
    ("ldbc-sf1", "ldbc-schemi"),
    ("ldbc-sf3", "ldbc-schemi"),
    ("ldbc-sf10", "ldbc-schemi"),
    ("findkg", "findkg-schemi"),
    ("mb6", "mb6-schemi"),
    ("network-management", "network-management-schemi"),
    ("northwind", "northwind-schemi"),
    ("spotify", "spotify-schemi"),
    ("steam", "steam-schemi"),
    ("tpc-h", "tpc-h-schemi"),
    ("twitter", "twitter-schemi"),
    ("wordnet", "wordnet-schemi"),
]


def experiment(alpha, beta, gamma, N=10, datasets=None,
               results_dir="./experiment/scalability_test/results"):
    print(
        f"Starting experiment with alpha={alpha}, beta={beta}, gamma={gamma}, N={N}")
    if datasets:
        selected = set(datasets)
        dataset_names = [p for p in DATASETS if p[0] in selected]
    else:
        dataset_names = list(DATASETS)
    from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH
    os.makedirs(results_dir, exist_ok=True)

    csv_filename = f"{results_dir}/results_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    header = ["timestamp", "dataset", "run",
              "elapsed_time", "abs_time", "flatten_time", "score_time",
              "other_time"]

    log_filename = f"{results_dir}/error.log"

    with open(csv_filename, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        for instance_db_name, schema_db_name in dataset_names:
            print(f"Evaluating dataset: {instance_db_name}")
            # Keep alpha + mandatory + optional weighted to 1
            mandatory = (1 - alpha) / 2
            optional = (1 - alpha) / 2
            for run_idx in range(1, N + 1):
                start_time = time.time()
                try:
                    (*_, abs_time, flatten_time, score_time,
                     other_time) = utils_sparse.eval_c2_sparse(
                        URI, AUTH, instance_db_name, schema_db_name, label_w=alpha,
                        mandatory_w=mandatory, optional_w=optional,
                        endpoint_w=beta, gamma=gamma)
                except Exception:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    err_msg = traceback.format_exc().replace('\n', ' | ')
                    utils.log_error(log_filename, timestamp, "",
                                    instance_db_name, alpha, beta, gamma, err_msg)
                    continue
                elapsed_time = time.time() - start_time
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([
                    timestamp, instance_db_name, run_idx, round(
                        elapsed_time, 4),
                    round(abs_time, 4) if abs_time is not None else "",
                    round(flatten_time, 4) if flatten_time is not None else "",
                    round(score_time, 4) if score_time is not None else "",
                    round(other_time, 4) if other_time is not None else "",
                ])
                csvfile.flush()
                os.fsync(csvfile.fileno())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="EQ4 scalability experiment "
                    "(defaults reproduce the paper setting)")
    parser.add_argument("--datasets", nargs="*",
                        choices=[name for name, _ in DATASETS], default=None,
                        help="instance DBs to measure (default: all fifteen)")
    parser.add_argument("--runs", type=int, default=10,
                        help="measurement runs per dataset (default: 10)")
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="label weight (property weights are (1-alpha)/2 each)")
    parser.add_argument("--beta", type=float, default=0.5,
                        help="endpoint weight")
    parser.add_argument("--gamma", type=float, default=0.15,
                        help="redundancy threshold factor")
    parser.add_argument("--results-dir",
                        default="./experiment/scalability_test/results")
    args = parser.parse_args()

    experiment(args.alpha, args.beta, args.gamma, N=args.runs,
               datasets=args.datasets, results_dir=args.results_dir)
