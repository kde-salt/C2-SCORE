CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory"})
CREATE (user2:User{id: "mandatory", name: "mandatory"}) // Regression: duplicated User node type

CREATE (user)-[:CREATES]->(post)
CREATE (user)-[:FOLLOWS]->(user2)
CREATE (user2)-[:FOLLOWS]->(user) // Regression: expanded self-loop edge
