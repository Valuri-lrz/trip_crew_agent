import os
from pathlib import Path
root = Path(".data/crewai").resolve()
root.mkdir(parents=True, exist_ok=True)
import crewai_core.paths as p
p.db_storage_path = lambda: str(root)
import crewai
print("VERSION", crewai.__version__)
print("TOP", sorted(n for n in dir(crewai) if not n.startswith("_")))
from crewai import Agent, Task, Crew, Process, LLM
print("CORE_OK", Agent, Process.RAINBOW if hasattr(Process,"RAINBOW") else [x for x in dir(Process) if not x.startswith("_")])
