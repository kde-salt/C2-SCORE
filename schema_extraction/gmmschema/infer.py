""" Script to create a Neo4j graph with """

# Imports
import csv

# Neo4j imports
from neo4j import GraphDatabase


def create_neo4j_graph(
    driver2,
    uri,
    user,
    passwd,
    db_name,
    mid_table_path
):
    """ Create a Neo4j graph 

    Parameters
    ----------
    driver2 : GraphDatabase.driver object
        Driver used to access the PG stored in a Neo4j database.
    edges : Boolean.
        If edges is set at True by default.
        When edges is at True, add all edges to the Neo4j graph.
        When edges is at False, only add edges SUBTYPE_OF.

    Returns
    -------
    A Neo4j graph representation of the inferred schema
    """

    with driver2.session() as session:
        query = "MATCH (n)-[r]->(m) \
            RETURN DISTINCT labels(n),keys(n),type(r),labels(m),keys(m)"
        edge_types = session.run(query)

        all_labels_n = []
        all_keys_n = []
        all_type_r = []
        all_keys_m = []
        all_labels_m = []

        for edge_type in edge_types:
            all_labels_n.append(
                ":".join(f"`{label}`" for label in sorted(
                    edge_type["labels(n)"]))
            )
            all_keys_n.append(":".join(sorted(edge_type["keys(n)"])))
            all_type_r.append(edge_type["type(r)"])
            all_labels_m.append(
                ":".join(f"`{label}`" for label in sorted(
                    edge_type["labels(m)"]))
            )
            all_keys_m.append(":".join(sorted(edge_type["keys(m)"])))

    driver = GraphDatabase.driver(uri, database=f"{db_name}-gmmschema",
                                  auth=(user, passwd), encrypted=False)

    with driver.session() as session:
        query = "MATCH (n) DETACH DELETE n"
        session.run(query)

        with open(mid_table_path) as csv_file:
            lines = csv.reader(csv_file, delimiter=',')
            # skip header
            next(lines)

            id_elementId_dict = {}
            for row in lines:
                if row[5] == "yes" and row[2] == "":
                    continue
                
                node_id = row[0]
                node_labels = row[1]
                node_labels = ":".join(
                    f"`{label}`" for label in sorted(row[1].split(":"))
                ).replace("?", "")
                joined_props = ":".join(sorted(row[2].split(":")))
                props = row[2].split(":")
                combined_props = ""
                for prop in props:
                    if prop == "":
                        continue
                    if "?" in prop:
                        prop = prop.replace("?", "")
                        combined_props += f"{prop}:\"type?\","
                    else:
                        combined_props += f"{prop}:\"type\","
                if combined_props == "":
                    combined_props = "{" + \
                        "labels:\"" + node_labels + "\"," + \
                        "props:\"" + joined_props + "\"}"
                else:
                    combined_props = "{" + \
                        "labels:\"" + node_labels + "\"," + \
                        "props:\"" + joined_props + "\"," + \
                        combined_props[:-1] + "}"
                query = f"MERGE (n:{node_labels} {combined_props}) RETURN elementId(n)"
                result = session.run(query)
                element_id = result.single()[0]
                id_elementId_dict[node_id] = element_id

                # for base type
                if row[5] == "yes":
                    continue

                parent_id = row[3]
                parent_element_id = id_elementId_dict.get(parent_id)
                if parent_element_id is None:
                    continue

                # neo4j node creation query
                query2 = f"""
                MATCH (parent),(child) \
                WHERE elementId(parent) = \"{str(parent_element_id)}\" \
                        AND elementId(child) = \"{str(element_id)}\"
                CREATE (child)-[:EXTENDS]->(parent)
                """
                session.run(query2)

    with driver.session() as session:
        for i in range(len(all_labels_n)):
            labels_n = all_labels_n[i].replace("?", "")
            keys_n = all_keys_n[i]
            type_r = all_type_r[i]
            labels_m = all_labels_m[i]
            keys_m = all_keys_m[i]

            query = "MATCH(n),(m) WHERE n.labels='"+labels_n+"' AND n.props='"+keys_n + \
                "' AND m.labels='"+labels_m+"' AND m.props='" + \
                    keys_m+"' MERGE (n)-[r:"+type_r+"]->(m)"
            session.run(query)

    # remove the helper properties used for edge creation
    with driver.session() as session:
        query = "MATCH (n) REMOVE n.props"
        session.run(query)
        query = "MATCH (n) REMOVE n.labels"
        session.run(query)
