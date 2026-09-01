// --------- Nodes ------------
CREATE (co:Company:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', phone:'optional?'}) // Inheritance expansion
CREATE (pe:Person:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', phone:'optional?'}) // Inheritance expansion
CREATE (o:Order      {order_id:'mandatory', order_date:'mandatory', status:'mandatory'})
CREATE (p:Product    {product_id:'mandatory', name:'mandatory', price:'mandatory', description:'optional?'})
CREATE (s:Supplier   {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'})
CREATE (c:Category   {category_id:'mandatory', name:'mandatory'})
CREATE (r:Region     {region_id:'mandatory', name:'mandatory'})

// ---------- Relationships -------------
MERGE (co)-[:PLACES_ORDER {channel:'optional?', delivery_time:'optional?'}]->(o) // Inheritance expansion
MERGE (pe)-[:PLACES_ORDER {channel:'optional?', delivery_time:'optional?'}]->(o) // Inheritance expansion
MERGE (o)-[:HAS_LINE_ITEM {quantity:'mandatory'}]->(p)
MERGE (p)-[:BELONGS_TO]->(c)
MERGE (c)-[:IS_PART_OF]->(c)
MERGE (s)-[:SUPPLIES]->(p)
MERGE (p)-[:MADE_IN]->(r)
MERGE (s)-[:PARTNERS_WITH]->(s)
MERGE (p)-[:FREQUENTLY_BOUGHT_WITH]->(p)
MERGE (co)-[:LOCATED_IN]->(r)
MERGE (pe)-[:LIVES_IN]->(r)
