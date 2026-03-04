// G-Lab integration test seed graph
// ~50 nodes (Person ×20, Company ×15, Address ×15)
// ~80 relationships (KNOWS, WORKS_AT, OWNS, LOCATED_AT)
//
// Usage: Run against a test Neo4j instance before integration tests.
// The CypherSanitiser allowlist does NOT allow MERGE/CREATE — this
// file is executed directly against Neo4j outside the G-Lab backend.

// ── Clear any prior state ──────────────────────────────────────────────────
MATCH (n) DETACH DELETE n;

// ── Person nodes (20) ─────────────────────────────────────────────────────
CREATE (p1:Person  {name: 'Alice Andersen',  born: 1980, email: 'alice@example.com'});
CREATE (p2:Person  {name: 'Bob Bergmann',    born: 1975, email: 'bob@example.com'});
CREATE (p3:Person  {name: 'Carol Chen',      born: 1990, email: 'carol@example.com'});
CREATE (p4:Person  {name: 'David Dupont',    born: 1965, email: 'david@example.com'});
CREATE (p5:Person  {name: 'Eva Eriksson',    born: 1985, email: 'eva@example.com'});
CREATE (p6:Person  {name: 'Frank Fischer',   born: 1970, email: 'frank@example.com'});
CREATE (p7:Person  {name: 'Grace Gomez',     born: 1995, email: 'grace@example.com'});
CREATE (p8:Person  {name: 'Hans Hoffmann',   born: 1960, email: 'hans@example.com'});
CREATE (p9:Person  {name: 'Ingrid Ivanova',  born: 1988, email: 'ingrid@example.com'});
CREATE (p10:Person {name: 'Jack Jensen',     born: 1978, email: 'jack@example.com'});
CREATE (p11:Person {name: 'Karen Kowalski',  born: 1983, email: 'karen@example.com'});
CREATE (p12:Person {name: 'Liam Larsson',    born: 1992, email: 'liam@example.com'});
CREATE (p13:Person {name: 'Mia Moreau',      born: 1987, email: 'mia@example.com'});
CREATE (p14:Person {name: 'Nils Nielsen',    born: 1973, email: 'nils@example.com'});
CREATE (p15:Person {name: 'Olivia Ortega',   born: 1996, email: 'olivia@example.com'});
CREATE (p16:Person {name: 'Peter Petrov',    born: 1968, email: 'peter@example.com'});
CREATE (p17:Person {name: 'Qian Qiu',        born: 1991, email: 'qian@example.com'});
CREATE (p18:Person {name: 'Rosa Russo',      born: 1982, email: 'rosa@example.com'});
CREATE (p19:Person {name: 'Stefan Schmidt',  born: 1977, email: 'stefan@example.com'});
CREATE (p20:Person {name: 'Tanya Tanaka',    born: 1993, email: 'tanya@example.com'});

// ── Company nodes (15) ────────────────────────────────────────────────────
CREATE (c1:Company  {name: 'Apex Analytics',    sector: 'Technology',  founded: 2005});
CREATE (c2:Company  {name: 'Blue Bridge Ltd',   sector: 'Finance',     founded: 1998});
CREATE (c3:Company  {name: 'CrestCorp',         sector: 'Energy',      founded: 2010});
CREATE (c4:Company  {name: 'Delta Dynamics',    sector: 'Technology',  founded: 2015});
CREATE (c5:Company  {name: 'Echo Enterprises',  sector: 'Retail',      founded: 2001});
CREATE (c6:Company  {name: 'Frontier Finance',  sector: 'Finance',     founded: 1995});
CREATE (c7:Company  {name: 'Global Goods Inc',  sector: 'Retail',      founded: 2008});
CREATE (c8:Company  {name: 'Harbor Holdings',   sector: 'Real Estate', founded: 2003});
CREATE (c9:Company  {name: 'Iris Innovations',  sector: 'Technology',  founded: 2018});
CREATE (c10:Company {name: 'Jasper & Jones',    sector: 'Legal',       founded: 1987});
CREATE (c11:Company {name: 'Kinetic Kapital',   sector: 'Finance',     founded: 2012});
CREATE (c12:Company {name: 'Luminary Labs',     sector: 'Technology',  founded: 2020});
CREATE (c13:Company {name: 'Meridian Media',    sector: 'Media',       founded: 2006});
CREATE (c14:Company {name: 'Northstar Nett',    sector: 'Telecom',     founded: 1999});
CREATE (c15:Company {name: 'Orbit Operations',  sector: 'Logistics',   founded: 2014});

