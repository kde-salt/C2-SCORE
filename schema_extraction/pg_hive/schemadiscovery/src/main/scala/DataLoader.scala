import org.apache.spark.sql.{DataFrame, Row, SparkSession}
import org.apache.spark.sql.types._
import org.apache.hadoop.fs.{FileSystem, Path}
import org.neo4j.driver.{AuthTokens, GraphDatabase, SessionConfig}
import scala.collection.JavaConverters._
import scala.collection.mutable.ArrayBuffer


object DataLoader {
  // --- lean load -----------------------------------------------------------
  // The full-graph loaders below build one DataFrame row per node/edge, with
  // one column per distinct property key. Materialising those rows eagerly as
  // dense Array[Any]s on the driver is what dominated the heap on the DBpedia
  // variants: dbpedia-ds (726,269 nodes x 4,473 columns) costs ~26 GB in row
  // arrays alone -- exactly the ~4 GB per 100k rows the load-nodes progress
  // lines report -- and the ParallelCollectionRDD keeps them referenced (plus
  // its partition slices) for the entire run, for a 96.9 GB peak RSS. Almost
  // every cell is null: the same DB has only 4.5M non-null cells out of 3.2
  // billion slots.
  //
  // The lean path stores each record sparsely (positions of the present
  // fields + their values) and builds the dense Row lazily inside an
  // RDD.map, so a dense row only exists transiently per partition while a
  // Spark job streams over it. The DataFrame contents are identical: the
  // same values end up at the same schema positions, missing fields are
  // null either way, and later writes win on a (pathological) clash between
  // a property key and a synthetic column exactly like the Map `+` did.
  // Row order, partitioning (same default numSlices) and the schema are
  // unchanged, so this removes engineering overhead only.
  // Set PGHIVE_LEAN_LOAD=0 to fall back to the eager dense path.
  private def tunable(prop: String, env: String): Option[String] =
    sys.props.get(prop).filter(_.nonEmpty)
      .orElse(sys.env.get(env).filter(_.nonEmpty))

  private val leanLoad: Boolean =
    tunable("pghive.leanLoad", "PGHIVE_LEAN_LOAD").getOrElse("1") != "0"

  /** One record in sparse form: positions into the schema's field array that
    * are present, and their values (parallel arrays). */
  private final case class SparseRec(idx: Array[Int], vals: Array[Any])

  /** Lazily densify sparse records into Rows; the closure captures only the
    * field count, never a DataFrame or the record buffer. */
  private def sparseRowRDD(spark: SparkSession, recs: Seq[SparseRec],
                           numFields: Int) = {
    val nf = numFields
    spark.sparkContext.parallelize(recs).map { r =>
      val arr = new Array[Any](nf)
      var i = 0
      while (i < r.idx.length) { arr(r.idx(i)) = r.vals(i); i += 1 }
      Row.fromSeq(arr)
    }
  }
  // -------------------------------------------------------------------------

  def loadNodesBatch(spark: SparkSession, batchSize: Int, offset: Long, dbName: String = "neo4j"): DataFrame = {
    import spark.implicits._
    val uri = sys.env.getOrElse("NEO4J_URI", "bolt://localhost:7687")
    val user = sys.env.getOrElse("NEO4J_USER", "neo4j")
    val password = sys.env.getOrElse("NEO4J_PASSWORD", "password")

    val driver = GraphDatabase.driver(uri, AuthTokens.basic(user, password))
    val session = driver.session(SessionConfig.forDatabase(dbName))

    println(s"Loading batch of nodes (offset: $offset, batchSize: $batchSize) from Neo4j")

    val query = s"""
      MATCH (n)
      WITH n, labels(n) AS labels
      ORDER by id(n)
      SKIP $offset
      LIMIT $batchSize
      RETURN n, labels
    """
    val result = session.run(query)
    val nodes = result.list().asScala.map { record =>
      val node = record.get("n").asNode()
      val labels = record.get("labels").asList().asScala.map(_.toString)
      val props = node.asMap().asScala.toMap.map { case (key, value) =>
        val strValue = value match {
          case list: java.util.List[_] => list.asScala.mkString(",")
          case other => other.toString
        }
        key -> strValue
      }
      props + ("_nodeId" -> node.id()) + ("_labels" -> labels.mkString(":")) + ("originalLabels" -> labels)
    }

    session.close()
    driver.close()

    val allKeys = nodes.flatMap(_.keys).toSet
    val fields = allKeys.map {
      case "_nodeId" => StructField("_nodeId", LongType, nullable = false)
      case "originalLabels" => StructField("originalLabels", ArrayType(StringType), nullable = true)
      case key => StructField(key, StringType, nullable = true)
    }.toArray
    val schema = StructType(fields.toSeq)

    val rows = nodes.map { nodeMap =>
      Row(schema.fields.map(f => Option(nodeMap.getOrElse(f.name, null)).orNull): _*)
    }

    val nodesDF = spark.createDataFrame(spark.sparkContext.parallelize(rows.toSeq), schema)
    println(s"Loaded ${nodesDF.count()} nodes in batch")
    nodesDF
  }

