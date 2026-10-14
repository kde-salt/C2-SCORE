import org.apache.spark.sql.Column
import org.apache.spark.sql.functions.col

/** Property keys can be IRIs (dblp / dbpedia) containing '.', ':', '/'.
  * Spark's col("a.b") parses the dot as struct-field access, so any column
  * reference built from a property key must be backquoted. */
object ColName {
  def qcol(name: String): Column = col("`" + name.replace("`", "``") + "`")

  /** Split a "propertyName:Type" entry at the LAST colon: IRI property
    * names contain ':' themselves, so a plain split(":") shreds them
    * (and the exporters then silently dropped every IRI property).
    * Returns None when the entry has no colon at all. */
  def splitPropType(entry: String): Option[(String, String)] = {
    val i = entry.lastIndexOf(':')
    if (i < 0) None else Some((entry.substring(0, i), entry.substring(i + 1)))
  }
}
