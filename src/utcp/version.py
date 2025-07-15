from importlib.metadata import version, PackageNotFoundError
import tomli
from pathlib import Path

__version__ = "0.1.3"
try:
    __version__ = version("utcp")
except PackageNotFoundError:
    try:
        pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomli.load(f)
                __version__ = pyproject_data.get("project", {}).get("version", __version__)
    except (ImportError, FileNotFoundError, KeyError):
        pass
