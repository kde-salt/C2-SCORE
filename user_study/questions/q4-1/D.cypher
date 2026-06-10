// --------- Nodes ------------
CREATE (cust:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', type:'mandatory'}) // type=(Person|Company)
CREATE (o:Order      {order_id:'mandatory',    order_date:'mandatory', status:'mandatory'})
CREATE (p:Product    {product_id:'mandatory',  name:'mandatory', price:'mandatory'})
CREATE (s:Supplier   {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'})
CREATE (s2:Supplier  {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'}) // Regression: duplicated Supplier node type for self-loop expansion

// ---------- Relationships -------------
MERGE (cust)-[:PLACES_ORDER]->(o)
MERGE (o)-[:HAS_LINE_ITEM]->(p)
MERGE (s)-[:SUPPLIES]->(p)
MERGE (s2)-[:SUPPLIES]->(p)
MERGE (s)-[:PARTNERS_WITH]->(s2)  // Regression 1: expand PARTNERS_WITH self-loop into (x)->(y)
MERGE (s2)-[:PARTNERS_WITH]->(s)  // Regression 1: expand PARTNERS_WITH self-loop into (y)->(x)
MERGE (p)-[:FREQUENTLY_BOUGHT_WITH]->(p)
