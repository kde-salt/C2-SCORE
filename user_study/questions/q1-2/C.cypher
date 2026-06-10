CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", bio: "optional?"}) // Regression: missing name property

CREATE (user)-[:CREATES{timestamp: "mandatory"}]->(post)
CREATE (user)-[:FOLLOWS{timestamp: "mandatory"}]->(user)
CREATE (user)-[:LIKES]->(post) // Regression: missing edge property (timestamp omitted)
