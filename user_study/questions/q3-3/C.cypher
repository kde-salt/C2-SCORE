CREATE (person:Person{name: "mandatory", orcid: "optional?"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory", doi: "optional?"})
CREATE (venue:Venue:Conference{name: "mandatory", year: "mandatory"}) // Expanded inheritance
CREATE (venue2:Venue:Journal{name: "mandatory", volume: "mandatory", issue: "mandatory"}) // Expanded inheritance
CREATE (ins:Institution{name: "mandatory"})
CREATE (univ:University)
CREATE (industry:Industry)
CREATE (researchIns:ResearchInstitute)

CREATE (person)-[:AUTHORED{authorIndex: "mandatory"}]->(paper)
CREATE (paper)-[:CITES]->(paper)
CREATE (paper)-[:PUBLISHED_IN]->(venue)
CREATE (paper)-[:PUBLISHED_IN]->(venue2)
CREATE (person)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(ins)
CREATE (univ)-[:EXTENDS]->(ins)
CREATE (industry)-[:EXTENDS]->(ins)
CREATE (researchIns)-[:EXTENDS]->(ins)
