CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory", bio: "optional?"})
CREATE (official:Official{verifiedAt: "mandatory"})

CREATE (user)-[:CREATES{timestamp: "mandatory"}]->(post)
CREATE (user)-[:FOLLOWS{timestamp: "mandatory"}]->(user)
CREATE (user)-[:LIKES{timestamp: "mandatory"}]->(post)
CREATE (official)-[:EXTENDS]->(user)
