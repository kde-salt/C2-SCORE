// Q3-3 reduced instance: 17 nodes / 26 edges (the full Instance.cypher has
// 29 / 44). Used for the follow-up user study, whose questionnaire is a single
// Markdown/PDF: the full instance figure is too dense to read on paper.
//
// It preserves the *complete type set* of Instance.cypher, which is what the
// C2 evaluation collapses an instance to
// (experiment/common/utils.py::_get_all_node_and_edge_types_from_instance):
//   node types  Person{name; orcid?} / Paper{title, year; doi?}
//               / Conference:Venue{name, year} / Journal:Venue{name, volume, issue}
//               / Institution:University{name} / Industry:Institution{name}
//               / Institution:ResearchInstitute{name}
//   edge types  Person-AUTHORED{authorIndex}->Paper, Paper-CITES->Paper,
//               Paper-PUBLISHED_IN->Conference:Venue,
//               Paper-PUBLISHED_IN->Journal:Venue, and
//               Person-AFFILIATED_WITH{from; to?}-> each of the 3 Institution types
// Each AFFILIATED_WITH target type needs one edge carrying `to` and one
// without, which is what keeps that property optional; Person.orcid and
// Paper.doi need the same present/absent pair.
//
// Verify with:
//   python -m experiment.task4.verify_mini \
//       --cypher user_study/questions/q3-3/Instance-mini.cypher \
//       --db q5-2-mini --gt user_study/questions/q3-3/D.cypher
//
// Distribution: Person 1 without orcid / 3 with, Paper 1 without doi / 5 with,
// 2 Conference, 1 Journal, 1 ResearchInstitute, 2 Industry, 1 University.
// The 1:3 and 1:5 splits are what make gmmschema keep Person and Paper as two
// node types each; when it merges them into one type with an optional property
// the per-edge endpoint signatures stop matching and every incident edge type
// disappears from its output.
//
// The edge counts are not arbitrary either. AUTHORED is deliberately the most
// frequent edge type (8 vs 6/6/6) and PUBLISHED_IN is deliberately skewed
// toward Conference (4 vs 2). pg-hive embeds relationship-type and endpoint
// label *names* with Word2Vec, whose vocabulary Spark orders by frequency, so
// these counts decide which types share an LSH bucket -- and therefore how
// many spurious edge types its cross-product expansion produces (14 here, 11
// with the earlier 17/21 distribution).

// === Institution (4) ===
CREATE (ins1:Institution:ResearchInstitute {name:"Aurora Research Institute"})
CREATE (ins2:Institution:Industry {name:"Lumen Tech Labs"})
CREATE (ins3:Institution:Industry {name:"Orion Medical Center"})
CREATE (ins4:Institution:University {name:"Helios Institute of Science"})

// === Person (4): one without orcid, three with ===
CREATE (p2:Person {name:"Brian Lee"})
CREATE (p1:Person {name:"Alice Tanaka", orcid:"0000-0001-2345-6789"})
CREATE (p3:Person {name:"Clara Suzuki", orcid:"0000-0002-1111-2222"})
CREATE (p5:Person {name:"Elena Nakamura", orcid:"0000-0003-3333-4444"})

// === Venue (3): two Conference, one Journal ===
CREATE (v1:Venue:Conference {name:"Symposium on Artificial Minds", year:2020})
CREATE (v3:Venue:Conference {name:"Quantum Data Communications", year:2021})
CREATE (v2:Venue:Journal {name:"Journal of Sustainable Robotics", volume:12, issue:3})

// === Paper (6): one without doi, five with ===
CREATE (pa3:Paper {title:"Adaptive Healthcare Systems", year:2019})
CREATE (pa1:Paper {title:"Neural Pathways in Artificial Minds", year:2020, doi:"10.5555/npam.2020.001"})
CREATE (pa2:Paper {title:"Quantum-Based Data Transmission", year:2021, doi:"10.5555/qbdt.2021.042"})
CREATE (pa4:Paper {title:"Sustainable Robotics Design", year:2022, doi:"10.5555/srd.2022.010"})
CREATE (pa6:Paper {title:"Efficient Energy Grids", year:2021, doi:"10.5555/eeg.2021.077"})
CREATE (pa7:Paper {title:"Nanotechnology in Medicine", year:2018, doi:"10.5555/nim.2018.031"})

// === AFFILIATED_WITH (6): each target type gets one edge with `to` and one without ===
CREATE (p1)-[:AFFILIATED_WITH {from:"2018-04", to:"2021-03"}]->(ins1)
CREATE (p3)-[:AFFILIATED_WITH {from:"2017-10"}]->(ins1)
CREATE (p2)-[:AFFILIATED_WITH {from:"2019-06", to:"2023-03"}]->(ins2)
CREATE (p5)-[:AFFILIATED_WITH {from:"2020-01"}]->(ins3)
CREATE (p1)-[:AFFILIATED_WITH {from:"2016-04", to:"2021-09"}]->(ins4)
CREATE (p2)-[:AFFILIATED_WITH {from:"2019-04"}]->(ins4)

// === AUTHORED (8): the most frequent edge type (see the header) ===
CREATE (p2)-[:AUTHORED {authorIndex:1}]->(pa3)
CREATE (p2)-[:AUTHORED {authorIndex:1}]->(pa1)
CREATE (p1)-[:AUTHORED {authorIndex:1}]->(pa2)
CREATE (p3)-[:AUTHORED {authorIndex:1}]->(pa4)
CREATE (p5)-[:AUTHORED {authorIndex:1}]->(pa6)
CREATE (p1)-[:AUTHORED {authorIndex:1}]->(pa7)
CREATE (p1)-[:AUTHORED {authorIndex:2}]->(pa3)
CREATE (p3)-[:AUTHORED {authorIndex:2}]->(pa1)

// === CITES (6) ===
CREATE (pa1)-[:CITES]->(pa3)
CREATE (pa2)-[:CITES]->(pa1)
CREATE (pa3)-[:CITES]->(pa4)
CREATE (pa6)-[:CITES]->(pa2)
CREATE (pa4)-[:CITES]->(pa1)
CREATE (pa7)-[:CITES]->(pa2)

// === PUBLISHED_IN (6): skewed 4 Conference / 2 Journal (see the header) ===
CREATE (pa1)-[:PUBLISHED_IN]->(v1)
CREATE (pa3)-[:PUBLISHED_IN]->(v1)
CREATE (pa2)-[:PUBLISHED_IN]->(v3)
CREATE (pa4)-[:PUBLISHED_IN]->(v3)
CREATE (pa6)-[:PUBLISHED_IN]->(v2)
CREATE (pa7)-[:PUBLISHED_IN]->(v2)
