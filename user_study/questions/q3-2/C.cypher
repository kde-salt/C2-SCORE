CREATE (person:Person{name: "mandatory", orcid: "optional?"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory", doi: "optional?"})
CREATE (ins:Institution{name: "mandatory", type: "mandatory"})
CREATE (venue:Venue{name: "mandatory", type: "mandatory", year: "optional?", volume: "optional?", issue: "optional?"})

CREATE (person)-[:AUTHORED]->(paper) // Missing edge property: removed authorIndex
CREATE (paper)-[:CITES]->(paper)
CREATE (person)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(ins)
CREATE (paper)-[:PUBLISHED_IN {impactFactor: "mandatory"}]->(venue) // Added an edge property not present in the data
