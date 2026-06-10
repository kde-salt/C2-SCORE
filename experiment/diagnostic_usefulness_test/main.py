import csv
from ..common import utils
import traceback
import os
from datetime import datetime


def experiment(alpha, beta, gamma):
    instance_db_names = [
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
    methods = ["lei", "schemi", "gmmschema", "pg-hive"]
    URI = "bolt://localhost:7687"
    AUTH = ("neo4j", "password")
    results_dir = "./experiment/diagnostic_usefulness_test/results"
    os.makedirs(results_dir, exist_ok=True)
    csv_filename = f"{results_dir}/results_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"

    header = [
        "timestamp", "instance_db_name", "method", "alpha", "beta", "gamma",
        "node_coverage", "edge_coverage", "node_concision", "edge_concision",
        "node_c2", "edge_c2"
    ]

    log_filename = "./experiment/diagnostic_usefulness_test/results/error.log"

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
    ALPHA = 0.5
    BETA = 0.5
    GAMMA = 0.15
    experiment(ALPHA, BETA, GAMMA)
