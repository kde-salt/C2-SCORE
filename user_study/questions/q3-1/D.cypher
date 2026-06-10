CREATE (person:Person{name: "mandatory"})
CREATE (paper:Paper{title: "mandatory"}) // Remove year
CREATE (ins:Institution{name: "mandatory", type: "mandatory"})

CREATE (person)-[:AUTHORED]->(paper)
CREATE (paper)-[:CITES]->(paper)
CREATE (person)-[:AFFILIATED_WITH]->(ins)
