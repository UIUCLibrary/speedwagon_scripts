"""Packaging script for Speedwagon distribution with bundled plugins."""
import abc
import pathlib
import shutil
import sys
import tempfile
import typing
import venv
import argparse
import subprocess
import os
from typing import Optional, Callable, Dict
import zipfile

if sys.version_info < (3, 10):
    import importlib_metadata as metadata
else:
    from importlib import metadata

from package_speedwagon import installer

import PyInstaller.__main__

DEFAULT_BOOTSTRAP_SCRIPT =\
    os.path.join(os.path.dirname(__file__), 'speedwagon-bootstrap.py')

DEFAULT_APP_ICON = os.path.join(os.path.dirname(__file__), 'favicon.ico')
DEFAULT_EXECUTABLE_NAME = 'speedwagon'
DEFAULT_COLLECTION_NAME = 'Speedwagon!'

SPEC_TEMPLATE = """# -*- mode: python ; coding: utf-8 -*-
import os
import sys
try:  # pragma: no cover
    from importlib import metadata
except ImportError:  # pragma: no cover
    import importlib_metadata as metadata  # type: ignore

block_cipher = None
a = Analysis([%(bootstrap_script)r],
             pathex=%(search_paths)s,
             binaries=[],
             datas=%(datas)s,
             hiddenimports=['%(top_level_package_folder_name)s'],
             hookspath=[os.path.join(workpath, ".."), SPECPATH] + %(hookspath)s,
             hooksconfig={},
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=True)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=True,
          name='%(app_executable_name)s',
          debug=True,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False,
          disable_windowed_traceback=False,
          target_arch=None,
          codesign_identity=None,
          entitlements_file=None, 
          icon=%(app_icon)r)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               upx_exclude=[],
               name='%(collection_name)s')
pkg_metadata = metadata.metadata("speedwagon")

app = BUNDLE(coll,
             name='%(bundle_name)s',
             version=pkg_metadata['Version'],
             icon=%(installer_icon)r,
             bundle_identifier=None)

"""


def get_default_app_icon() -> str:
    """Get path to default icon for launching desktop application."""
    return os.path.join(os.path.dirname(__file__), 'favicon.ico')


class SetInstallerIconAction(argparse.Action):
    def __call__(
            self,
            parser: argparse.ArgumentParser,
            namespace: argparse.Namespace,
            values,
            option_string: Optional[str] = None
    ):
        if values is None:
            raise ValueError("missing installer icon file")
        values = typing.cast(pathlib.Path, values)
        if not values.exists():
            parser.error(f"'{values}' does not exist.")
        if not values.is_file():
            parser.error(f"'{values}' is not a file.")
        if sys.platform == "darwin":
            if not values.name.endswith(".icns"):
                parser.error(
                    "--installer-icon for MacOS requires .icns icon file"
                )
        elif sys.platform == "win32":
            if not values.name.endswith(".ico"):
                parser.error(
                    "--installer-icon for Windows requires .ico icon file"
                )

        setattr(namespace, self.dest, values)


class ValidatePackage(argparse.Action):

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values,
        option_string: Optional[str] = None
    ):
        if values is None:
            raise ValueError("missing package")
        values = typing.cast(pathlib.Path, values)
        if not values.exists():
            parser.error(f"'{values}' does not exist.")
        if not values.is_file():
            parser.error(f"'{values}' is not a file.")
        if not values.name.endswith(".whl"):
            parser.error(f"'{values}' is not a wheel")
        setattr(namespace, self.dest, values)


class AppIconValidate(argparse.Action):

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values,
        option_string: Optional[str] = None
    ):
        values = typing.cast(pathlib.Path, values)
        if not values.name.endswith(".ico"):
            parser.error("--app-icon needs to be a .ico file")
        setattr(namespace, self.dest, values)


