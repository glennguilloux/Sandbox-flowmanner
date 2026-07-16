#!/usr/bin/env python3
"""Entrypoint that ensures /app/uploads is writable, then execs the CMD as flowmanner."""

import os
import pwd
import shlex
import subprocess
import sys

upload_dir = "/app/uploads"

os.makedirs(upload_dir, exist_ok=True)

# Chown only if running as root and ownership is wrong
try:
    stat_info = os.stat(upload_dir)
    if stat_info.st_uid != 1000 or stat_info.st_gid != 1000:
        os.chown(upload_dir, 1000, 1000)
except PermissionError:
    pass  # already running as flowmanner, can't chown but dir exists

# If running as root, drop to flowmanner
if os.geteuid() == 0:
    flowmanner = pwd.getpwnam("flowmanner")
    # Set up groups
    os.setgid(flowmanner.pw_gid)
    os.setuid(flowmanner.pw_uid)
    # Clean environment
    os.environ["HOME"] = flowmanner.pw_dir
    os.environ["USER"] = flowmanner.pw_name

# Reconcile built-in mission templates against the baked seed file.
# Self-healing: the canvas gallery always matches the image's seed
# after every container start (no manual re-seed, no silent DB drift).
# Runs as root (above) so it can reach the DB via the app env.
# Best-effort: a transient DB outage at boot must NEVER block startup,
# so failures are logged and swallowed before we exec uvicorn.
try:
    import subprocess as _sp

    _sp.run(
        [sys.executable, "/app/scripts/reload_builtin_templates.py"],
        env={**os.environ, "APP_DIR": "/app", "PYTHONPATH": "/app"},
        check=False,
        timeout=120,
    )
except Exception as _e:
    sys.stderr.write(f"[entrypoint] builtin-template reload skipped: {_e}\n")


# Exec the CMD (args passed via sys.argv[1:])
if len(sys.argv) > 1:
    cmd = sys.argv[1:]
    os.execvp(cmd[0], cmd)
else:
    # No CMD defined — keep container alive for debugging
    subprocess.run(["tail", "-f", "/dev/null"])
