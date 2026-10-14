// =====================
// Institution
// =====================
CREATE (ins1:Institution {name:"Aurora Research Institute", type:"Research Institute"})
CREATE (ins2:Institution {name:"Lumen Tech Labs", type:"Industry"})
CREATE (ins3:Institution {name:"Orion Medical Center", type:"Industry"})
CREATE (ins4:Institution {name:"Helios Institute of Science", type:"University"})
CREATE (ins5:Institution {name:"Nexa Innovations", type:"Industry"})

// =====================
// Person (with optional orcid)
// =====================
CREATE (p1:Person {name:"Alice Tanaka", orcid:"0000-0001-2345-6789"})
CREATE (p2:Person {name:"Brian Lee"})
CREATE (p3:Person {name:"Clara Suzuki", orcid:"0000-0002-1111-2222"})
CREATE (p4:Person {name:"Daniel Ito"})
CREATE (p5:Person {name:"Elena Nakamura", orcid:"0000-0003-3333-4444"})
CREATE (p6:Person {name:"Fiona Yamamoto"})
CREATE (p7:Person {name:"George Kato"})
CREATE (p8:Person {name:"Hana Mori", orcid:"0000-0004-5555-6666"})
CREATE (p9:Person {name:"Isaac Fujii"})
CREATE (p10:Person {name:"Julia Sato"})

// =====================
// Venue (Conference | Journal) with optional year/volume/issue
// =====================
CREATE (v1:Venue {name:"Symposium on Artificial Minds", type:"Conference", year:2020})
CREATE (v2:Venue {name:"Journal of Sustainable Robotics", type:"Journal", volume:12, issue:3})
CREATE (v3:Venue {name:"Quantum Data Communications", type:"Conference", year:2021})
CREATE (v4:Venue {name:"International Journal of Climate & AI", type:"Journal", volume:5, issue:1})

// =====================
// Paper (with optional doi)
// =====================
CREATE (pa1:Paper {title:"Neural Pathways in Artificial Minds", year:2020, doi:"10.5555/npam.2020.001"})
CREATE (pa2:Paper {title:"Quantum-Based Data Transmission", year:2021, doi:"10.5555/qbdt.2021.042"})
CREATE (pa3:Paper {title:"Adaptive Healthcare Systems", year:2019})
CREATE (pa4:Paper {title:"Sustainable Robotics Design", year:2022, doi:"10.5555/srd.2022.010"})
CREATE (pa5:Paper {title:"Cognitive Models for Language Processing", year:2020})
CREATE (pa6:Paper {title:"Efficient Energy Grids", year:2021, doi:"10.5555/eeg.2021.077"})
CREATE (pa7:Paper {title:"Nanotechnology in Medicine", year:2018})
CREATE (pa8:Paper {title:"Autonomous Vehicle Ethics", year:2019, doi:"10.5555/ave.2019.015"})
CREATE (pa9:Paper {title:"Augmented Reality Learning", year:2022})
CREATE (pa10:Paper {title:"Climate-Aware AI Models", year:2023, doi:"10.5555/caai.2023.002"})

// =====================
// Affiliation (from mandatory, to optional)
// =====================
CREATE (p1)-[:AFFILIATED_WITH {from:"2018-04", to:"2021-03"}]->(ins1)
CREATE (p2)-[:AFFILIATED_WITH {from:"2019-06", to:"2023-03"}]->(ins2)
CREATE (p3)-[:AFFILIATED_WITH {from:"2017-10"}]->(ins1)
CREATE (p4)-[:AFFILIATED_WITH {from:"2020-01"}]->(ins3)
CREATE (p5)-[:AFFILIATED_WITH {from:"2016-04", to:"2021-09"}]->(ins4)
CREATE (p6)-[:AFFILIATED_WITH {from:"2021-07"}]->(ins2)
CREATE (p7)-[:AFFILIATED_WITH {from:"2015-04", to:"2020-09"}]->(ins5)
CREATE (p8)-[:AFFILIATED_WITH {from:"2019-04"}]->(ins4)
CREATE (p9)-[:AFFILIATED_WITH {from:"2018-01"}]->(ins3)
CREATE (p10)-[:AFFILIATED_WITH {from:"2022-04"}]->(ins5)

// =====================
// Authorship with authorIndex (1-based)
//  - Single-author papers have authorIndex=1
//  - Multi-author papers get unique 1,2,... without duplicates
// =====================
CREATE (p1)-[:AUTHORED {authorIndex:1}]->(pa1)
CREATE (p2)-[:AUTHORED {authorIndex:1}]->(pa2)
CREATE (p3)-[:AUTHORED {authorIndex:1}]->(pa3)
CREATE (p4)-[:AUTHORED {authorIndex:1}]->(pa4)
CREATE (p5)-[:AUTHORED {authorIndex:1}]->(pa5)
CREATE (p6)-[:AUTHORED {authorIndex:1}]->(pa6)
CREATE (p7)-[:AUTHORED {authorIndex:1}]->(pa7)
CREATE (p8)-[:AUTHORED {authorIndex:1}]->(pa8)
CREATE (p9)-[:AUTHORED {authorIndex:1}]->(pa9)
CREATE (p10)-[:AUTHORED {authorIndex:1}]->(pa10)

// Additional co-authorship relationships (turn some existing papers into co-authored)
CREATE (p1)-[:AUTHORED {authorIndex:2}]->(pa5)    // pa5: Elena(1), Alice(2)
CREATE (p5)-[:AUTHORED {authorIndex:1}]->(pa5)
CREATE (p3)-[:AUTHORED {authorIndex:2}]->(pa9)    // pa9: Isaac(1), Clara(2)
CREATE (p9)-[:AUTHORED {authorIndex:1}]->(pa9)
CREATE (p6)-[:AUTHORED {authorIndex:2}]->(pa2)    // pa2: Brian(1), Fiona(2)
CREATE (p2)-[:AUTHORED {authorIndex:1}]->(pa2)
CREATE (p8)-[:AUTHORED {authorIndex:2}]->(pa10)   // pa10: Julia(1), Hana(2)
CREATE (p10)-[:AUTHORED {authorIndex:1}]->(pa10)

// =====================
// Citations
// =====================
CREATE (pa1)-[:CITES]->(pa3)
CREATE (pa2)-[:CITES]->(pa1)
CREATE (pa3)-[:CITES]->(pa7)
CREATE (pa4)-[:CITES]->(pa2)
CREATE (pa5)-[:CITES]->(pa1)
CREATE (pa6)-[:CITES]->(pa4)
CREATE (pa7)-[:CITES]->(pa3)
CREATE (pa8)-[:CITES]->(pa6)
CREATE (pa9)-[:CITES]->(pa5)
CREATE (pa10)-[:CITES]->(pa8)

// =====================
// Published In (Paper -> Venue)
// =====================
CREATE (pa1)-[:PUBLISHED_IN]->(v1)
CREATE (pa2)-[:PUBLISHED_IN]->(v3)
CREATE (pa3)-[:PUBLISHED_IN]->(v2)
CREATE (pa4)-[:PUBLISHED_IN]->(v2)
CREATE (pa5)-[:PUBLISHED_IN]->(v1)
CREATE (pa6)-[:PUBLISHED_IN]->(v3)
CREATE (pa7)-[:PUBLISHED_IN]->(v2)
CREATE (pa8)-[:PUBLISHED_IN]->(v1)
CREATE (pa9)-[:PUBLISHED_IN]->(v1)
CREATE (pa10)-[:PUBLISHED_IN]->(v4)
