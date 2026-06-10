CREATE (artist:Artist{name: "mandatory"})
CREATE (album:Album{name: "mandatory"})
CREATE (track:Track{name: "mandatory", duration: "mandatory"})
CREATE (guest:Artist{name: "mandatory"}) // Duplicate Artist node type

CREATE (artist)-[:PERFORMS]->(track)
CREATE (guest)-[:PERFORMS]->(track) // Duplicate edge type
CREATE (artist)-[:RELEASED]->(album)
CREATE (track)-[:BELONGS_TO]->(album)