// ── Address nodes (15) ────────────────────────────────────────────────────
CREATE (a1:Address  {street: '10 Baker St',      city: 'London',    country: 'UK'});
CREATE (a2:Address  {street: '22 Rue de Paix',   city: 'Paris',     country: 'FR'});
CREATE (a3:Address  {street: '5 Hauptstraße',     city: 'Berlin',    country: 'DE'});
CREATE (a4:Address  {street: '100 Main Ave',      city: 'New York',  country: 'US'});
CREATE (a5:Address  {street: '88 Queen Rd',       city: 'Sydney',    country: 'AU'});
CREATE (a6:Address  {street: '3 Via Roma',        city: 'Rome',      country: 'IT'});
CREATE (a7:Address  {street: '7 Gran Vía',        city: 'Madrid',    country: 'ES'});
CREATE (a8:Address  {street: '15 Nanjing Rd',     city: 'Shanghai',  country: 'CN'});
CREATE (a9:Address  {street: '30 Yonge St',       city: 'Toronto',   country: 'CA'});
CREATE (a10:Address {street: '200 King St',       city: 'Amsterdam', country: 'NL'});
CREATE (a11:Address {street: '9 Arbat St',        city: 'Moscow',    country: 'RU'});
CREATE (a12:Address {street: '55 Crown Pl',       city: 'Cape Town', country: 'ZA'});
CREATE (a13:Address {street: '18 Sukhumvit Rd',   city: 'Bangkok',   country: 'TH'});
CREATE (a14:Address {street: '41 Paulista Ave',   city: 'São Paulo', country: 'BR'});
CREATE (a15:Address {street: '6 Collins St',      city: 'Melbourne', country: 'AU'});

