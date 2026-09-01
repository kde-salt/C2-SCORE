import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.functions._
import org.apache.spark.ml.feature.{Word2Vec, VectorAssembler}

object PatternPreprocessing {

  def encodePatterns(spark: SparkSession, patternsDF: DataFrame, allProperties: Set[String]): DataFrame = {
    import spark.implicits._

    val propertiesCols = allProperties.toArray

    // Binary presence columns are named by index (prop_0, prop_1, ...):
    // IRI property keys contain dots, which VectorAssembler cannot resolve
    // as column names. Order and values are unchanged, only the names.
    // One single select instead of a foldLeft/withColumn chain: with
    // hundreds of IRI keys the nested-Project plan made the analyzer hit
    // its 100-iteration cap at the later self-crossJoin.
    val binaryColExprs = propertiesCols.zipWithIndex.map { case (prop, i) =>
      when(ColName.qcol(prop).isNotNull, 1.0).otherwise(0.0).as(s"prop_$i")
    }
    val withBinaryColsDF = patternsDF.select(col("*") +: binaryColExprs.toSeq: _*)

    val withLabelArrayDF = withBinaryColsDF
      .withColumn("labelArray", array(coalesce($"_labels".cast("string"), lit(""))))

    val word2Vec = new Word2Vec()
      .setInputCol("labelArray")
      .setOutputCol("labelVector")
      .setVectorSize(5)
      .setMinCount(0)

    val w2vModel = word2Vec.fit(withLabelArrayDF)
    val withLabelVecDF = w2vModel.transform(withLabelArrayDF)

    val binaryCols = propertiesCols.indices.map(i => s"prop_$i").toArray
    val assembler = new VectorAssembler()
      .setInputCols(Array("labelVector") ++ binaryCols)
      .setOutputCol("features")
      .setHandleInvalid("skip")

    assembler.transform(withLabelVecDF)
  }

  def encodeEdgePatterns(spark: SparkSession, edgesDF: DataFrame, allProperties: Set[String]): DataFrame = {
    import spark.implicits._

    val propertiesCols = allProperties.toArray

    // Same index-based naming and single-select as encodePatterns.
    val binaryColExprs = propertiesCols.zipWithIndex.map { case (prop, i) =>
      when(ColName.qcol(prop).isNotNull, 1.0).otherwise(0.0).as(s"prop_$i")
    }
    val withBinaryColsDF = edgesDF.select(col("*") +: binaryColExprs.toSeq: _*)

    val withArraysDF = withBinaryColsDF
      .withColumn("relationshipTypeArray", array(coalesce($"relationshipType".cast("string"), lit(""))))
      .withColumn("srcLabelArray", array(coalesce($"srcType".cast("string"), lit(""))))
      .withColumn("dstLabelArray", array(coalesce($"dstType".cast("string"), lit(""))))

    val word2VecRel = new Word2Vec()
      .setInputCol("relationshipTypeArray")
      .setOutputCol("relVector")
      .setVectorSize(10)
      .setMinCount(0)
    val relModel = word2VecRel.fit(withArraysDF)
    val withRelVec = relModel.transform(withArraysDF)

    val word2VecSrc = new Word2Vec()
      .setInputCol("srcLabelArray")
      .setOutputCol("srcVector")
      .setVectorSize(4)
      .setMinCount(0)

    val srcModel = word2VecSrc.fit(withRelVec)
    val withSrcVec = srcModel.transform(withRelVec)

    val word2VecDst = new Word2Vec()
      .setInputCol("dstLabelArray")
      .setOutputCol("dstVector")
      .setVectorSize(4)
      .setMinCount(0)

    val dstModel = word2VecDst.fit(withSrcVec)
    val withDstVec = dstModel.transform(withSrcVec)

    val binaryCols = propertiesCols.indices.map(i => s"prop_$i").toArray
    val assembler = new VectorAssembler()
      .setInputCols(Array("relVector", "srcVector", "dstVector") ++ binaryCols)
      .setOutputCol("features")
      .setHandleInvalid("skip")

    assembler.transform(withDstVec)
  }
}