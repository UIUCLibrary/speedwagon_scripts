"""Packaging script for Speedwagon distribution with bundled plugins."""
import abc
import pathlib
import platform
import tomllib
import shutil
import sys
import tempfile
import typing
import venv
import argparse
import re
import subprocess
import os
from typing import Optional, Callable, Dict, List, Union, Sequence
import zipfile

import cmake
from importlib import metadata

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

author_email_regex = re.compile(
    r'^"(?P<author>(.)+)"( <)(?P<email>[a-zA-Z0-9]+@[a-zA-Z0-9.]+)>'
)


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
        "--app-name", default="Speedwagon UIUC Prescon",
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


def generate_package_description_file(
    package_metadata: metadata.PackageMetadata,
    output_path: str,
    output_name: str = "package_description_file.txt"
) -> str:
    """Generate package description file.

    Args:
        package_metadata: Package metadata
        output_path: Directory path to save the description file
        output_name: file name to use for the data

    Returns: path to description file

    """
    description_file = os.path.join(output_path, output_name)
    with open(description_file, 'w') as f:
        data: Union[List[str], str] = package_metadata.get_all(
            'summary',
            failobj=''
        )
        if isinstance(data, list):
            data = data[0]
        f.write(data)
    return description_file


class AbsCPackGenerator(abc.ABC):
    def __init__(
        self,
        app_name: str,
        frozen_application_path: str,
        output_path: str,
        package_metadata: metadata.PackageMetadata
    ) -> None:
        self.package_metadata = package_metadata
        self.app_name = app_name
        self.frozen_application_path = frozen_application_path
        self.output_path = output_path

    @abc.abstractmethod
    def cpack_generator_name(self) -> str:
        """Get CPack generator."""

    @abc.abstractmethod
    def get_cpack_system_name(self) -> str:
        """Get CPACK_SYSTEM_NAME value."""
    @abc.abstractmethod
    def package_specific_config_lines(self) -> str:
        """Package specific cpack lines."""
    def general_section(self) -> str:
        return ''

    def generate(self) -> str:
        """Create text for cpack config file."""
        return "\n".join([
            self.general_section(),
            self.package_specific_config_lines()
        ])


class CPackGenerator(AbsCPackGenerator):
    general_cpack_template = """
set(CPACK_GENERATOR "%(cpack_generator)s")
set(CPACK_PACKAGE_NAME "%(cpack_package_name)s")
set(CPACK_INSTALLED_DIRECTORIES "%(cpack_installed_directories_source)s" "%(cpack_installed_directories_output)s")
set(CPACK_PACKAGE_VENDOR "%(cpack_package_vendor)s")
set(CPACK_SYSTEM_NAME "%(cpack_system_name)s")
set(CPACK_PACKAGE_VERSION "%(cpack_package_version)s")
set(CPACK_PACKAGE_VERSION_MAJOR "%(cpack_package_version_major)d")
set(CPACK_PACKAGE_VERSION_MINOR "%(cpack_package_version_minor)d")
set(CPACK_PACKAGE_VERSION_PATCH "%(cpack_package_version_patch)d")
set(CPACK_PACKAGE_FILE_NAME "%(cpack_package_file_name)s")
set(CPACK_RESOURCE_FILE_LICENSE "%(cpack_resource_file_license)s")
set(CPACK_PACKAGE_DESCRIPTION_FILE "%(cpack_package_description_file)s")
set(CPACK_PACKAGE_INSTALL_DIRECTORY "Speedwagon - UIUC")
set(CPACK_PACKAGE_EXECUTABLES "speedwagon" "%(app_name)s")
"""

    def get_cpack_package_file_name(self) -> str:
        return "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-${CPACK_SYSTEM_NAME}"  # noqa: E501

    def get_license_path(self) -> str:
        """Get path to License file."""
        return os.path.join(self.output_path, "LICENSE")

    def __init__(
        self,
        app_name: str,
        frozen_application_path: str,
        output_path: str,
        package_metadata: metadata.PackageMetadata,
        cl_args: argparse.Namespace
    ) -> None:
        super().__init__(app_name, frozen_application_path, output_path,
                         package_metadata)
        self.package_vendor = (
            self._get_first_author_from_package_metadata(package_metadata)
        )
        self.toml_config_file: Optional[pathlib.Path] =\
            pathlib.Path('pyproject.toml')

        self.command_line_args = cl_args

    @staticmethod
    def _get_first_author_from_package_metadata(
        package_metadata: metadata.PackageMetadata
    ) -> str:
        author_email: Union[str, List[str]] = package_metadata.json.get(
            'author_email', ''
        )
        if isinstance(author_email, list):
            author_email = author_email[0]
        result = author_email_regex.search(author_email)
        if result is None:
            return ''
        return result.groupdict().get('author', '')

    def get_cpack_system_name(self) -> str:
        return "${CMAKE_SYSTEM_NAME}"

    def general_section(self) -> str:
        major_version = int(self.package_metadata['version'].split(".")[0])
        minor_version = int(self.package_metadata['version'].split(".")[1])
        patch_version = int(self.package_metadata['version'].split(".")[2])
        specs = {
            "cpack_generator": self.cpack_generator_name(),
            "cpack_package_name": self.app_name,
            "cpack_system_name": self.get_cpack_system_name(),
            "cpack_installed_directories_source":
                os.path.abspath(
                    self.frozen_application_path
                ).replace(os.sep, "/"),
            "cpack_installed_directories_output":
                f"/{os.path.split(self.frozen_application_path)[-1]}",
            "cpack_package_vendor": self.package_vendor,
            "cpack_package_version":
                f"{major_version}.{minor_version}.{patch_version}",
            "cpack_package_version_major": major_version,
            "cpack_package_version_minor": minor_version,
            "cpack_package_version_patch": patch_version,
            "app_name": self.app_name,
            "cpack_package_file_name": self.get_cpack_package_file_name(),
            "cpack_resource_file_license": os.path.abspath(
                self.get_license_path()
            ).replace(os.sep, '/'),
            "cpack_package_description_file": os.path.abspath(
                generate_package_description_file(
                    self.package_metadata,
                    output_path=self.output_path
                )
            ).replace(os.sep, '/')
        }
        return CPackGenerator.general_cpack_template % specs


