CREATE (post:Post{text: "mandatory"})
CREATE (user:User{id: "mandatory", name: "mandatory"})

CREATE (user)-[:CREATES]->(post)
CREATE (user)-[:FOLLOWS]->(user)
