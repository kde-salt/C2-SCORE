CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory"})

CREATE (user)-[:CREATES]->(post)
CREATE (user)-[:LIKES]->(post) // Regression: edge type not present in data
CREATE (user)-[:FOLLOWS]->(user)
