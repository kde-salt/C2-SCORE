""" Main script to infer a PG schema of any database using a clustering method """

# Imports
from termcolor import colored
import time

# Neo4j imports
from neo4j import GraphDatabase

# File imports
from .preprocessing_step import preprocessing
from .sampling import sampling
from .GMM_clustering import iter_gmm
from .storing import storing
from .infer import create_neo4j_graph
from pprint import pprint


def main(uri, user, passwd, DBname, mid_table_path, sampling_rate):
    print(colored("Schema inference using Gaussian Mixture Model clustering on PG\n", "red"))
    driver = GraphDatabase.driver(uri, auth=(
        user, passwd), database=DBname, encrypted=False)

    print(colored("Starting to query on ", "red"),
          colored(DBname, "red"), colored(":", "red"))
    t1 = time.perf_counter()
    amount_dict, list_of_distinct_nodes, distinct_labels, labs_sets = preprocessing(
        driver)
    t1f = time.perf_counter()

    step1 = t1f - t1  # time to complete step 1
    print(colored("Queries are done.", "green"))
    print("Step 1: Preprocessing was completed in ", step1, "s")

    print("---------------")

    print(colored("Data sampling : ", "blue"))
    ts = time.perf_counter()
    amount_dict, list_of_distinct_nodes, validate, test = sampling(
        amount_dict, list_of_distinct_nodes, sampling_rate)
    tsf = time.perf_counter()
    steps = tsf - ts  # time to complete the sampling step
    print(colored("Separating done.", "green"))
    print("The sampling step was processed in ", steps, "s")

    print("---------------")

    print(colored("Starting to cluster data using GMM :", "red"))
    t2 = time.perf_counter()
    all_clusters, hierarchy_tree = iter_gmm(
        amount_dict, list_of_distinct_nodes, distinct_labels, labs_sets)
    t2f = time.perf_counter()

    pprint(hierarchy_tree)

    step2 = t2f - t2  # time to complete step 2
    print(colored("Clustering done.", "green"))
    print("Step 2: Clustering was completed in ", step2, "s")

    print("---------------")

    print(colored("Writing file and identifying subtypes :", "red"))
    t3 = time.perf_counter()
    storing(distinct_labels, labs_sets, hierarchy_tree, mid_table_path)
    t3f = time.perf_counter()

    step3 = t3f - t3  # time to complete step 3
    print(colored("Writing done.", "green"))
    print("Step 3: Identifying subtypes and storing to file was completed in", step3, "s")

    print("---------------")
    print(colored("Creating neo4j graph :", "red"))

    t4 = time.perf_counter()
    create_neo4j_graph(driver, uri, user, passwd, DBname, mid_table_path)
    t4f = time.perf_counter()

    step4 = t4f - t4
    print(colored("Graph created.", "green"))
    print("Step 4: Creating neo4j graph was completed in ", step4, "s")
