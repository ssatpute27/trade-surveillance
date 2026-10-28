"""Stable stdio entry point for the private tunnel, independent of working directory."""
import runpy
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
runpy.run_module('app.chatgpt_mcp',run_name='__main__')
