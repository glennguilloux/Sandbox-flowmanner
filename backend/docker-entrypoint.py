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

# Exec the CMD (args passed via sys.argv[1:])
if len(sys.argv) > 1:
    cmd = sys.argv[1:]
    os.execvp(cmd[0], cmd)
else:
    # No CMD defined — keep container alive for debugging
    subprocess.run(["tail", "-f", "/dev/null"])
