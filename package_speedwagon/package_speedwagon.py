"""Packaging script for Speedwagon distribution with bundled plugins."""
import pathlib
import shutil
import sys
import tempfile
import typing
import venv
import argparse
import subprocess
import os
from typing import Optional
import zipfile
from package_speedwagon import defaults, freeze

if sys.version_info < (3, 10):
    import importlib_metadata as metadata
else:
    from importlib import metadata

from package_speedwagon import installer


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
            os.path.normcase(defaults.DEFAULT_BOOTSTRAP_SCRIPT),
            start=os.getcwd()
        ),
        help="Python script used to launch Speedwagon (default: %(default)s)"
    ),
    parser.add_argument(
        "--app-icon",
        default=pathlib.Path(
            os.path.relpath(defaults.DEFAULT_APP_ICON, start=os.getcwd())
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
        "--app-executable-name", default=defaults.DEFAULT_EXECUTABLE_NAME,
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
    specs_file_generator = freeze.DefaultGenerateSpecs()
    specs_file_generator.data.bootstrap_script = os.path.abspath(args.app_bootstrap_script)
    specs_file_generator.data.app_executable_name = args.app_executable_name
    specs_file_generator.data.data_files = data_files
    specs_file_generator.data.collection_name = defaults.DEFAULT_COLLECTION_NAME
    specs_file_generator.data.bundle_name =f"{args.app_name}.app" if sys.platform == "darwin" else args.app_name
    specs_file_generator.data.app_icon = os.path.abspath(args.app_icon)
    specs_file_generator.data.installer_icon = os.path.abspath(args.installer_icon)
    specs_file_generator.data.top_level_package_folder_name = get_package_top_level(args.python_package_file)
    specs_file_generator.data.hookspath =  [
        os.path.abspath(os.path.dirname(__file__)),
        os.path.abspath(additional_hooks_path)
    ]
    specs_file_generator.data.search_paths = [
        package_env
    ]
    with open(specs_file_name, "w", encoding="utf-8") as spec_file:
        spec_file.write(specs_file_generator.generate())

    freeze.create_hook_for_wheel(
        path=additional_hooks_path,
        strategy=lambda: get_package_top_level(args.python_package_file),
    )
    freeze.freeze_env(
        specs_file=specs_file_name,
        work_path=os.path.join(args.build_path, 'workpath'),
        build_path=package_env,
        dest=args.dist
    )
    expected_frozen_path = freeze.find_frozen_folder(args.dist, args=args)
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
