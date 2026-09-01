// --------- Nodes ------------
CREATE (cust:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', type:'mandatory', phone:'mandatory'}) // Regression 1: changed from optional? to mandatory
CREATE (o:Order      {order_id:'mandatory', order_date:'mandatory', status:'mandatory'})
CREATE (prod:Product {product_id:'mandatory', name:'mandatory', price:'mandatory', description:'optional?'})
CREATE (s:Supplier   {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'})
CREATE (r:Region     {region_id:'mandatory', name:'mandatory'})

// ---------- Relationships -------------
MERGE (cust)-[:PLACES_ORDER {channel:'optional?'}]->(o)
MERGE (o)-[:HAS_LINE_ITEM {quantity:'mandatory'}]->(prod)
MERGE (s)-[:SUPLIES]->(prod) // Regression 2: typo
MERGE (s)-[:PARTNERS_WITH]->(s)
MERGE (prod)-[:FREQUENTLY_BOUGHT_WITH]->(prod)
MERGE (cust)-[:LIVES_IN]->(r)
MERGE (cust)-[:LOCATED_IN]->(r)
MERGE (prod)-[:MADE_IN]->(r)
