#!/usr/bin/env python3
"""After the skin is built (vst.json "skin_post"): the factory presets as MPC preset files in its Presets/."""
import os
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
env = dict(os.environ, MPC_VST_TOOLS="/mv/tools")
subprocess.run([sys.executable, os.path.join(here, "..", "tools", "presets.py"), "xpl", sys.argv[1]], check=True, env=env)
n = len([f for f in os.listdir(os.path.join(sys.argv[1], "Presets")) if f.endswith(".xpl")])
if n < 2:
    sys.exit("skin_post: no factory presets written")
print("presets:", n)