  def loadRelationshipsBatch(spark: SparkSession, batchSize: Int, offset: Long, dbName: String = "neo4j"): DataFrame = {
    import spark.implicits._
    val uri = sys.env.getOrElse("NEO4J_URI", "bolt://localhost:7687")
    val user = sys.env.getOrElse("NEO4J_USER", "neo4j")
    val password = sys.env.getOrElse("NEO4J_PASSWORD", "password")

    val driver = GraphDatabase.driver(uri, AuthTokens.basic(user, password))
    val session = driver.session(SessionConfig.forDatabase(dbName))

    println(s"Loading batch of relationships (offset: $offset, batchSize: $batchSize) from Neo4j")

    val query = s"""
      MATCH (n)-[r]->(m)
      WITH n, r, m
      ORDER BY id(r)
      SKIP $offset
      LIMIT $batchSize
      RETURN id(n) AS srcId, labels(n) AS srcType,
             id(m) AS dstId, labels(m) AS dstType,
             type(r) AS relationshipType, properties(r) AS properties
    """
    val result = session.run(query)
    val relationships = result.list().asScala.map { record =>
      val srcId = record.get("srcId").asLong()
      val dstId = record.get("dstId").asLong()
      val srcType = record.get("srcType").asList().asScala.mkString(":")
      val dstType = record.get("dstType").asList().asScala.mkString(":")
      val relationshipType = record.get("relationshipType").asString()
      val properties = record.get("properties").asMap().asScala.toMap.mapValues(_.toString)
      properties + ("srcId" -> srcId, "dstId" -> dstId, "relationshipType" -> relationshipType, "srcType" -> srcType, "dstType" -> dstType)
    }

    session.close()
    driver.close()

    val allKeys = relationships.flatMap(_.keys).toSet
    val fields = allKeys.map {
      case key @ ("srcId" | "dstId") => StructField(key, LongType, nullable = false)
      case key => StructField(key, StringType, nullable = true)
    }.toArray
    val schema = StructType(fields.toSeq)

    val rows = relationships.map { relMap =>
      Row(schema.fields.map(f => Option(relMap.getOrElse(f.name, null)).orNull): _*)
    }

    val relationshipsDF = spark.createDataFrame(spark.sparkContext.parallelize(rows.toSeq), schema)
    println(s"Loaded ${relationshipsDF.count()} relationships in batch")
    relationshipsDF
  }

  def fileExists(spark: SparkSession, path: String): Boolean = {
    val fs = FileSystem.get(spark.sparkContext.hadoopConfiguration)
    fs.exists(new Path(path))
  }

