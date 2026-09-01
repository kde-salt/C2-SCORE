// Q4-2 reduced instance: 17 nodes / 20 edges (the full Instance.cypher has
// 50 / 92). Used for the follow-up user study, whose questionnaire is a single
// Markdown/PDF: the full instance figure is too dense to read on paper.
//
// It preserves the *complete type set* of Instance.cypher, which is what the
// C2 evaluation collapses an instance to
// (experiment/common/utils.py::_get_all_node_and_edge_types_from_instance):
//   node types  Customer{customer_id, email, name, type; phone?}
//               / Order{order_id, order_date, status}
//               / Product{product_id, name, price; description?}
//               / Region{region_id, name} / Supplier{supplier_id, name, rating}
//   edge types  Customer-LIVES_IN->Region, Customer-LOCATED_IN->Region,
//               Customer-PLACES_ORDER{channel?}->Order,
//               Order-HAS_LINE_ITEM{quantity}->Product,
//               Product-FREQUENTLY_BOUGHT_WITH->Product, Product-MADE_IN->Region,
//               Supplier-PARTNERS_WITH->Supplier, Supplier-SUPPLIES->Product
// Customer.phone, Product.description and PLACES_ORDER.channel each need a
// present/absent pair to stay optional.
//
// Distribution: Customer 3 without phone / 1 with, Product 4 without
// description / 2 with, 3 Orders, 2 Regions, 2 Suppliers. Those splits are what
// make gmmschema keep Customer and Product as two node types each; when it
// merges them into one type with an optional property the per-edge endpoint
// signatures stop matching and its edge types disappear.
//
// Verify with:
//   python -m experiment.task4.verify_mini \
//       --cypher user_study/questions/q4-2/Instance-mini.cypher \
//       --db q4-2-mini --baseline q4-2 --gt user_study/questions/q4-2/B.cypher

// === Region (2) ===
CREATE (r1:Region {region_id:'R1', name:'Kanto'})
CREATE (r2:Region {region_id:'R2', name:'Kansai'})

// === Supplier (2) ===
CREATE (s1:Supplier {supplier_id:'S1', name:'Alpha Supply', rating:5})
CREATE (s2:Supplier {supplier_id:'S2', name:'Beta Traders', rating:4})

// === Product (6): two with description, four without ===
CREATE (p1:Product {product_id:'P1', name:'Smartphone A', price:699, description:'Entry smartphone'})
CREATE (p3:Product {product_id:'P3', name:'Phone Case X', price:19, description:'Soft case'})
CREATE (p2:Product {product_id:'P2', name:'Smartphone B', price:899})
CREATE (p4:Product {product_id:'P4', name:'Wireless Charger', price:39})
CREATE (p6:Product {product_id:'P6', name:'Drip Coffee Set', price:45})
CREATE (p10:Product {product_id:'P10', name:'Screen Protector', price:12})

// === Customer (4): one with phone, three without ===
CREATE (cuc1:Customer {customer_id:'CUC1', name:'Acorn LLC', email:'contact@acorn.example', type:'Company', phone:'+1-202-555-0101'})
CREATE (cuc2:Customer {customer_id:'CUC2', name:'Bright Co.', email:'hello@bright.example', type:'Company'})
CREATE (cuc4:Customer {customer_id:'CUC4', name:'Delta Group', email:'info@delta.example', type:'Company'})
CREATE (cup2:Customer {customer_id:'CUP2', name:'Bob Smith', email:'bob@example.com', type:'Person'})

// === Order (3) ===
CREATE (o1:Order {order_id:'O1', order_date:'2025-06-03', status:'shipped'})
CREATE (o2:Order {order_id:'O2', order_date:'2025-06-05', status:'pending'})
CREATE (o3:Order {order_id:'O3', order_date:'2025-06-08', status:'canceled'})

// === Customer -> Region (4) ===
CREATE (cuc1)-[:LOCATED_IN]->(r1)
CREATE (cuc2)-[:LOCATED_IN]->(r2)
CREATE (cuc4)-[:LOCATED_IN]->(r1)
CREATE (cup2)-[:LIVES_IN]->(r2)

// === PLACES_ORDER (3): with and without `channel` ===
CREATE (cuc1)-[:PLACES_ORDER {channel:'web'}]->(o1)
CREATE (cup2)-[:PLACES_ORDER]->(o2)
CREATE (cuc2)-[:PLACES_ORDER {channel:'phone'}]->(o3)

// === HAS_LINE_ITEM (4) ===
CREATE (o1)-[:HAS_LINE_ITEM {quantity:1}]->(p1)
CREATE (o1)-[:HAS_LINE_ITEM {quantity:2}]->(p3)
CREATE (o2)-[:HAS_LINE_ITEM {quantity:1}]->(p2)
CREATE (o3)-[:HAS_LINE_ITEM {quantity:1}]->(p4)

// === Product relations (5) ===
CREATE (p1)-[:FREQUENTLY_BOUGHT_WITH]->(p3)
CREATE (p2)-[:FREQUENTLY_BOUGHT_WITH]->(p4)
CREATE (p1)-[:MADE_IN]->(r1)
CREATE (p2)-[:MADE_IN]->(r2)
CREATE (p6)-[:MADE_IN]->(r1)

// === Supplier relations (4) ===
CREATE (s1)-[:PARTNERS_WITH]->(s2)
CREATE (s1)-[:SUPPLIES]->(p1)
CREATE (s2)-[:SUPPLIES]->(p2)
CREATE (s1)-[:SUPPLIES]->(p10)
