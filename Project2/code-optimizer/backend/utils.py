"""
File + Git helpers (unchanged logic, now with logging & pathlib)
"""

import subprocess
import sys
import logging
from pathlib import Path
from typing import List
from langchain_openai import AzureChatOpenAI
from langfuse import Langfuse
from functools import lru_cache
from kvsecrets import get_secret

_LOGGER = logging.getLogger(__name__)
_langfuse = Langfuse()

@lru_cache
def _prompt(name: str):
    return _langfuse.get_prompt(name)


def _llm(model: str, temperature: float):
    return AzureChatOpenAI(
        api_key=get_secret("AZURE-OPENAI-API-KEY"),
        api_version="2024-12-01-preview",
        model=model,
        temperature=temperature,
    )


def run_command(cmd: str) -> None:
    _LOGGER.info("Running: %s", cmd)
    try:
        subprocess.run(cmd, shell=True, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        _LOGGER.error("Command failed: %s", exc.stderr)
        sys.exit(1)


def clone_repo(url: str, base_dir: Path) -> Path:
    base_dir.mkdir(exist_ok=True)
    repo_name = url.split("/")[-1].removesuffix(".git")
    dest = base_dir / repo_name
    if dest.exists():
        _LOGGER.info("Repo already cloned: %s", dest)
        return dest
    run_command(f"git clone --depth 1 {url} {dest}")
    return dest


def list_files(root: Path) -> List[str]:
    return [str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()]
