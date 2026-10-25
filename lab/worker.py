"""Isolated child process with one immutable run context."""

import json
import subprocess
import sys

from lab.project import ROOT, write_json
from lab.runtime import OUT

command = sys.argv[1]
arguments = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"machine": "sine"}
if (
    command in ("build", "render", "profile", "test")
    and arguments.get("machine") == "sine"
):
    from lab.suite import run

    result = run(command)
else:
    from lab.mods import build_mod, cpu_plan, resource_declarations, test_mod

    if command == "build":
        result = build_mod(
            arguments["machine"],
            OUT,
            arguments["runtime_variant"],
            shared_save=arguments.get("shared_save", False),
        )
    elif command == "test":
        result = test_mod(
            arguments["machine"],
            OUT,
            arguments["runtime_variant"],
            shared_save=arguments.get("shared_save", False),
        )
    elif command == "plan":
        result = cpu_plan(arguments["mods"], OUT)
        result["ok"] = result["compatible"]
        print(
            "COMPATIBLE"
            if result["ok"]
            else "REFUSED: conflicting writes or insufficient owned placement",
            flush=True,
        )
    elif command == "resources":
        result = resource_declarations()
        write_json(OUT / "integration-resources.json", result)
        result = dict(ok=True, output=str(OUT / "integration-resources.json"))
    elif command == "compare-runtime":
        subprocess.run(
            [
                sys.executable,
                "-B",
                str(ROOT / "scripts/check-reuse-runtime.py"),
                str(OUT / "paired"),
            ],
            check=True,
        )
        result = dict(ok=True, output=str(OUT / "paired/runtime-comparison.json"))
    else:
        raise ValueError("Unknown lab command")
write_json(OUT / "result.json", result)
