import Dependencies._

ThisBuild / scalaVersion     := "2.12.17"
ThisBuild / version          := "0.1.0-SNAPSHOT"
ThisBuild / organization     := "com.example"
ThisBuild / organizationName := "example"

// Uncomment and modify if needed for Windows
// ThisBuild / javaHome := Some(file("C:\\Program Files\\Java\\jdk-11.0.17"))

lazy val root = (project in file("."))
  .settings(
    name := "schemadiscovery",

    libraryDependencies ++= Seq(
      munit % Test,                  // Unit testing
      sparkCore,                      // Spark Core
      sparkSql,                       // Spark SQL
      sparkMllib,                     // Spark MLlib
      "org.apache.spark" %% "spark-hive" % sparkVer,
      "org.neo4j.driver" % "neo4j-java-driver" % "4.4.10",
      "org.neo4j" % "neo4j-connector-apache-spark_2.12" % "4.1.4", // Consider updating to 4.1.6
      "org.scala-lang" % "scala-library" % scalaVer
    ),

    // Add Neo4j Maven repository to resolve the connector
    resolvers += Resolver.mavenCentral,


    // Ensure the application forks when running to use the Java options.
    // Heap defaults to 10G; override with the PGHIVE_XMX env var for
    // large-graph feasibility runs (Task 1).
    //
    // The code cache is raised for the same reason the heap is.  Spark emits a
    // whole-stage-codegen class per property query, and InferTypes issues two
    // per property, so a schema with ~10k property keys exhausts JDK 11's
    // 240 MB default: dbpedia-dm2 (10,024 keys) logged "CodeHeap 'non-profiled
    // nmethods' is full. Compiler has been disabled." at 2,630 s and then ran
    // interpreted at 0.67 properties/min, while dbpedia-ds (4,470 keys) never
    // filled it and finished 4,470 in ~52 min.  This is a resource setting, not
    // a change to the method -- upstream likewise ships only -Xmx10G.
    Compile / run / fork := true,
    Compile / run / javaOptions ++= Seq(
        "-Xmx" + sys.env.getOrElse("PGHIVE_XMX", "10G"),
        "-XX:ReservedCodeCacheSize=" + sys.env.getOrElse("PGHIVE_CODECACHE", "1G"),
        // Forwarded as system properties so they survive the fork regardless of
        // how the environment is passed down; InferTypes reads either form.
        "-Dpghive.fastTypeInfer=" + sys.env.getOrElse("PGHIVE_FAST_TYPEINFER", ""),
        "-Dpghive.typeInferChunk=" + sys.env.getOrElse("PGHIVE_TYPEINFER_CHUNK", ""),
        "-Dpghive.leanLoad=" + sys.env.getOrElse("PGHIVE_LEAN_LOAD", ""),
        "-Dspark.executor.memory=10G",
        "-Dspark.driver.memory=10G",
        "-Dspark.driver.cores=3",
        "-Dspark.driver.maxResultSize=4G"
    )

  )

import sbtassembly.AssemblyPlugin.autoImport._

assemblyMergeStrategy in assembly := {
  case PathList("META-INF", xs @ _*) => MergeStrategy.discard
  case x => MergeStrategy.first
}