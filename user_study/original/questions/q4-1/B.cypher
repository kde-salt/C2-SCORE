// --------- Nodes ------------
CREATE (cust:Customer {customer_id:'mandatory', name:'mandatory', email:'mandatory', type:'mandatory'}) // type=(Person|Company)
CREATE (o:Order      {order_id:'mandatory',    order_date:'mandatory', status:'mandatory'})
CREATE (p:Product    {product_id:'mandatory',  name:'mandatory', price:'mandatory'})
CREATE (s {supplier_id:'mandatory', name:'mandatory', rating:'mandatory'}) // Regression 1: missing Supplier node label

// ---------- Relationships -------------
MERGE (o)-[:PLACES_ORDER]->(cust) // Regression 3: reversed PLACES_ORDER direction
MERGE (o)-[:HAS_LINE_ITEM]->(p)
MERGE (s)-[:SUPPLIES]->(p)
MERGE (s)-[:PARTNERS_WITH]->(s)
MERGE (p)-[:FREQUENTLY_BOUGHT_WITH]->(p)
MERGE (cust)-[:INFLUENCED_BY_PROMO]->(p) // Regression 2: add an edge type not present in the data
