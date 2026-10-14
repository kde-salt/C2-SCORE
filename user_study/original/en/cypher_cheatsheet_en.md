# Cypher Query Cheat Sheet

## All Nodes and Edges
```cypher
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
```

## All Nodes
```cypher
MATCH (n) RETURN n;
```

## All Edges
```cypher
MATCH p=()-[]->() RETURN p;
```

## Nodes with Person Label
```cypher
MATCH (n:Person) RETURN n;
```

## Nodes with Only Person Label
```cypher
MATCH (n:Person) WHERE size(labels(n)) = 1 RETURN n;
```

## Edges with FOLLOWS Label
```cypher
MATCH ()-[r:FOLLOWS]->() RETURN r;
```

## Person Mandatory and Optional Properties
```cypher
MATCH (n:Person)
WITH count(n) AS total
MATCH (n:Person)
UNWIND keys(n) AS prop
WITH prop, total, count(*) AS freq
RETURN prop, (freq = total) AS is_mandatory
ORDER BY is_mandatory DESC, prop;
```

## FOLLOWS Mandatory and Optional Properties
```cypher
MATCH ()-[r:FOLLOWS]->()
WITH count(r) AS total
MATCH ()-[r:FOLLOWS]->()
UNWIND keys(r) AS prop
WITH prop, total, count(*) AS freq
RETURN prop, (freq = total) AS is_mandatory
ORDER BY is_mandatory DESC, prop;
```

## Nodes with name Property
```cypher
MATCH (n) WHERE n.name IS NOT NULL RETURN n;
```

## Nodes with Specific name
```cypher
MATCH (n) WHERE n.name = "Alice" RETURN n;
```

## Edges with timestamp Property
```cypher
MATCH ()-[r]->() WHERE r.timestamp IS NOT NULL RETURN r;
```

## Edges with Specific timestamp
```cypher
MATCH ()-[r]->() WHERE r.timestamp = "2025-10-14 20:35" RETURN r;
```

## Edges from Person to Post
```cypher
MATCH (src:Person)-[r]->(dst:Post) RETURN src, r, dst;
```

## Endpoints of FOLLOWS Edges
```cypher
MATCH (src)-[:FOLLOWS]->(dst) RETURN src, dst;
```

## Distinct Source Labels of FOLLOWS
```cypher
MATCH (src)-[:FOLLOWS]->() RETURN DISTINCT labels(src) AS src_labels;
```

## Complex Graph Pattern (Alice Posts)
```cypher
// Retrieve posts created by people followed by Alice
MATCH (a:Person)-[:FOLLOWS]->(:Person)-[:CREATES]->(p:Post)
WHERE a.name = "Alice"
RETURN p;
```
