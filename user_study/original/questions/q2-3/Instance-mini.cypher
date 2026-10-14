// Q2-3 reduced instance: 14 nodes / 19 edges (the full Instance.cypher has
// 30 / 50). Used for the follow-up user study, whose questionnaire is a single
// Markdown/PDF: the full instance figure is too dense to read on paper.
//
// It preserves the *complete type set* of Instance.cypher, which is what the
// C2 evaluation collapses an instance to
// (experiment/common/utils.py::_get_all_node_and_edge_types_from_instance):
//   node types  Artist{name; alias?} / Album{name, releasedYear}
//               / Pop:Track{name, duration} / Rock:Track{name, duration}
//               / Playlist{name, modifiedAt, numFollowers}
//   edge types  Artist-PERFORMS->Pop:Track, Artist-PERFORMS->Rock:Track,
//               Artist-RELEASED{date}->Album, Pop:Track-BELONGS_TO->Album,
//               Rock:Track-BELONGS_TO->Album, Playlist-CONTAINS->Pop:Track,
//               Playlist-CONTAINS->Rock:Track
// Two Artists differ in whether they carry `alias`, which is what keeps that
// property optional rather than mandatory.
//
// Verify with:
//   python -m experiment.task4.verify_mini \
//       --cypher user_study/questions/q2-3/Instance-mini.cypher \
//       --db q2-3-mini --baseline q2-3 --gt user_study/questions/q2-3/A.cypher

// === Nodes (14) ===
// Artists (6): 3 with alias, 3 without -> `alias` stays optional
CREATE (a1:Artist {name:"Ava Sterling", alias:"AVS"})
CREATE (a3:Artist {name:"Liam Hart", alias:"L.Hart"})
CREATE (a6:Artist {name:"Zoe Monroe", alias:"Z.M."})
CREATE (a2:Artist {name:"Noah Wilder"})
CREATE (a4:Artist {name:"Mia Collins"})
CREATE (a5:Artist {name:"Ethan Brooks"})

// Albums (2)
CREATE (al1:Album {name:"Neon Echoes", releasedYear:2019})
CREATE (al2:Album {name:"Paper Skies", releasedYear:2020})

// Tracks (4)
CREATE (t1:Track:Pop {name:"City Lights", duration:"03:28"})
CREATE (t5:Track:Pop {name:"Fever Dream", duration:"03:47"})
CREATE (t3:Track:Rock {name:"Hollow Moon", duration:"04:12"})
CREATE (t8:Track:Rock {name:"Running Red", duration:"03:50"})

// Playlists (2)
CREATE (p1:Playlist {name:"Fresh Finds Mix", modifiedAt:"2025-08-10", numFollowers:1243})
CREATE (p2:Playlist {name:"Roadtrip Fuel", modifiedAt:"2025-07-29", numFollowers:982})

// === Edges (19) ===
// PERFORMS (8) - artists with and without alias each reach Pop and Rock
CREATE (a1)-[:PERFORMS]->(t1)
CREATE (a1)-[:PERFORMS]->(t3)
CREATE (a3)-[:PERFORMS]->(t5)
CREATE (a6)-[:PERFORMS]->(t8)
CREATE (a2)-[:PERFORMS]->(t1)
CREATE (a2)-[:PERFORMS]->(t8)
CREATE (a4)-[:PERFORMS]->(t5)
CREATE (a5)-[:PERFORMS]->(t3)

// RELEASED (3) - artists with and without alias each release an album
CREATE (a1)-[:RELEASED {date:"2019-05-21"}]->(al1)
CREATE (a3)-[:RELEASED {date:"2021-09-03"}]->(al1)
CREATE (a2)-[:RELEASED {date:"2020-06-12"}]->(al2)

// BELONGS_TO (4)
CREATE (t1)-[:BELONGS_TO]->(al1)
CREATE (t3)-[:BELONGS_TO]->(al1)
CREATE (t5)-[:BELONGS_TO]->(al2)
CREATE (t8)-[:BELONGS_TO]->(al2)

// CONTAINS (4)
CREATE (p1)-[:CONTAINS]->(t1)
CREATE (p1)-[:CONTAINS]->(t3)
CREATE (p2)-[:CONTAINS]->(t5)
CREATE (p2)-[:CONTAINS]->(t8)
