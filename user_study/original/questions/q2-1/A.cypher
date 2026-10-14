CREATE (artist:Artist{name: "mandatory"})
CREATE (album:Album{name: "mandatory"})
CREATE (track:Track{name: "mandatory", duration: "mandatory"})

CREATE (artist)-[:PERFORMS]->(track)
CREATE (album)-[:RELEASED]->(artist) // Reverse edge connection
CREATE (track)-[:BELONGS_TO]->(album)
