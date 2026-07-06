#!/bin/sh
# entrypoint-wrapper.sh — per-sandbox worker entrypoint (current)
#
# Runs as PID 1 in the per-sandbox worker container spawned by sandboxd.
# Responsibilities (in order):
#
#   1. Create /home/sandbox/.runtimed (runtimed needs this; the bind-mount
#      overlay means it must be created AFTER the mount is applied).
#      Best-effort: with CapDrop=ALL, root in the container has no
#      capabilities and the bind-mounted host workspace is owned by a
#      different host uid, so this mkdir will usually fail with
#      "Permission denied" — which is now OK because we override the
#      socket path via RUNTIMED_DIR below.
#
#   2. Start a static HTTP server on port $SANDBOXD_PREVIEW_PORT (default
#      8081) in the background, serving from /home/sandbox/. This makes
#      the worker self-sufficient: the preview URL works as soon as the
#      container starts, without needing `sandboxd_serve` or a file
#      write to trigger the session-3 band-aid.  Uses `nohup` + `&` so
#      the server is detached from this shell.
#
#   3. Hand over to runtimed as PID 1. runtimed is the sandboxd runtime
#      that provides the file API, exec API, etc. for the LLM via the
#      control plane. The python server is a side process that survives
#      runtimed's signal handling — when runtimed exits, the container
#      dies, and the python server dies with it (which is fine, the
#      container is going away).
#
# Failure mode: if the python server fails to start, the log is at
# /tmp/http_server.log. The container is still up (runtimed is PID 1),
# but the preview URL will 404/connection-refused until the issue is
# debugged. This is a strict improvement over the previous behavior
# where the server never started at all (per the session-4 audit).

# Note: set -e is intentionally OFF. The mkdir for /home/sandbox/.runtimed
# will fail (see comment above) but we don't want that to abort the
# script. RUNTIMED_DIR overrides the runtimed's socket path so the
# failure is irrelevant.

mkdir -p /home/sandbox/.runtimed 2>/dev/null || true

# Best-effort: RUNTIMED_DEV_CMD's directory may not exist on a fresh
# container. The python server on 8081 serves from /home/sandbox/ root
# regardless, so this is just to keep runtimed's optional dev command
# from erroring out for legacy templates.
mkdir -p /home/sandbox/workspace/app 2>/dev/null || true

# Start the static HTTP server on port $SANDBOXD_PREVIEW_PORT (default
# 8081) in the background.  The same env var is read by the backend
# (settings.SANDBOXD_PREVIEW_PORT) so the preview URL port matches the
# server port without a hardcoded constant in two places.
# `nohup` ignores SIGHUP; `&` puts it in the background; redirecting
# stdout/stderr to a log file means failures are inspectable after the
# fact instead of filling the container's stdout (which runtimed owns).
nohup python3 -m http.server "${SANDBOXD_PREVIEW_PORT:-8081}" --directory /home/sandbox/ \
    >/tmp/http_server.log 2>&1 &

# Hand over to runtimed as PID 1. This replaces the current shell with
# runtimed; the python server (already backgrounded) becomes a child of
# runtimed and continues serving until the container terminates.
exec /usr/local/bin/runtimed
