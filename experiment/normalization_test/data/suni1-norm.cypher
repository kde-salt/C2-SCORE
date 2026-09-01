// S_Uni-1 normalized graph, transcribed from Fig. 2 of Schrott et al. "Graph-Native Normalization"
// (arXiv:2603.02995). Result of psi_between-n-ep for the GO-FD
//   (c:Course)<-[t:TEACHES:usingBook]-() :: c => t.usingBook
// applied to suni1.cypher: usingBook moves from the TEACHES edges to the Course node.
// Node/edge counts unchanged (4 / 3); AvgPropNode 1.25 -> 1.5, AvgPropEdge 2 -> 1 (paper Tables 7/9).
CREATE (d:Course {title: "Database Systems", language: "English", usingBook: "Alice"})
CREATE (k:Lecturer {name: "Katja"})
CREATE (j:Lecturer {name: "Johannes"})
CREATE (m:Lecturer {name: "Maxime"})
CREATE (k)-[:TEACHES {at: "2026-02-23"}]->(d)
CREATE (j)-[:TEACHES {at: "2026-02-09"}]->(d)
CREATE (m)-[:TEACHES {at: "2026-02-16"}]->(d)
