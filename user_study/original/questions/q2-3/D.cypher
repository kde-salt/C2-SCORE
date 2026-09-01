CREATE (artist:Artist { name: "mandatory", alias: "optional?" })
CREATE (album:Album { name: "mandatory", releasedYear: "mandatory" })
CREATE (track:Track { name: "mandatory", duration: "mandatory" })
// Missing CREATE (playlist:Playlist { ... }) // Missing node type: removed Playlist
CREATE (pop:Pop)
CREATE (rock:Rock)

// Missing CREATE (playlist)-[:CONTAINS]->(track) // Missing edge type: removed CONTAINS
CREATE (artist)-[:PERFORMS]->(track)
CREATE (artist)-[:RELEASED { date: "mandatory" }]->(album)
CREATE (track)-[:BELONGS_TO]->(album)
CREATE (pop)-[:EXTENDS]->(track)
CREATE (rock)-[:EXTENDS]->(track)