def get_args_parser() -> argparse.ArgumentParser:
    """Get CLI args parser."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "python_package_file",
        type=pathlib.Path,
        action=ValidatePackage,
        help="wheel or source distribution package"
    )
    parser.add_argument(
        "--force-rebuild",
        action='store_true',
        help="force application environment to be rebuilt"
    ),
    parser.add_argument(
        "--build-path",
        default=os.path.join("build", "packaging"),
        help="path to build directory (default: %(default)s)"
    )
    parser.add_argument(
        "--dist",
        default="dist",
        help='output path directory (default: %(default)s)'
    )
    default_installer_icon =\
        os.path.join(os.path.dirname(__file__), 'favicon.icns') \
        if sys.platform == "darwin" \
        else os.path.join(os.path.dirname(__file__), 'favicon.ico')
    parser.add_argument(
        "--installer-icon",
        default=os.path.relpath(default_installer_icon, start=os.getcwd()),
        type=pathlib.Path,
        action=SetInstallerIconAction,
        help='icon used by installer (default: %(default)s)'
    ),
    parser.add_argument(
        "--app-bootstrap-script",
        default=os.path.relpath(
            os.path.normcase(DEFAULT_BOOTSTRAP_SCRIPT), start=os.getcwd()
        ),
        help="Python script used to launch Speedwagon (default: %(default)s)"
    ),
    parser.add_argument(
        "--app-icon",
        default=pathlib.Path(
            os.path.relpath(DEFAULT_APP_ICON, start=os.getcwd())
        ),
        action=AppIconValidate,
        type=pathlib.Path,
        help="Application icon (default: %(default)s)"
    ),
    parser.add_argument(
        "--app-name", default="Speedwagon",
        help="Name of application (default: %(default)s)"
    )
    parser.add_argument(
        "--app-executable-name", default=DEFAULT_EXECUTABLE_NAME,
        help="Name of application executable file (default: %(default)s)"
    )
    parser.add_argument(
        "-r", "--requirement",
        action='append',
        default=[],
        help='-r --requirement <file>    '
             'Install from the given requirements file. '
             'This option can be used multiple times.'
    )
    parser.add_argument(
        "--config-file",
        # default="pyproject.toml",
        type=pathlib.Path,
        help="config file"
    )
    return parser


def create_virtualenv(
    package: str,
    build_path: str,
    *requirements_files
) -> None:
    """Create Python virtual environment using the package provided."""
    try:
        venv.create(build_path, with_pip=False)
        requirements_commands = []
        for file_name in requirements_files:
            requirements_commands += ["-r", file_name]

        subprocess.run(
            [
                "pip",
                "install", package,
                "--upgrade",
                f"--target={build_path}"
            ] + requirements_commands,
            check=True
        )
    except Exception:
        shutil.rmtree(build_path)
        raise


def freeze_env(
    specs_file: str,
    build_path: str,
    work_path: str,
    dest: str
) -> None:
    """Freeze Python Environment."""
    PyInstaller.__main__.run([
        '--noconfirm',
        specs_file,
        "--distpath", dest,
        "--workpath", work_path,
        "--clean"
    ])


search_frozen_strategy = Callable[[str, argparse.Namespace], Optional[str]]


def find_frozen_mac(
    search_path: str,
    args: argparse.Namespace
) -> Optional[str]:
    """Search strategy to location frozen Python application on MacOS.

    Args:
        search_path: starting path to search recursively
        args: user args from CLI

    Returns: Path to speedwagon application if found, else returns None.

    """
    for root, dirs, _ in os.walk(search_path):
        for dir_name in dirs:
            if dir_name != f"{args.app_name}.app":
                continue
            return os.path.join(root, dir_name)
    return None


def find_frozen_windows(
    search_path: str,
    _: argparse.Namespace
) -> Optional[str]:
    """Search strategy to location frozen Python application on Windows.

    Args:
        search_path: starting path to search recursively
        _:

    Returns: Path to speedwagon application if found, else returns None.

    """
    for root, dirs, __ in os.walk(search_path):
        for dir_name in dirs:
            if dir_name != DEFAULT_COLLECTION_NAME:
                continue
            path = os.path.join(root, dir_name)
            for filename in os.listdir(path):
                if not filename.endswith(".exe"):
                    continue
                if filename == "speedwagon.exe":
                    return path
    return None


def find_frozen_folder(
    search_path: str,
    args: argparse.Namespace,
    strategy: Optional[search_frozen_strategy] = None
) -> Optional[str]:
    """Locates the folder containing Frozen Speedwagon application.

    Args:
        search_path: path to search frozen folder recursively
        args: cli args
        strategy: searching strategy, if not selected explicitly, the strategy
            is determined by system platform.

    Returns: Path to the folder containing Frozen Speedwagon application if
              found or None if not found.

    """
    strategies: Dict[str, search_frozen_strategy] = {
        "win32": find_frozen_windows,
        "darwin": find_frozen_mac
    }
    if strategy is None:
        strategy = strategies.get(sys.platform)
        if strategy is None:
            raise ValueError(f"Unsupported platform: {sys.platform}")
    return strategy(search_path, args)


def get_package_metadata(
    package_file: pathlib.Path
) -> metadata.PackageMetadata:
    """Read metadata of a Python wheel packager.

    Args:
        package_file: Path to a Python whl file.

    Returns: Distribution metadata

    """
    metadata_text = read_file_in_archive_in_zip(package_file, 'METADATA')
    with tempfile.TemporaryDirectory() as temp_dir:
        metadata_file = os.path.join(temp_dir, "METADATA")

        with open(metadata_file, "wb") as fp:
            fp.write(metadata_text)

        return metadata.Distribution.at(metadata_file).metadata
    raise FileNotFoundError(f"No metadata found for {package_file}")


def read_file_in_archive_in_zip(
    archive: pathlib.Path,
    file_name: str
) -> bytes:
    """Read data of a file inside a zip archive."""
    with zipfile.ZipFile(archive) as zf:
        for item in zf.infolist():
            if item.is_dir():
                continue
            if not os.path.split(item.filename)[-1] == file_name:
                continue
            with zf.open(item) as f:
                return f.read()
    raise ValueError(f"No {file_name} file in {archive}")


def get_package_top_level(package_file: pathlib.Path) -> str:
    """Get package top level folder."""
    if package_file.name.endswith(".whl"):
        return read_file_in_archive_in_zip(
            package_file,
            "top_level.txt"
        ).decode("utf-8").strip()
    raise ValueError("unknown File type")


def create_hook_for_wheel(
    path: str,
    strategy: Callable[[], str]
) -> None:
    package_name = strategy()
    template = """# Generated by package_speedwagon.py script