// ── KNOWS relationships (20) ──────────────────────────────────────────────
MATCH (a:Person {name:'Alice Andersen'}),  (b:Person {name:'Bob Bergmann'})    CREATE (a)-[:KNOWS {since: 2010}]->(b);
MATCH (a:Person {name:'Alice Andersen'}),  (b:Person {name:'Carol Chen'})      CREATE (a)-[:KNOWS {since: 2015}]->(b);
MATCH (a:Person {name:'Bob Bergmann'}),    (b:Person {name:'David Dupont'})    CREATE (a)-[:KNOWS {since: 2005}]->(b);
MATCH (a:Person {name:'Carol Chen'}),      (b:Person {name:'Eva Eriksson'})    CREATE (a)-[:KNOWS {since: 2018}]->(b);
MATCH (a:Person {name:'David Dupont'}),    (b:Person {name:'Frank Fischer'})   CREATE (a)-[:KNOWS {since: 2000}]->(b);
MATCH (a:Person {name:'Eva Eriksson'}),    (b:Person {name:'Grace Gomez'})     CREATE (a)-[:KNOWS {since: 2019}]->(b);
MATCH (a:Person {name:'Frank Fischer'}),   (b:Person {name:'Hans Hoffmann'})   CREATE (a)-[:KNOWS {since: 1998}]->(b);
MATCH (a:Person {name:'Grace Gomez'}),     (b:Person {name:'Ingrid Ivanova'})  CREATE (a)-[:KNOWS {since: 2020}]->(b);
MATCH (a:Person {name:'Hans Hoffmann'}),   (b:Person {name:'Jack Jensen'})     CREATE (a)-[:KNOWS {since: 2002}]->(b);
MATCH (a:Person {name:'Ingrid Ivanova'}),  (b:Person {name:'Karen Kowalski'})  CREATE (a)-[:KNOWS {since: 2016}]->(b);
MATCH (a:Person {name:'Jack Jensen'}),     (b:Person {name:'Liam Larsson'})    CREATE (a)-[:KNOWS {since: 2012}]->(b);
MATCH (a:Person {name:'Karen Kowalski'}),  (b:Person {name:'Mia Moreau'})      CREATE (a)-[:KNOWS {since: 2017}]->(b);
MATCH (a:Person {name:'Liam Larsson'}),    (b:Person {name:'Nils Nielsen'})    CREATE (a)-[:KNOWS {since: 2014}]->(b);
MATCH (a:Person {name:'Mia Moreau'}),      (b:Person {name:'Olivia Ortega'})   CREATE (a)-[:KNOWS {since: 2021}]->(b);
MATCH (a:Person {name:'Nils Nielsen'}),    (b:Person {name:'Peter Petrov'})    CREATE (a)-[:KNOWS {since: 2008}]->(b);
MATCH (a:Person {name:'Olivia Ortega'}),   (b:Person {name:'Qian Qiu'})        CREATE (a)-[:KNOWS {since: 2022}]->(b);
MATCH (a:Person {name:'Peter Petrov'}),    (b:Person {name:'Rosa Russo'})      CREATE (a)-[:KNOWS {since: 2007}]->(b);
MATCH (a:Person {name:'Qian Qiu'}),        (b:Person {name:'Stefan Schmidt'})  CREATE (a)-[:KNOWS {since: 2020}]->(b);
MATCH (a:Person {name:'Rosa Russo'}),      (b:Person {name:'Tanya Tanaka'})    CREATE (a)-[:KNOWS {since: 2019}]->(b);
MATCH (a:Person {name:'Tanya Tanaka'}),    (b:Person {name:'Alice Andersen'})  CREATE (a)-[:KNOWS {since: 2023}]->(b);

