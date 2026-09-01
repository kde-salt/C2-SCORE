CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory", bio: "optional?"})
// Regression: expanded inheritance edge
CREATE (official:User:Official{id: "mandatory", name: "mandatory", bio: "optional?", verifiedAt: "mandatory"})

CREATE (user)-[:CREATES{timestamp: "mandatory"}]->(post)
CREATE (official)-[:CREATES{timestamp: "mandatory"}]->(post)
CREATE (user)-[:LIKES{timestamp: "mandatory"}]->(post)
CREATE (official)-[:LIKES{timestamp: "mandatory"}]->(post)

CREATE (user)-[:FOLLOWS{timestamp: "mandatory"}]->(official)
CREATE (user)-[:FOLLOWS{timestamp: "mandatory"}]->(user)
CREATE (official)-[:FOLLOWS{timestamp: "mandatory"}]->(official)
CREATE (official)-[:FOLLOWS{timestamp: "mandatory"}]->(user)
