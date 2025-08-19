from importlib.metadata import version, PackageNotFoundError
import tomli
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

__version__ = "1.0.1"
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
            logger.warning("pyproject.toml not found")
    except (ImportError, FileNotFoundError, KeyError):
        logger.warning("Failed to load version from pyproject.toml")