  def loadAllNodes(spark: SparkSession, dbName: String = "neo4j"): DataFrame = {
    import spark.implicits._
    val uri = sys.env.getOrElse("NEO4J_URI", "bolt://localhost:7687")
    val user = sys.env.getOrElse("NEO4J_USER", "neo4j")
    val password = sys.env.getOrElse("NEO4J_PASSWORD", "password")

    val driver = GraphDatabase.driver(uri, AuthTokens.basic(user, password))
    val session = driver.session(SessionConfig.forDatabase(dbName))

    println("Loading all nodes from Neo4j")
    println(s"[lean-load] ${if (leanLoad) "sparse (lazy-densified) rows" else "eager dense rows"}")

    // Pass 1: the property keys, aggregated server-side.
    // The column list has to be known before rows can be built. Deriving it by
    // buffering every node's Map and taking the union is what exhausted an 80GB
    // heap on dblp (10.6M nodes): the Maps alone reached 54GB, and the Row copy
    // built from them on top of that pushed the driver over the limit. The key
    // set is identical either way — it is the union of keys(n) over all nodes,
    // plus the three synthetic columns added per node below.
    val keyResult = session.run("MATCH (n) UNWIND keys(n) AS k RETURN DISTINCT k")
    val propKeys = ArrayBuffer[String]()
    while (keyResult.hasNext) propKeys += keyResult.next().get("k").asString()

    val allKeys = (propKeys ++ Seq("_nodeId", "_labels", "originalLabels")).toSet
    val fields = allKeys.map {
      case "_nodeId" => StructField("_nodeId", LongType, nullable = false)
      case  "originalLabels" => StructField("originalLabels", ArrayType(StringType), nullable = true)
      case key => StructField(key, StringType, nullable = true)
    }.toArray
    val schema = StructType(fields.toSeq)

    // Pass 2: stream the nodes off the wire. The per-node Map is short-lived
    // either way; what stays on the heap for the whole run is, on the lean
    // path, only the sparse (positions, values) pairs instead of a dense
    // Array[Any] per node (see the lean-load note at the top of this object).
    val fieldPos: Map[String, Int] = schema.fieldNames.zipWithIndex.toMap
    val result = session.run("MATCH (n) WITH n, rand() AS random RETURN n, labels(n) AS labels ORDER BY random")
    val rows = ArrayBuffer[Row]()
    val recs = ArrayBuffer[SparseRec]()
    var progressCount = 0L
    val progressStart = System.currentTimeMillis
    while (result.hasNext) {
      val record = result.next()
      val node = record.get("n").asNode()
      val labels = record.get("labels").asList().asScala.map(_.toString)
      val props = node.asMap().asScala.toMap.map { case (key, value) =>
        val strValue = value match {
          case list: java.util.List[_] =>
            list.asScala.mkString(",")
          case other =>
            other.toString
        }
        key -> strValue
      }

      if (leanLoad) {
        // Same entries as nodeMap below, props first so the three synthetic
        // fields overwrite them on a name clash, as Map `+` does.
        val idx = new Array[Int](props.size + 3)
        val vals = new Array[Any](props.size + 3)
        var i = 0
        props.foreach { case (k, v) => idx(i) = fieldPos(k); vals(i) = v; i += 1 }
        idx(i) = fieldPos("_nodeId"); vals(i) = node.id(); i += 1
        idx(i) = fieldPos("_labels"); vals(i) = labels.mkString(":"); i += 1
        idx(i) = fieldPos("originalLabels"); vals(i) = labels
        recs += SparseRec(idx, vals)
      } else {
        val nodeMap: Map[String, Any] =
          props + ("_nodeId" -> node.id()) + ("_labels" -> labels.mkString(":")) + ("originalLabels" -> labels)
        rows += Row(schema.fields.map(f => Option(nodeMap.getOrElse(f.name, null)).orNull): _*)
      }
      progressCount += 1
      if (progressCount % 100000 == 0) {
        val elapsed = (System.currentTimeMillis - progressStart) / 1000.0
        val heapGb = (Runtime.getRuntime.totalMemory - Runtime.getRuntime.freeMemory) / 1e9
        println(f"[progress] ${java.time.LocalTime.now().withNano(0)} pghive:load-nodes: $progressCount%,d rows rate=${progressCount / elapsed}%,.0f/s heap=$heapGb%.1fGB elapsed=$elapsed%.0fs")
      }
    }

    session.close()
    driver.close()

    val nodesDF =
      if (leanLoad) spark.createDataFrame(sparseRowRDD(spark, recs, schema.fields.length), schema)
      else spark.createDataFrame(spark.sparkContext.parallelize(rows.toSeq), schema)
    println(s"Total nodes loaded: ${nodesDF.count()}")
    nodesDF
  }

