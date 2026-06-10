import csv
from ..common import utils
import traceback
import os
import time
from datetime import datetime


def experiment(alpha, beta, gamma, N=10):
    print(
        f"Starting experiment with alpha={alpha}, beta={beta}, gamma={gamma}, N={N}")
    dataset_names = [
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
    URI = "bolt://localhost:7687"
    AUTH = ("neo4j", "password")
    results_dir = "./experiment/scalability_test/results"
    os.makedirs(results_dir, exist_ok=True)

    csv_filename = f"{results_dir}/results_{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}.csv"

    header = ["timestamp", "dataset", "run",
              "elapsed_time", "abs_time", "flatten_time", "score_time",
              "other_time"]

    log_filename = "error.log"

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
                     other_time) = utils.eval_c2(
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
                        elapsed_time, 2),
                    round(abs_time, 2) if abs_time is not None else "",
                    round(flatten_time, 2) if flatten_time is not None else "",
                    round(score_time, 2) if score_time is not None else "",
                    round(other_time, 2) if other_time is not None else "",
                ])
                csvfile.flush()
                os.fsync(csvfile.fileno())


if __name__ == "__main__":
    ALPHA = 0.5
    BETA = 0.5
    GAMMA = 0.15
    experiment(ALPHA, BETA, GAMMA)
