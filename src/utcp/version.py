import pathlib

# Get the path to the VERSION file
version_path = pathlib.Path(__file__).parent / "VERSION"

# Read the version from the file
with open(version_path, "r") as f:
    __version__ = f.read().strip()
