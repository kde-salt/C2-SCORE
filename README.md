# C2-SCORE Artifact

The artifact runs entirely in Docker: a Neo4j container holds the datasets, and
a Python container runs the experiments.

> **Reproducibility note.** The reported experiments were run natively on a
> 128 GB machine, not in Docker. Score values are unaffected; runtimes and
> extraction success under a resource budget depend on the Docker VM's size.

## 1. Setup

### 1.1. Requirements

* **Docker Engine 24+** with **Compose v2** (replace `docker compose` with
  `docker-compose` if you only have the standalone binary).
* **Disk:** ~100 GB free for the Docker VM (databases ~70 GB, images ~3 GB).
* **Memory:** at least 20 GB for the Docker VM with the default settings; the
  DBpedia-scale runs need more.
* **Neo4j Enterprise** is required. `docker-compose.yml` starts it under the
  free [Neo4j Evaluation Agreement](https://neo4j.com/terms/enterprise_us/).

### 1.2. Configure

```bash
cp .env.example .env
```

The defaults work as they are; every setting is documented in `.env.example`.
Check `NEO4J_HTTP_PORT` / `NEO4J_BOLT_PORT` if 7474 / 7687 are already in use,
and on Linux set `HOST_UID` / `HOST_GID` to your own account so that result
files stay yours.

### 1.3. Build and start

```bash
docker compose build
docker compose up -d neo4j
docker compose ps        # wait until the neo4j service reports "healthy"
```

`build` produces the Python image used by every experiment; the PG-HIVE image is
behind a profile and is only needed for Section 4.2. The Neo4j Browser is then
at http://localhost:7474 (user `neo4j`, password from `.env`).

### 1.4. Download the dump files

The dump files are not in this repository; download the archive from
[Google Drive](https://drive.google.com/file/d/19wQStWA7kFRZ6f0XmB1sLb-DcvNRhsk8/view?usp=sharing)
and extract all `.dump` files into `edbt_dumps/`, or point `DUMP_DIR` in `.env`
at the directory you extracted them into. Each `xx.dump` becomes a database named
`xx` (e.g. `mb6.dump` → `mb6`). The dumps were created with Neo4j 5.26.0, the
version the compose file pins.

### 1.5. Import the dumps

```bash
./docker/import-dumps.sh
```

This loads every dump and starts the resulting databases — a single step that
populates the databases for **all** experiments below. Re-running it is safe.

---

## 2. Running Experiments

* Run all commands from the repository root; it is mounted at `/workspace`, so
  results land in the repository on your host.
* `docker compose run` starts Neo4j and waits for it to become healthy.
* Running an entry point **without arguments reproduces the reported setting**;
  most accept `--help` (`--datasets`, `--methods`, `--trials`, `--runs`, …).
* For long runs (EQ4 and the extractions of Section 4.3), use
  `docker compose run -d --name <name> ...` and follow with `docker logs -f`.

Database naming: `<DATASET>` for the original instance, `<DATASET>-gt` for a
ground-truth schema, `<DATASET>-<METHOD>` for an extracted schema, where
`<METHOD>` ∈ {`lei`, `schemi`, `gmmschema`, `pg-hive`}.

### 2.1. Experiment 1 (EQ1): Sensitivity

**Schema-side perturbations** — injects errors into the ground-truth schemas of
ldbc, mb6, northwind, spotify, steam and tpc-h:

```bash
docker compose run --rm experiment python -m experiment.sensitivity_test.main
```

**Instance-side irregularities** — holds the schema fixed (SchemI's output on
full DBpedia) and perturbs the instance abstraction on k ∈ {1, 10, 100} nodes;
the second command prints the per-condition scores and deltas:

```bash
docker compose run --rm experiment python -m experiment.sensitivity_test.instance_irregularity \
    --instance dbpedia --schema dbpedia-schemi --k 1,10,100 --trials 3

docker compose run --rm experiment python -m experiment.sensitivity_test.summarize_irregularity \
    experiment/sensitivity_test/results/instance_irregularity_*.csv
```

Results: `experiment/sensitivity_test/results` (CSV).

### 2.2. Experiment 2 (EQ2): Diagnostic Usefulness

**Ten main datasets** — evaluates the schemas of the four methods (Lei, SchemI,
GMMSchema, PG-HIVE) against the original databases of findkg, ldbc, mb6,
network-management, northwind, spotify, steam, tpc-h, twitter and wordnet:

```bash
docker compose run --rm experiment python -m experiment.diagnostic_usefulness_test.main
```

Results: `experiment/diagnostic_usefulness_test/results` (CSV).

**Diagnostic breakdown** — per-type analyses (redundant types, coverage loss,
unobserved signatures):

```bash
docker compose run --rm experiment python -m experiment.diagnostic_usefulness_test.diagnose --instance spotify
docker compose run --rm experiment python -m experiment.diagnostic_usefulness_test.diagnose_g1
docker compose run --rm experiment python -m experiment.diagnostic_usefulness_test.diagnose_g3_extra --instance steam
```

**Complex real-world PGs** — the four methods on `dblp` and on DBpedia at four
sizes (`dbpedia-ds`, `dbpedia-dm2`, `dbpedia-dl2`, `dbpedia`), one instance per
run:

```bash
docker compose run --rm experiment python -m experiment.complex_pgs_test.eval_c2 --instance dblp
docker compose run --rm experiment python -m experiment.complex_pgs_test.eval_c2 --instance dbpedia-ds
```

Results are appended to `experiment/complex_pgs_test/results/c2_scores.csv`.

Method × instance combinations without a schema database are reported failures:
their extraction exceeded the common resource budget (Section 4.3). Dataset
statistics: `python -m experiment.complex_pgs_test.stats --db dblp --estimate-signatures`.

### 2.3. Experiment 3 (EQ3): Normalization Consistency

Checks that C2 distinguishes matched from mismatched instance–schema pairs under
graph normalization, on `dbpedia` / `dbpedia-2gnf` and on the small curated
`suni1` / `suni1-norm` pair (create the latter with
`python -m experiment.normalization_test.load_suni1`, then extract its SchemI
schemas as in Section 4). Score the four combinations of each pair:

```bash
# matched
docker compose run --rm experiment python -m experiment.complex_pgs_test.eval_c2 --instance dbpedia --methods schemi
docker compose run --rm experiment python -m experiment.complex_pgs_test.eval_c2 --instance dbpedia-2gnf --methods schemi

# cross
docker compose run --rm experiment python -m experiment.normalization_test.eval_crosspair --instance dbpedia --schema dbpedia-2gnf-schemi
docker compose run --rm experiment python -m experiment.normalization_test.eval_crosspair --instance dbpedia-2gnf --schema dbpedia-schemi
```

(and analogously for `suni1` / `suni1-norm`). Cross-pair results are appended to
`experiment/normalization_test/results/crosspair_c2.csv`.

The scripts in `dataset_preparation/` originally built `dblp` / `dbpedia` /
`dbpedia-2gnf` from the external artifact of Egger et al.; not needed with the dumps.

### 2.4. Experiment 4 (EQ4): Scalability

Measures the runtime of the C2-score computation on LDBC at five scale factors
(`ldbc-sf0.1` … `ldbc-sf10`) plus the nine other EQ2 datasets, each against its
SchemI schema, 10 repetitions per instance with a per-phase breakdown.

```bash
docker compose run --rm experiment python -m experiment.scalability_test.main
```

Results: `experiment/scalability_test/results` (CSV). Under the default
`NEO4J_PAGECACHE=8G` — smaller than the largest stores — absolute times are
substantially slower and I/O-bound; the trend across scale factors remains visible.

## 3. User Study

Materials live in `user_study`, split into the original study and the follow-up
study. **Participant responses are not published**, for both studies, to protect
participants' personal information; the aggregated outcomes are reported in the
paper. The analysis scripts below are included to document how the responses
were analysed — with no input data shipped, they cannot be re-run as they are.

* [`user_study/original/questions/`](user_study/original/questions/) — 12
  scenarios (`q1-1` … `q4-3`), each with a PG instance (`Instance.cypher`) and
  four anonymized schemas (`A.cypher`–`D.cypher`); three also contain the
  reduced `Instance-mini.cypher` used in the follow-up study.
* [`user_study/original/en/`](user_study/original/en/) /
  [`user_study/original/ja/`](user_study/original/ja/) — participant
  instructions and Cypher cheat sheets.
* [`user_study/original/scripts/`](user_study/original/scripts/) — Borda-count
  golden ranking (`create_golden.py`) and Kendall's W (`kendall.py`).
* [`user_study/followup/`](user_study/followup/) — the questionnaire, its
  figures, and `scripts/followup_analysis.py` (anonymization, Borda consensus,
  Kendall's tau against the C2 ranking).

## 4. (Optional) Schema Extraction

`schema_extraction/` contains the four methods (Lei, SchemI, GMMSchema: Python;
PG-HIVE: Scala/Spark). The extracted schemas are already distributed as dumps
(Section 1.4), so running this code is **not required**.

GMMSchema and PG-HIVE are taken from their authors' repositories
([pg-schemainference](https://github.com/naussicaa/pg-schemainference) and
[PG-HIVE](https://github.com/sophisid/PG-HIVE)) and carry some modifications of
ours, mostly to make them run on the larger datasets; the modified paths are
on by default and can be turned off with the environment variables named in
the comments next to them. Lei and SchemI are our own implementations.

### 4.1. Running the Four Methods

```bash
docker compose run --rm experiment python -m schema_extraction.main
```

Target databases and methods are set by the constants at the top of
`schema_extraction/main.py`; the repository is bind-mounted, so editing the file
on the host is enough. Setting `PG_HIVE_EXTRACT = True` needs the PG-HIVE image:

```bash
docker compose --profile pghive build
docker compose --profile pghive run --rm --name c2score-pghive pghive python -m schema_extraction.main
```

If you rebuild that image later, drop its cached build volumes so the new build
is picked up: `docker volume rm c2score_pghive-target c2score_pghive-project-target`.

### 4.2. PG-HIVE Details

PG-HIVE runs in two steps: a heavy Spark **extraction** producing a schema txt
file, and a pure-Python **commit** writing it to `<DATASET>-pg-hive`. By default
only the commit runs, reusing the txt files archived in
`schema_extraction/pg_hive/results/`. To re-run the extraction itself:

```bash
docker compose --profile pghive run --rm --name c2score-pghive pghive \
    python -m schema_extraction.pg_hive.pg_hive <DB_NAME> --extract
```

* **Never run two PG-HIVE extractions concurrently** — they share the sbt build
  output and fixed output paths. Keeping `--name c2score-pghive` enforces this.
* The extraction **overwrites the tracked txt** for that dataset and is **not
  deterministic** (node sampling drives the LSH parameters). Restore the
  evaluated schemas with `git checkout -- schema_extraction/pg_hive/results/`.

### 4.3. Supervised Extraction Runner

Runs one method on one database under a wall-clock timeout and memory
supervision, as the large-dataset extractions were executed:

```bash
docker compose run --rm experiment python -m schema_extraction.run_extraction \
    --db dblp --method lei --timeout 21600 --mem-limit-gb 100

docker compose --profile pghive run --rm --name c2score-pghive pghive \
    python -m schema_extraction.run_extraction \
    --db dblp --method pg-hive --timeout 21600 --mem-limit-gb 100
```

The reported extractions used `PGHIVE_XMX=80G` and `--mem-limit-gb 100`; under
smaller budgets, success/failure outcomes are not comparable. Keep the Docker
VM's memory above `--mem-limit-gb` so the runner, not the kernel, terminates the
child. Outcomes are appended to
`experiment/complex_pgs_test/results/extraction_runs.csv`, logs to
`schema_extraction/logs/`. A failure on a smaller rung of the nested DBpedia
ladder (`dbpedia-ds` ⊆ `dbpedia-dm2` ⊆ `dbpedia-dl2`) is recorded as an implied
failure on the larger rungs.
