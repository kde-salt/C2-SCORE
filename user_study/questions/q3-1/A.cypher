CREATE (person:Person{name: "mandatory"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory"})
CREATE (paper2:Paper{title: "mandatory", year: "mandatory"}) // Regression 1: duplicated Paper node type (for self-loop expansion)
CREATE (ins:Institution{name: "mandatory", type: "mandatory"})

CREATE (paper)-[:AUTHORED]->(person) // Regression 2: reversed edge direction (should be person->paper)

// Regression 3: expanded self-loop edge (paper CITES paper expanded into paper->paper2, paper2->paper)
CREATE (paper)-[:CITES]->(paper2)
CREATE (paper2)-[:CITES]->(paper)

CREATE (person)-[:AFFILIATED_WITH]->(ins)
