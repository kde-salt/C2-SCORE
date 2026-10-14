CREATE (artist:Artist{name: "mandatory"})
CREATE (album:Album{name: "mandatory"})
CREATE (track:Track{name: "mandatory", duration: "mandatory"})

CREATE (artist)-[:PERFORMS]->(track)
CREATE (artist)-[:RELEASED]->(album)
CREATE (track)-[:BELONGS_TO]->(album)
