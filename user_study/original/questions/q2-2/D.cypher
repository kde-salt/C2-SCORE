// Nodes
CREATE (artist { name: "mandatory", alias: "optional?" }) // Missing node label (removed :Artist)
CREATE (album:Album { name: "mandatory", releasedYear: "mandatory" })
CREATE (track:Track { name: "mandatory", duration: "mandatory" })
CREATE (playlist:Playlist { name: "mandatory", modifiedAt: "mandatory", numFollowers: "mandatory" })

// Relationships
CREATE (artist)-[:PERFORMS]->(track)
CREATE (artist)-[:RELEASED { date: "mandatory" }]->(album)
CREATE (album)<-[:BELONGS_TO]-(track)
CREATE (playlist)-[:CONTAINS]->(track)
