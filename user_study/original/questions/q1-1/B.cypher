CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory"}) // Regression: missing name property

CREATE (user)-[:CREATES]->(post)
CREATE (user)-[:FOLLOWS]->(user)
