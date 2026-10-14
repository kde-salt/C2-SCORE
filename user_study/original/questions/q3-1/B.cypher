CREATE (person:Person{name: "mandatory"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory"})
CREATE (ins:Institution{name: "mandatory", type: "mandatory"}) // type=(University | Industry | Research Institute)

CREATE (person)-[:AUTHORED]->(paper)
CREATE (paper)-[:CITES]->(paper)
CREATE (person)-[:AFFILIATED_WITH]->(ins)
