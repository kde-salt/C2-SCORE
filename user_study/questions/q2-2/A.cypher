// Nodes
CREATE (artist:Artist { name: "mandatory", alias: "optional?" })
CREATE (album:Album { name: "mandatory", releasedYear: "mandatory" })
CREATE (track:Track { name: "mandatory", duration: "mandatory" })
CREATE (playlist:Playlist { name: "mandatory", modifiedAt: "mandatory", numFollowers: "mandatory" })

// Relationships
CREATE (artist)-[:PERFORMS]->(track)
CREATE (artist)-[:RELEASED{date: "mandatory"}]->(album)
CREATE (track)-[:BELONGS_TO]->(album)
CREATE (playlist)-[:CONTAINS]->(album) // Incorrect edge connection (should connect to track)
