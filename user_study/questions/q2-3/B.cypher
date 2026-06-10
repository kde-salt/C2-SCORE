CREATE (artist:Artist { name: "mandatory", alias: "optional?" })
CREATE (album:Album { name: "mandatory", releasedYear: "optional?" }) // Required/optional property mistake: releasedYear → optional?
CREATE (track:Track { name: "mandatory", duration: "mandatory" })
CREATE (playlist:Playlist { name: "mandatory", modifiedAt: "mandatory", numFollowers: "mandatory" })
CREATE (pop:Pop)
CREATE (rock:Rock)

CREATE (artist)-[:PERFORMS]->(track)
CREATE (artist)-[:RELEASED { date: "mandatory" }]->(album)
CREATE (track)-[:BELONGS_TO]->(album)
CREATE (playlist)-[:CONTAINS]->(track)
CREATE (pop)-[:EXTENDS]->(track)
CREATE (rock)-[:EXTENDS]->(track)
