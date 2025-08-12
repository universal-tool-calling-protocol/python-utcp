from importlib.metadata import version, PackageNotFoundError
import tomli
from pathlib import Path
import logging

__version__ = "0.2.1"
try:
    __version__ = version("utcp")
except PackageNotFoundError:
    try:
        pyproject_path = Path(__file__).parent.parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomli.load(f)
                __version__ = pyproject_data.get("project", {}).get("version", __version__)
        else:
            logging.warning("pyproject.toml not found")
    except (ImportError, FileNotFoundError, KeyError):
        logging.warning("Failed to load version from pyproject.toml")
