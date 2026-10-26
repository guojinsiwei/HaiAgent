"""Offline verification; intended to run under Linux/WSL."""
from pathlib import Path
import os
import subprocess
import sys

root=Path(__file__).resolve().parent
env=dict(os.environ,PYTHONPATH=str(root/'src'))
subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_lean*.py','-v'],
               cwd=root,env=env,check=True)
subprocess.run([sys.executable,'-B','-m','bestfgs','--help'],cwd=root,env=env,check=True)
