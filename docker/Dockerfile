# C2-SCORE artifact images.
#
# Two targets:
#   experiment  Python-only image; runs every entry point except the PG-HIVE
#               *extraction* step (the PG-HIVE commit step is pure Python and
#               works here).
#   pghive      experiment + JDK 11 + sbt, for `pg_hive ... --extract`.
#
# Kept free of BuildKit-only syntax so it also builds with the legacy builder.

# ---------------------------------------------------------------- experiment
FROM python:3.12.4-slim-bookworm AS experiment

# procps  : schema_extraction/run_extraction.py supervises the child's RSS with
#           `ps -o rss= -g <pgid>`; the slim image ships no ps.
# util-linux: flock, used by the pghive stage's entrypoint guard.
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash ca-certificates procps util-linux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# HOME is pinned to a world-writable directory instead of /root so the image
# still works when compose runs it as an arbitrary host uid (see `user:` in
# docker-compose.yml). pip, sbt and coursier all write here.
ENV HOME=/home/runner \
    PYTHONHASHSEED=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
RUN mkdir -p /home/runner /workspace && chmod 0777 /home/runner /workspace

WORKDIR /workspace
COPY . /workspace
CMD ["bash"]

# -------------------------------------------------------------------- pghive
FROM experiment AS pghive

# Scala 2.12 needs Java 11. Debian bookworm has no openjdk-11 package, so the
# JDK is copied from the official Temurin image (published for amd64 and arm64).
COPY --from=eclipse-temurin:11-jdk-jammy /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk \
    JAVA_11_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:/opt/sbt/bin:$PATH

# user.home: the JVM reads it from the passwd database rather than from $HOME,
#   so sbt, coursier and ivy would cache under /root -- unreadable once compose
#   runs the container as the host's uid. Pinning it keeps the caches resolved
#   at build time usable at run time.
# sbt.server.forcestart: sbt binds a "boot server" unix socket before loading
#   the build and, when that bind fails, waits for a console that a container
#   run does not have. Forcing the start skips that handshake; the build itself
#   is unaffected.
ENV SBT_OPTS="-Duser.home=/home/runner -Dsbt.server.forcestart=true"

# sbt 1.9.9, pinned to match schemadiscovery/project/build.properties.
# The launcher is a JVM program, so the tarball is architecture independent.
ADD https://github.com/sbt/sbt/releases/download/v1.9.9/sbt-1.9.9.tgz /tmp/sbt.tgz
RUN echo "c57cae60c2122ca1bba77184dfb4d0d25fc6c18805394ab36ab6208b0c0f262f  /tmp/sbt.tgz" \
        | sha256sum -c - \
    && tar -xzf /tmp/sbt.tgz -C /opt \
    && rm /tmp/sbt.tgz

# Resolve the Spark 3.4.1 dependency set (~500 MB) into the image so that a run
# needs no network. The build output itself is deliberately NOT baked in: sbt
# sets explicit mtimes under target/, which only the owner may do, and files
# baked as root would be unwritable once compose runs the container as the
# host's uid. Leaving target/ empty but world-writable lets the run user create
# and own everything inside it.
#
# target/ and project/target/ are named volumes at run time (see
# docker-compose.yml). Docker seeds them from these empty, 0777 directories,
# which keeps the repository bind mount from hiding them and keeps the host's
# macOS build output from mixing with the container's Linux one.
RUN cd /workspace/schema_extraction/pg_hive/schemadiscovery \
    && sbt -java-home "$JAVA_11_HOME" update \
    && rm -rf target project/target \
    && mkdir -p target project/target \
    && chmod -R a+rwX /home/runner /workspace/schema_extraction/pg_hive/schemadiscovery

# The entrypoint appends a passwd entry for the running uid (see the script);
# that needs /etc/passwd to be writable by whichever uid compose picks.
RUN chmod 0666 /etc/passwd

COPY docker/pghive-entrypoint.sh /usr/local/bin/pghive-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/pghive-entrypoint.sh"]
CMD ["bash"]
