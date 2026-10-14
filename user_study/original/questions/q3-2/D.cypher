CREATE (person:Person{name: "mandatory", orcid: "optional?"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory", doi: "optional?"})
CREATE (ins:Institution{name: "mandatory", type: "mandatory"})
CREATE (venue:Venue{name: "mandatory", type: "mandatory", year: "optional?", volume: "optional?", issue: "optional?"})

CREATE (person)-[:AUTHORED{authorIndex: "mandatory"}]->(paper)
CREATE (venue)-[:PUBLISHED_IN]->(paper) // Reversed edge direction: PUBLISHED_IN is reversed
CREATE (paper)-[:CITES]->(paper)
CREATE (person)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(ins)
