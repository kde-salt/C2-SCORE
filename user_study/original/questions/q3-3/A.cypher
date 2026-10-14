CREATE (person:Person{name: "mandatory", orcid: "optional?"})
CREATE (paper:Paper{title: "mandatory", year: "mandatory", doi: "optional?"})
CREATE (venue:Venue:Conference:Journal{name: "mandatory", year: "mandatory", volume: "mandatory", issue: "mandatory"}) // Label merge
CREATE (ins:Institution:University:Industry:ResearchInstitute{name: "mandatory"}) // Label merge

CREATE (person)-[:AUTHORED{authorIndex: "mandatory"}]->(paper)
CREATE (paper)-[:CITES]->(paper)
CREATE (paper)-[:PUBLISHED_IN]->(venue)
CREATE (person)-[:AFFILIATED_WITH{from: "mandatory", to:"optional?"}]->(ins)
