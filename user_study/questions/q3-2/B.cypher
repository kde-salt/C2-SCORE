CREATE (person:Person{name: "mandatory", orcid: "optional?"}) // Add orcid
CREATE (paper:Paper{title: "mandatory", year: "mandatory", doi: "optional?"}) // Add doi
CREATE (ins:Institution{name: "mandatory", type: "mandatory"})
CREATE (venue:Venue{name: "mandatory", type: "mandatory", year: "optional?", volume: "optional?", issue: "optional?"}) // type=(Conference | Journal)

CREATE (person)-[:AUTHORED{authorIndex: "mandatory"}]->(paper) // Add authorIndex
CREATE (paper)-[:CITES]->(paper)
CREATE (person)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(ins)
CREATE (paper)-[:PUBLISHED_IN]->(venue)