// ── WORKS_AT relationships (20) ───────────────────────────────────────────
MATCH (p:Person {name:'Alice Andersen'}),  (c:Company {name:'Apex Analytics'})   CREATE (p)-[:WORKS_AT {role:'Engineer',   since:2015}]->(c);
MATCH (p:Person {name:'Bob Bergmann'}),    (c:Company {name:'Blue Bridge Ltd'})   CREATE (p)-[:WORKS_AT {role:'Analyst',    since:2010}]->(c);
MATCH (p:Person {name:'Carol Chen'}),      (c:Company {name:'CrestCorp'})         CREATE (p)-[:WORKS_AT {role:'Manager',    since:2018}]->(c);
MATCH (p:Person {name:'David Dupont'}),    (c:Company {name:'Delta Dynamics'})    CREATE (p)-[:WORKS_AT {role:'Director',   since:2016}]->(c);
MATCH (p:Person {name:'Eva Eriksson'}),    (c:Company {name:'Echo Enterprises'})  CREATE (p)-[:WORKS_AT {role:'Consultant', since:2020}]->(c);
MATCH (p:Person {name:'Frank Fischer'}),   (c:Company {name:'Frontier Finance'})  CREATE (p)-[:WORKS_AT {role:'Trader',     since:2005}]->(c);
MATCH (p:Person {name:'Grace Gomez'}),     (c:Company {name:'Global Goods Inc'})  CREATE (p)-[:WORKS_AT {role:'Buyer',      since:2021}]->(c);
MATCH (p:Person {name:'Hans Hoffmann'}),   (c:Company {name:'Harbor Holdings'})   CREATE (p)-[:WORKS_AT {role:'Broker',     since:2003}]->(c);
MATCH (p:Person {name:'Ingrid Ivanova'}),  (c:Company {name:'Iris Innovations'})  CREATE (p)-[:WORKS_AT {role:'Researcher', since:2019}]->(c);
MATCH (p:Person {name:'Jack Jensen'}),     (c:Company {name:'Jasper & Jones'})    CREATE (p)-[:WORKS_AT {role:'Lawyer',     since:2012}]->(c);
MATCH (p:Person {name:'Karen Kowalski'}),  (c:Company {name:'Kinetic Kapital'})   CREATE (p)-[:WORKS_AT {role:'Advisor',    since:2017}]->(c);
MATCH (p:Person {name:'Liam Larsson'}),    (c:Company {name:'Luminary Labs'})     CREATE (p)-[:WORKS_AT {role:'Developer',  since:2020}]->(c);
MATCH (p:Person {name:'Mia Moreau'}),      (c:Company {name:'Meridian Media'})    CREATE (p)-[:WORKS_AT {role:'Producer',   since:2015}]->(c);
MATCH (p:Person {name:'Nils Nielsen'}),    (c:Company {name:'Northstar Nett'})    CREATE (p)-[:WORKS_AT {role:'Engineer',   since:2008}]->(c);
MATCH (p:Person {name:'Olivia Ortega'}),   (c:Company {name:'Orbit Operations'})  CREATE (p)-[:WORKS_AT {role:'Planner',    since:2022}]->(c);
MATCH (p:Person {name:'Peter Petrov'}),    (c:Company {name:'Apex Analytics'})    CREATE (p)-[:WORKS_AT {role:'Architect',  since:2006}]->(c);
MATCH (p:Person {name:'Qian Qiu'}),        (c:Company {name:'CrestCorp'})         CREATE (p)-[:WORKS_AT {role:'Scientist',  since:2021}]->(c);
MATCH (p:Person {name:'Rosa Russo'}),      (c:Company {name:'Blue Bridge Ltd'})   CREATE (p)-[:WORKS_AT {role:'Associate',  since:2018}]->(c);
MATCH (p:Person {name:'Stefan Schmidt'}),  (c:Company {name:'Delta Dynamics'})    CREATE (p)-[:WORKS_AT {role:'Engineer',   since:2019}]->(c);
MATCH (p:Person {name:'Tanya Tanaka'}),    (c:Company {name:'Echo Enterprises'})  CREATE (p)-[:WORKS_AT {role:'Intern',     since:2023}]->(c);

