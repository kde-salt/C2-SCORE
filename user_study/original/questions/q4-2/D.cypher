// --------- Nodes ------------
CREATE (cust:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', type:'mandatory', phone:'optional?'})
CREATE (o:Order      {order_id:'mandatory', order_date:'mandatory', status:'mandatory'})
CREATE (prod:Product {product_id:'mandatory', name:'mandatory', price:'mandatory', description:'optional?'})
CREATE (s:Supplier   {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'})
CREATE (r {region_id:'mandatory', name:'mandatory'}) // Regression 1: missing Region node label

// ---------- Relationships -------------
MERGE (cust)-[:PLACES_ORDER {channel:'optional?'}]->(o)
MERGE (o)-[:HAS_LINE_ITEM {quantity:'mandatory'}]->(prod)
MERGE (s)-[:SUPPLIES]->(prod)
MERGE (s)-[:PARTNERS_WITH]->(s)
MERGE (prod)-[:FREQUENTLY_BOUGHT_WITH]->(prod)
MERGE (prod)-[:LIVES_IN]->(r) // Regression 2: misconnected Customer->Region as Product->Region
MERGE (cust)-[:LOCATED_IN]->(r)
MERGE (prod)-[:MADE_IN]->(r)