from PyInstaller.utils.hooks import copy_metadata, collect_all
datas, binaries, hiddenimports = collect_all('%(package_name)s')
datas += copy_metadata('%(package_name)s', recursive=True)
    """ % dict(package_name=package_name)
    with open(os.path.join(path, f"hook-{package_name}.py"), "w") as fp:
        fp.write(template)


def main() -> None:
    args_parser = get_args_parser()
    args = args_parser.parse_args()
    package_env = os.path.join(args.build_path, "speedwagon")
    if any([
        args.force_rebuild is True,
        not os.path.exists(package_env),
        not os.path.exists(
            os.path.join(
                package_env,
                "Lib" if sys.platform == 'win32' else 'lib'
            )),
        not os.path.exists(
            os.path.join(
                package_env,
                "Scripts" if sys.platform == 'win32' else 'bin'
            )),
    ]):
        create_virtualenv(
            args.python_package_file,
            package_env,
            *args.requirement,
        )

    specs_file_name = os.path.join(args.build_path, "specs.spec")
    logo = os.path.abspath(os.path.join(package_env, "speedwagon", 'logo.png'))
    data_files = [
        (os.path.abspath(args.app_icon).replace(os.sep, '/'), 'speedwagon'),
        (logo, 'speedwagon'),
    ]
    additional_hooks_path = os.path.join(args.build_path, "hooks")
    if not os.path.exists(additional_hooks_path):
        os.makedirs(additional_hooks_path)

    specs = {
        "bootstrap_script": os.path.abspath(args.app_bootstrap_script),
        "search_paths": [
            package_env
        ],
        "collection_name": DEFAULT_COLLECTION_NAME,
        "app_icon": os.path.abspath(args.app_icon),
        "top_level_package_folder_name":
            get_package_top_level(args.python_package_file),
        "installer_icon": os.path.abspath(args.installer_icon),
        "datas": data_files,
        "bundle_name":
            f"{args.app_name}.app" if sys.platform == "darwin"
            else args.app_name,
        "app_executable_name": args.app_executable_name,
        'hookspath': [
            os.path.abspath(os.path.dirname(__file__)),
            os.path.abspath(additional_hooks_path)
        ]
    }
    with open(specs_file_name, "w", encoding="utf-8") as spec_file:
        spec_file.write(SPEC_TEMPLATE % specs)

    create_hook_for_wheel(
        path=additional_hooks_path,
        strategy=lambda: get_package_top_level(args.python_package_file),
    )
    freeze_env(
        specs_file=specs_file_name,
        work_path=os.path.join(args.build_path, 'workpath'),
        build_path=package_env,
        dest=args.dist
    )
    expected_frozen_path = find_frozen_folder(args.dist, args=args)
    if not expected_frozen_path:
        raise FileNotFoundError(
            "Unable to find folder containing frozen application"
        )

    installer.create_installer(
        expected_frozen_path,
        args.dist,
        get_package_metadata(args.python_package_file),
        app_name=args.app_name,
        build_path=args.build_path,
        cl_args=args,
    )


if __name__ == '__main__':
    main()
