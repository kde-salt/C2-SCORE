CREATE (person:Person{name: "mandatory", orcid: "optional?"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory"}) // Missing node property: removed doi
CREATE (ins:Institution{name: "mandatory", type: "mandatory"})
CREATE (venue:Venue{name: "mandatory", year: "optional?", volume: "optional?", issue: "optional?"}) // Missing node property: removed type

CREATE (person)-[:AUTHORED{authorIndex: "mandatory"}]->(paper)
// Missing edge type: removed CITES
CREATE (ins)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(person) // Reversed edge direction: AFFILIATED_WITH is reversed
CREATE (paper)-[:PUBLISHED_IN]->(venue)
