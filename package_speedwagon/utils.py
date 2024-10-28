import pathlib
from typing import Dict, Any, Callable, BinaryIO
import sys

if sys.version_info < (3, 11):
    from pip._vendor import tomli as tomllib
else:
    import tomllib


def read_toml_data(
    toml_config_file: pathlib.Path,
    loader: Callable[[BinaryIO], Dict[str, Any]] = tomllib.load
) -> Dict[str, Any]:
    """Read contents of toml file.

    Args:
        toml_config_file: path to toml config file.
        loader: toml loader function.

    Returns: contents of toml file

    """
    with open(toml_config_file, "rb") as f:
        return loader(f)
