CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory", bio: "optional?"})
CREATE (user2:User{id: "mandatory", name: "mandatory", bio: "optional?"}) // Regression (1): duplicated node type (User)

CREATE (user)-[:CREATES{timestamp: "mandatory"}]->(post)
CREATE (user2)-[:FOLLOWS{timestamp: "mandatory"}]->(user) // Regression (2): expanded self-loop edge
CREATE (user)-[:FOLLOWS{timestamp: "mandatory"}]->(user2) // Regression (2): expanded self-loop edge
CREATE (user2)-[:LIKES{timestamp: "mandatory"}]->(post)