class MacOSPackageGenerator(CPackGenerator):
    """Generate Mac installer package."""

    def cpack_generator_name(self) -> str:
        return 'DragNDrop'

    def package_specific_config_lines(self) -> str:
        return ''

    def get_cpack_package_file_name(self) -> str:
        arch = 'x86_64' if platform.processor() == 'i386' else "arm64"
        system = f'macos-{arch}'
        return "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-" f"{system}"


def read_toml_data(toml_config_file: pathlib.Path) -> Dict[str, typing.Any]:
    """Read contents of toml file.

    Args:
        toml_config_file: path to toml config file.

    Returns: contents of toml file

    """
    with open(toml_config_file, "rb") as f:
        return tomllib.load(f)


class WindowsPackageGenerator(CPackGenerator):
    """Windows Package Generator.

    Uses Wix toolset to generate msi file.
    """
    wix_cpack_template = """
set(CPACK_WIX_SIZEOF_VOID_P "%(cpack_wix_sizeof_void_p)s")
set(CPACK_WIX_ARCHITECTURE "%(cpack_wix_architecture)s")
"""

    def get_license_path(self) -> str:
        out_file_path = os.path.join(self.output_path, 'LICENSE.txt')
        with open('LICENSE', "r") as source_file:
            with open(out_file_path, "w") as formated_file:
                formated_file.write(source_file.read())
        return os.path.abspath(out_file_path)

    def cpack_generator_name(self) -> str:
        return "WIX"

    def get_cpack_system_name(self) -> str:
        arch = platform.architecture()
        if arch[0] == '64bit':
            return "win64"
        if arch[0] == '32bit':
            return "win32"
        raise ValueError(f"Unknown architecture {arch}")

    def get_pyproject_toml_metadata_windows_packager_data(self) -> Dict[
        str, Union[None, str, Sequence[str]]
    ]:
        if self.toml_config_file is None:
            return {}
        if not self.toml_config_file.exists():
            return {}
        toml_data = read_toml_data(self.toml_config_file)
        tool_data = toml_data.get('tool', {})
        if not tool_data:
            return {}
        windows_standalone_packager_metadata = \
            tool_data.get('windows_standalone_packager', {})

        if not windows_standalone_packager_metadata:
            return {}
        return windows_standalone_packager_metadata.get(
            'cpack_config_variables',
            {}
        )

    def package_specific_config_lines(self) -> str:
        if platform.architecture()[0] == '64bit':
            cpack_wix_architecture = "x64"
            cpack_wix_sizeof_void_p = "8"
        elif platform.architecture()[0] == '32bit':
            cpack_wix_sizeof_void_p = "4"
            cpack_wix_architecture = "x86"
        else:
            cpack_wix_architecture = ""
            cpack_wix_sizeof_void_p = ""
        required_specs = {
            "cpack_wix_architecture": cpack_wix_architecture,
            "cpack_wix_sizeof_void_p": cpack_wix_sizeof_void_p,
        }
        package_data = self.get_pyproject_toml_metadata_windows_packager_data()
        optional_lines = []
        for k, v in package_data.items():
            if not k.startswith('CPACK_WIX'):
                continue
            optional_lines.append(f'set({k} "{v}")')

        if self.command_line_args.installer_icon:
            installer_icon =\
                os.path.abspath(
                    self.command_line_args.installer_icon
                ).replace(os.sep, "/")
            optional_lines.append(
                f'set(CPACK_WIX_PRODUCT_ICON "{installer_icon}")'
            )

        return "\n".join(
            [
                WindowsPackageGenerator.wix_cpack_template % required_specs,
                '\n'.join(optional_lines),
                ''
            ]
        )


