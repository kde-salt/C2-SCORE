import csv
from ..common import utils
import traceback
import os
from datetime import datetime


DATASETS = [
    'findkg',
    'ldbc',
    'mb6',
    'network-management',
    'northwind',
    'spotify',
    'steam',
    'tpc-h',
    'twitter',
    'wordnet',
]
METHODS = ["lei", "schemi", "gmmschema", "pg-hive"]


def experiment(alpha, beta, gamma, datasets=None, methods=None,
               results_dir="./experiment/diagnostic_usefulness_test/results"):
    instance_db_names = list(datasets) if datasets else list(DATASETS)
    methods = list(methods) if methods else list(METHODS)
    from ..common.config import NEO4J_URI as URI, NEO4J_AUTH as AUTH
    os.makedirs(results_dir, exist_ok=True)
    csv_filename = f"{results_dir}/results_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    header = [
        "timestamp", "instance_db_name", "method", "alpha", "beta", "gamma",
        "node_coverage", "edge_coverage", "node_concision", "edge_concision",
        "node_c2", "edge_c2"
    ]

    log_filename = f"{results_dir}/error.log"

    with open(csv_filename, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(header)

        for instance_db_name in instance_db_names:
            for method in methods:
                schema_db_name = f"{instance_db_name}-{method}"
                # Keep alpha, mandatory, and optional weights normalized to 1
                mandatory = (1 - alpha) / 2
                optional = (1 - alpha) / 2
                try:
                    print(
                        f"Evaluating {instance_db_name} with method {method}")
                    node_coverage, edge_coverage, node_concision, edge_concision, node_c2, edge_c2, *_ = \
                        utils.eval_c2(URI, AUTH, instance_db_name, schema_db_name, label_w=alpha,
                                      mandatory_w=mandatory, optional_w=optional,
                                      endpoint_w=beta, gamma=gamma)
                except Exception:
                    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    err_msg = traceback.format_exc().replace('\n', ' | ')
                    utils.log_error(log_filename, timestamp, instance_db_name, method,
                                    round(alpha, 2), round(beta, 2), round(gamma, 2), err_msg)
                    continue

                if node_coverage is None:
                    continue

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([
                    timestamp, instance_db_name, method, round(
                        alpha, 2), round(beta, 2), round(gamma, 2),
                    node_coverage, edge_coverage, node_concision, edge_concision,
                    node_c2, edge_c2
                ])
                csvfile.flush()
                os.fsync(csvfile.fileno())


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="EQ2 diagnostic usefulness experiment "
                    "(defaults reproduce the paper setting)")
    parser.add_argument("--datasets", nargs="*", choices=DATASETS, default=None,
                        help="instance DBs to evaluate (default: all ten)")
    parser.add_argument("--methods", nargs="*", choices=METHODS, default=None,
                        help="extraction methods (default: all four)")
    parser.add_argument("--alpha", type=float, default=0.5,
                        help="label weight (property weights are (1-alpha)/2 each)")
    parser.add_argument("--beta", type=float, default=0.5,
                        help="endpoint weight")
    parser.add_argument("--gamma", type=float, default=0.15,
                        help="redundancy threshold factor")
    parser.add_argument("--results-dir",
                        default="./experiment/diagnostic_usefulness_test/results")
    args = parser.parse_args()

    experiment(args.alpha, args.beta, args.gamma,
               datasets=args.datasets, methods=args.methods,
               results_dir=args.results_dir)
