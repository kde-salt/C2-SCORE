// --------- Nodes ------------
CREATE (cust:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', type: 'mandatory'}) // type=(Person|Company)
CREATE (o:Order      {order_id:'mandatory',    order_date:'mandatory', status:'mandatory'})
CREATE (p:Product    {product_id:'mandatory',  name:'mandatory', price:'mandatory'})
CREATE (s:Supplier   {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'})

// ---------- Relationships -------------
MERGE (cust)-[:PLACES_ORDER]->(o)
MERGE (o)-[:HAS_LINE_ITEM]->(p)
MERGE (s)-[:SUPPLIES]->(p)
MERGE (s)-[:PARTNERS_WITH]->(s)
MERGE (p)-[:FREQUENTLY_BOUGHT_WITH]->(p)