def write_cpack_config_file(
    frozen_application_path: str,
    destination_path: str,
    package_metadata: metadata.PackageMetadata,
    app_name: str,
    cl_args: argparse.Namespace,
) -> str:
    """Generate a CPackConfig.cmake file for packaging with cpack command."""
    generators: Dict[str, typing.Type[CPackGenerator]] = {
        'win32': WindowsPackageGenerator,
        'darwin': MacOSPackageGenerator
    }
    generator_klass = generators.get(sys.platform)
    if generator_klass is None:
        raise ValueError(f"Unsupported platform '{sys.platform}'")
    generator = generator_klass(
        app_name,
        frozen_application_path=frozen_application_path,
        output_path=destination_path,
        package_metadata=package_metadata,
        cl_args=cl_args
    )
    generator.package_vendor = \
        (
            'University Library at The University of Illinois at Urbana '
            'Champaign: Preservation Services'
        )
    cpack_config_file = os.path.join(destination_path, "CPackConfig.cmake")
    with open(cpack_config_file, "w") as f:
        f.write(generator.generate())

    return cpack_config_file


def create_installer(
    frozen_application_path: str,
    dest: str,
    package_metadata: metadata.PackageMetadata,
    app_name: str,
    build_path: str,
    cl_args: argparse.Namespace,
) -> None:
    """Create OS specific system installer package."""
    config_file = write_cpack_config_file(
        frozen_application_path,
        build_path,
        package_metadata,
        app_name,
        cl_args
    )
    run_cpack(config_file)


def locate_cpack_on_path_env_var() -> str:
    """Locate cpack on the system path.

    If not found, a FileNotFoundError is raised.

    Returns: path to cpack command.

    """
    cpack_cmd = shutil.which("cpack")
    if cpack_cmd is None:
        raise FileNotFoundError("cpack command not found in the $PATH")
    return cpack_cmd


def locate_cpack_in_python_packages() -> str:
    """Locate cpack in the installed Python package in the current environment.

    If not found, a FileNotFoundError is raised.

    Returns: path to cpack command.

    """
    cpack_cmd = shutil.which("cpack", path=cmake.CMAKE_BIN_DIR)
    if cpack_cmd is None:
        raise FileNotFoundError("cpack command not found in python packages")
    return cpack_cmd


def get_cpack_path(
    strategies: Optional[List[Callable[[], str]]] = None
) -> str:
    """Locate CPack executable.

    Uses the list of search strategies to locate a valid CPack executable. The
    first successful result will return the value. If strategy called raises a
    FileNotFoundError, the next strategy will be attempted until a successful
    match happens. If all search strategies are exhausted with no result, this
    function will raise a FileNotFoundError.

    Args:
        strategies: Search strategy in order to attempt.

    Returns: Path to cpack executable.

    """
    if strategies is None:
        strategies = [
            locate_cpack_on_path_env_var,
            locate_cpack_in_python_packages
        ]
    for strategy in strategies:
        try:
            return strategy()
        except FileNotFoundError:
            continue
    raise FileNotFoundError("cpack command not found")


def run_cpack(
    config_file: str,
    build_path: str = os.path.join('.', "dist")
) -> None:
    """Execute cpack command with a config file.

    Args:
        config_file: path to a CPackConfig.cmake file
        build_path: Build path for cpack.

    """
    args = [
        "--config", config_file,
        "-B", build_path,
    ]
    cpack_cmd = get_cpack_path()
    subprocess.check_call([cpack_cmd] + args)


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
            os.path.abspath(os.path.dirname(__file__))
        ]
    }
    with open(specs_file_name, "w", encoding="utf-8") as spec_file:
        spec_file.write(SPEC_TEMPLATE % specs)

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
    wheel_metadata = get_package_metadata(args.python_package_file)
    create_installer(
        expected_frozen_path,
        args.dist,
        wheel_metadata,
        app_name=args.app_name,
        build_path=args.build_path,
        cl_args=args,
    )


if __name__ == '__main__':
    main()
