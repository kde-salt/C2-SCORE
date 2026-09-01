""" Script used to make the sampling of data """

# Imports
import random
from collections import Counter
from termcolor import colored

from . import RANDOM_SEED
from schema_extraction.progress import Progress


def sampling(amount_dict, list_of_distinct_nodes, training_percentage):
    """ Separates the data in three sets

    Parameters
    ----------
    amount_dict : Python dict
    A dictionary with node strings as keys and the number of occurrences of the node as a value
    Its format is : {'Label1 Label2 Label3 prop1 prop2 prop3 ...': int, ...}
    list_of_distinct_nodes : Python list
    A list of node strings
    Its format is : ['Label1 Label2 prop1', 'Label1 Label3 prop2', 'prop4 prop5', ...]
    training_percentage : Int
            An integer to represent the percentage of data used for the training set
            It should be 80, 70 or 50

    Returns
    -------
    amount_dict : Python dict (training set)
    A dictionary with node strings as keys and the number of occurrences of the node as a value
    Its format is : {'Label1 Label2 Label3 prop1 prop2 prop3 ...': int, ...}
    list_of_distinct_nodes : Python list (training set)
    A list of node strings
    Its format is : ['Label1 Label2 prop1', 'Label1 Label3 prop2', 'prop4 prop5', ...]
    validate : Python list (validation set)
    A list of node strings
    Its format is : ['Label1 Label2 prop1', 'Label1 Label3 prop2', 'prop4 prop5', ...]
    test : Python list (test set)
    A list of node strings
    Its format is : ['Label1 Label2 prop1', 'Label1 Label3 prop2', 'prop4 prop5', ...]

    """

    # get the number of occurrences of each node in a variable.
    # Sort the node list first: Neo4j does not guarantee row order, so without
    # this the sampled split (and thus clustering) varies across runs even with
    # a fixed RANDOM_SEED.
    data = []
    for node in sorted(list_of_distinct_nodes):
        amount = amount_dict[node]
        for i in range(amount):
            data.append(node)

    # Use a seeded local RNG so the split is deterministic across runs
    rng = random.Random(RANDOM_SEED)
    data = rng.sample(data, len(data))

    if training_percentage == 80:
        train = data[:int(len(data)*0.8)]
        validate = data[int(len(data)*0.8):int(len(data)*0.9)]
        test = data[int(len(data)*0.9):]
    elif training_percentage == 70:
        train = data[:int(len(data)*0.7)]
        validate = data[int(len(data)*0.7):int(len(data)*0.85)]
        test = data[int(len(data)*0.85):]
    elif training_percentage == 50:
        train = data[:int(len(data)*0.5)]
        validate = data[int(len(data)*0.5):int(len(data)*0.75)]
        test = data[int(len(data)*0.75):]
    elif training_percentage == 100:
        train = data
        validate = []
        test = []
    else:
        print(colored("Unvalid training percentage, should be 80, 70 or 50.", "red"))

    # training set with unique nodes (sorted for deterministic ordering)
    list_of_distinct_nodes = sorted(set(train))

    # number of occurrences of the nodes in the training set
    # (Counter gives the same counts as train.count(node) in one pass)
    train_counts = Counter(train)
    progress = Progress("gmm:sampling-count", total=len(list_of_distinct_nodes))
    for node in list_of_distinct_nodes:
        amount_dict[node] = train_counts[node]
        progress.tick()
    progress.done()

    return amount_dict, list_of_distinct_nodes, validate, test
