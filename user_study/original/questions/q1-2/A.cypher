CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory", bio: "mandatory"}) // Regression: required/optional mistake (bio optional? → mandatory)

CREATE (user)-[:CREATES{timestamp: "mandatory"}]->(post)
CREATE (user)-[:FOLLOWS{timestamp: "mandatory"}]->(user)
CREATE (user)-[:LIKES{timestamp: "mandatory"}]->(post)
