# Cypherクエリ チートシート

## 全ノード・エッジ
```cypher
MATCH (n)
OPTIONAL MATCH (n)-[r]->(m)
RETURN n, r, m
```

## 全ノード
```cypher
MATCH (n) RETURN n;
```

## 全エッジ
```cypher
MATCH p=()-[]->() RETURN p;
```

## Personラベルを持つノード
```cypher
MATCH (n:Person) RETURN n;
```

## Personラベルのみを持つノード
```cypher
MATCH (n:Person) WHERE size(labels(n)) = 1 RETURN n;
```

## FOLLOWSラベルを持つエッジ
```cypher
MATCH ()-[r:FOLLOWS]->() RETURN r;
```

## Personの必須/任意プロパティ
```cypher
MATCH (n:Person)
WITH count(n) AS total
MATCH (n:Person)
UNWIND keys(n) AS prop
WITH prop, total, count(*) AS freq
RETURN prop, (freq = total) AS is_mandatory
ORDER BY is_mandatory DESC, prop;
```

## FOLLOWSの必須/任意プロパティ
```cypher
MATCH ()-[r:FOLLOWS]->()
WITH count(r) AS total
MATCH ()-[r:FOLLOWS]->()
UNWIND keys(r) AS prop
WITH prop, total, count(*) AS freq
RETURN prop, (freq = total) AS is_mandatory
ORDER BY is_mandatory DESC, prop;
```

## nameプロパティを持つノード
```cypher
MATCH (n) WHERE n.name IS NOT NULL RETURN n;
```

## 特定のnameを持つノード
```cypher
MATCH (n) WHERE n.name = "Alice" RETURN n;
```

## timestampプロパティを持つエッジ
```cypher
MATCH ()-[r]->() WHERE r.timestamp IS NOT NULL RETURN r;
```

## 特定のtimestampを持つエッジ
```cypher
MATCH ()-[r]->() WHERE r.timestamp = "2025-10-14 20:35" RETURN r;
```

## Person→Postのエッジ
```cypher
MATCH (src:Person)-[r]->(dst:Post) RETURN src, r, dst;
```

## FOLLOWSの端点ノード
```cypher
MATCH (src)-[:FOLLOWS]->(dst) RETURN src, dst;
```

## FOLLOWS始点ラベル一覧
```cypher
MATCH (src)-[:FOLLOWS]->() RETURN DISTINCT labels(src) AS src_labels;
```

## Aliceがフォローしている人の投稿取得
```cypher
// 「Aliceがフォローしている人」が作成した投稿を取得する
MATCH (a:Person)-[:FOLLOWS]->(:Person)-[:CREATES]->(p:Post)
WHERE a.name = "Alice"
RETURN p;
```
