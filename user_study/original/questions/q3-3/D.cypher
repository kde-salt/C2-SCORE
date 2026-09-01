CREATE (person:Person{name: "mandatory", orcid: "optional?"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory", doi: "optional?"})
CREATE (venue:Venue{name: "mandatory"}) // Removed type
CREATE (ins:Institution{name: "mandatory"}) // Removed type
CREATE (conference:Conference{year: "mandatory"})
CREATE (journal:Journal{volume: "mandatory", issue: "mandatory"})
CREATE (univ:University)
CREATE (industry:Industry)
CREATE (researchIns:ResearchInstitute)

CREATE (person)-[:AUTHORED{authorIndex: "mandatory"}]->(paper)
CREATE (paper)-[:CITES]->(paper)
CREATE (paper)-[:PUBLISHED_IN]->(venue)
CREATE (person)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(ins)
CREATE (conference)-[:EXTENDS]->(venue)
CREATE (journal)-[:EXTENDS]->(venue)
CREATE (univ)-[:EXTENDS]->(ins)
CREATE (industry)-[:EXTENDS]->(ins)
CREATE (researchIns)-[:EXTENDS]->(ins)
