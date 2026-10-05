"""Isolated child process: native failures leave the parent able to report them."""

import sys

from lab.project import write_json
from lab.runtime import OUT
from lab.suite import run

result = run(sys.argv[1])
write_json(OUT / "result.json", result)