// ── OWNS relationships (20) ───────────────────────────────────────────────
MATCH (p:Person {name:'Alice Andersen'}),  (c:Company {name:'Apex Analytics'})   CREATE (p)-[:OWNS {share_pct: 25}]->(c);
MATCH (p:Person {name:'Bob Bergmann'}),    (c:Company {name:'Blue Bridge Ltd'})   CREATE (p)-[:OWNS {share_pct: 30}]->(c);
MATCH (p:Person {name:'Carol Chen'}),      (c:Company {name:'Luminary Labs'})     CREATE (p)-[:OWNS {share_pct: 51}]->(c);
MATCH (p:Person {name:'David Dupont'}),    (c:Company {name:'Harbor Holdings'})   CREATE (p)-[:OWNS {share_pct: 15}]->(c);
MATCH (p:Person {name:'Eva Eriksson'}),    (c:Company {name:'Iris Innovations'})  CREATE (p)-[:OWNS {share_pct: 40}]->(c);
MATCH (p:Person {name:'Frank Fischer'}),   (c:Company {name:'Frontier Finance'})  CREATE (p)-[:OWNS {share_pct: 60}]->(c);
MATCH (p:Person {name:'Grace Gomez'}),     (c:Company {name:'Global Goods Inc'})  CREATE (p)-[:OWNS {share_pct: 20}]->(c);
MATCH (p:Person {name:'Hans Hoffmann'}),   (c:Company {name:'Harbor Holdings'})   CREATE (p)-[:OWNS {share_pct: 35}]->(c);
MATCH (p:Person {name:'Ingrid Ivanova'}),  (c:Company {name:'Kinetic Kapital'})   CREATE (p)-[:OWNS {share_pct: 10}]->(c);
MATCH (p:Person {name:'Jack Jensen'}),     (c:Company {name:'Jasper & Jones'})    CREATE (p)-[:OWNS {share_pct: 50}]->(c);
MATCH (p:Person {name:'Karen Kowalski'}),  (c:Company {name:'CrestCorp'})         CREATE (p)-[:OWNS {share_pct: 22}]->(c);
MATCH (p:Person {name:'Liam Larsson'}),    (c:Company {name:'Meridian Media'})    CREATE (p)-[:OWNS {share_pct: 18}]->(c);
MATCH (p:Person {name:'Mia Moreau'}),      (c:Company {name:'Echo Enterprises'})  CREATE (p)-[:OWNS {share_pct: 45}]->(c);
MATCH (p:Person {name:'Nils Nielsen'}),    (c:Company {name:'Northstar Nett'})    CREATE (p)-[:OWNS {share_pct: 33}]->(c);
MATCH (p:Person {name:'Olivia Ortega'}),   (c:Company {name:'Orbit Operations'})  CREATE (p)-[:OWNS {share_pct: 55}]->(c);
MATCH (p:Person {name:'Peter Petrov'}),    (c:Company {name:'Delta Dynamics'})    CREATE (p)-[:OWNS {share_pct: 12}]->(c);
MATCH (p:Person {name:'Qian Qiu'}),        (c:Company {name:'Apex Analytics'})    CREATE (p)-[:OWNS {share_pct: 8}]->(c);
MATCH (p:Person {name:'Rosa Russo'}),      (c:Company {name:'Blue Bridge Ltd'})   CREATE (p)-[:OWNS {share_pct: 28}]->(c);
MATCH (p:Person {name:'Stefan Schmidt'}),  (c:Company {name:'Global Goods Inc'})  CREATE (p)-[:OWNS {share_pct: 5}]->(c);
MATCH (p:Person {name:'Tanya Tanaka'}),    (c:Company {name:'Luminary Labs'})     CREATE (p)-[:OWNS {share_pct: 49}]->(c);

// ── LOCATED_AT relationships (20) ─────────────────────────────────────────
MATCH (p:Person  {name:'Alice Andersen'}), (a:Address {street:'10 Baker St'})     CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Bob Bergmann'}),   (a:Address {street:'3 Via Roma'})      CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Carol Chen'}),     (a:Address {street:'15 Nanjing Rd'})   CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'David Dupont'}),   (a:Address {street:'22 Rue de Paix'}) CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Eva Eriksson'}),   (a:Address {street:'5 Hauptstraße'})   CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Frank Fischer'}),  (a:Address {street:'5 Hauptstraße'})   CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Grace Gomez'}),    (a:Address {street:'7 Gran Vía'})      CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Hans Hoffmann'}),  (a:Address {street:'5 Hauptstraße'})   CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Ingrid Ivanova'}), (a:Address {street:'9 Arbat St'})      CREATE (p)-[:LOCATED_AT]->(a);
MATCH (p:Person  {name:'Jack Jensen'}),    (a:Address {street:'200 King St'})     CREATE (p)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Apex Analytics'}),  (a:Address {street:'100 Main Ave'})   CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Blue Bridge Ltd'}), (a:Address {street:'10 Baker St'})    CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'CrestCorp'}),       (a:Address {street:'30 Yonge St'})    CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Delta Dynamics'}),  (a:Address {street:'88 Queen Rd'})    CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Echo Enterprises'}),(a:Address {street:'41 Paulista Ave'})CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Frontier Finance'}),(a:Address {street:'22 Rue de Paix'}) CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Global Goods Inc'}),(a:Address {street:'7 Gran Vía'})     CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Harbor Holdings'}), (a:Address {street:'10 Baker St'})    CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Iris Innovations'}),(a:Address {street:'15 Nanjing Rd'})  CREATE (c)-[:LOCATED_AT]->(a);
MATCH (c:Company {name:'Jasper & Jones'}),  (a:Address {street:'10 Baker St'})    CREATE (c)-[:LOCATED_AT]->(a);
