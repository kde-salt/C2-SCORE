CREATE (artist:Artist { name: "mandatory", alias: "optional?" })
CREATE (album:Album { name: "mandatory", releasedYear: "mandatory" })
CREATE (track:Track { name: "mandatory", duration: "mandatory" })
CREATE (playlist:Playlist { name: "mandatory", modifiedAt: "mandatory", numFollowers: "mandatory" })
CREATE (pop:Pop)
CREATE (rock:Rock)

CREATE (artist)-[:PERFORMS]->(track)
CREATE (artist)-[:RELEASED { date: "mandatory" }]->(album)
CREATE (album)-[:BELONGS_TO]->(track) // Reverse edge connection: should be track->album
CREATE (playlist)<-[:CONTAINS]-(track) // Reverse edge connection: should be playlist->track
CREATE (pop)-[:EXTENDS]->(track)
CREATE (rock)-[:EXTENDS]->(track)