  def loadAllRelationships(spark: SparkSession, dbName: String = "neo4j"): DataFrame = {
    import spark.implicits._
    val uri = sys.env.getOrElse("NEO4J_URI", "bolt://localhost:7687")
    val user = sys.env.getOrElse("NEO4J_USER", "neo4j")
    val password = sys.env.getOrElse("NEO4J_PASSWORD", "password")

    val driver = GraphDatabase.driver(uri, AuthTokens.basic(user, password))
    val session = driver.session(SessionConfig.forDatabase(dbName))
    println("Loading all relationships from Neo4j")

    // Pass 1: the edge property keys, aggregated server-side (see loadAllNodes
    // for why the column list is no longer derived from a buffer of Maps).
    val keyResult = session.run("MATCH ()-[r]->() UNWIND keys(r) AS k RETURN DISTINCT k")
    val propKeys = ArrayBuffer[String]()
    while (keyResult.hasNext) propKeys += keyResult.next().get("k").asString()

    val allKeys = (propKeys ++ Seq("srcId", "dstId", "relationshipType",
                                   "srcType", "dstType")).toSet
    val fields = allKeys.map {
      case key @ ("srcId" | "dstId") => StructField(key, LongType, nullable = false)
      case key => StructField(key, StringType, nullable = true)
    }.toArray
    val schema = StructType(fields.toSeq)

    // Pass 2: stream the relationships off the wire (sparse on the lean
    // path, see loadAllNodes).
    val fieldPos: Map[String, Int] = schema.fieldNames.zipWithIndex.toMap
    val result = session.run(
      """MATCH (n)-[r]->(m)
        |WITH n, r, m, rand() as random
        |RETURN id(n) AS srcId, labels(n) AS srcType,
        |       id(m) AS dstId, labels(m) AS dstType,
        |       type(r) AS relationshipType, properties(r) AS properties
        | ORDER BY random""".stripMargin
    )

    val rows = ArrayBuffer[Row]()
    val recs = ArrayBuffer[SparseRec]()
    var progressCount = 0L
    val progressStart = System.currentTimeMillis

    while (result.hasNext) {
      val record = result.next()

      val srcId = record.get("srcId").asLong()
      val dstId = record.get("dstId").asLong()
      val srcType = record.get("srcType").asList().asScala.mkString(":")
      val dstType = record.get("dstType").asList().asScala.mkString(":")
      val relationshipType = record.get("relationshipType").asString()
      val properties = record.get("properties").asMap().asScala.toMap.mapValues(_.toString)

      if (leanLoad) {
        // Props first, then the five synthetic fields, so the synthetics win
        // on a name clash exactly like the Map `+` below.
        val idx = new Array[Int](properties.size + 5)
        val vals = new Array[Any](properties.size + 5)
        var i = 0
        properties.foreach { case (k, v) => idx(i) = fieldPos(k); vals(i) = v; i += 1 }
        idx(i) = fieldPos("srcId"); vals(i) = srcId; i += 1
        idx(i) = fieldPos("dstId"); vals(i) = dstId; i += 1
        idx(i) = fieldPos("relationshipType"); vals(i) = relationshipType; i += 1
        idx(i) = fieldPos("srcType"); vals(i) = srcType; i += 1
        idx(i) = fieldPos("dstType"); vals(i) = dstType
        recs += SparseRec(idx, vals)
      } else {
        val relMap: Map[String, Any] =
          properties + ("srcId" -> srcId, "dstId" -> dstId,
                        "relationshipType" -> relationshipType,
                        "srcType" -> srcType, "dstType" -> dstType)
        rows += Row(schema.fields.map(f => Option(relMap.getOrElse(f.name, null)).orNull): _*)
      }
      progressCount += 1
      if (progressCount % 100000 == 0) {
        val elapsed = (System.currentTimeMillis - progressStart) / 1000.0
        val heapGb = (Runtime.getRuntime.totalMemory - Runtime.getRuntime.freeMemory) / 1e9
        println(f"[progress] ${java.time.LocalTime.now().withNano(0)} pghive:load-edges: $progressCount%,d rows rate=${progressCount / elapsed}%,.0f/s heap=$heapGb%.1fGB elapsed=$elapsed%.0fs")
      }
    }

    session.close()
    driver.close()

    val relationshipsDF =
      if (leanLoad) spark.createDataFrame(sparseRowRDD(spark, recs, schema.fields.length), schema)
      else spark.createDataFrame(spark.sparkContext.parallelize(rows.toSeq), schema)
    println(s"Total relationships loaded: ${relationshipsDF.count()}")
    relationshipsDF
  }
}
