import abc
import argparse
import os
import platform
import re
import shutil
import packaging.version
import pathlib
import subprocess
import sys
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Type,
    Union, Tuple
)

if sys.version_info < (3, 10):
    import importlib_metadata as metadata
else:
    from importlib import metadata


import cmake

from package_speedwagon import utils
__all__ = ['cpack_config_generators']


def get_license(
    strategies_list: Optional[List[Callable[[], Optional[str]]]] = None
) -> str:
    for strategy in strategies_list if strategies_list is not None else []:
        result = strategy()
        if result is None:
            continue
        return result
    raise FileNotFoundError("Unable to find license file")


class LocateLicenseFile:

    def __init__(self, search_paths: Optional[Iterable[str]] = None) -> None:
        super().__init__()
        self.search_paths = search_paths or ['.']
        self.potential_file_name = "LICENSE"

    def locate_license_file(self) -> Optional[str]:

        for search_path in self.search_paths:
            potential_file =\
                os.path.join(search_path, self.potential_file_name)
            if os.path.exists(potential_file):
                return potential_file
        return None

    def __call__(self) -> Optional[str]:
        license_file = self.locate_license_file()
        if license_file:
            return os.path.abspath(license_file)
        return None


class GenerateNoLicenseGivenFile:

    def __init__(self, output_file: str) -> None:
        self.output_file = output_file

    @staticmethod
    def get_license_text() -> str:
        return "No License given"

    def write_license_file(self) -> None:
        with open(self.output_file, "w", encoding="utf-8") as license_file:
            license_file.write(self.get_license_text())

    def __call__(self) -> Optional[str]:
        self.write_license_file()
        return os.path.abspath(self.output_file)


class CopyLicenseFile:

    def __init__(self, source_file: str, output_file: str) -> None:
        super().__init__()
        self.output_file = output_file
        self.source_file = source_file

    def copy_file(self) -> None:
        with open(self.source_file, "r") as source_file:
            with open(self.output_file, "w") as formated_file:
                formated_file.write(source_file.read())

    def pre_check(self) -> bool:
        if not os.path.exists(self.source_file):
            return False
        return True

    def __call__(self) -> Optional[str]:
        if not self.pre_check():
            return None
        self.copy_file()
        return os.path.abspath(self.output_file)


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


author_email_regex = re.compile(
    r'^"(?P<author>(.)+)"( <)(?P<email>[a-zA-Z0-9]+@[a-zA-Z0-9.]+)>'
)


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
"""  # noqa: E501

    def get_cpack_package_file_name(
        self,
        version: packaging.version.Version
    ) -> str:
        if not version.is_prerelease:
            return "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-${CPACK_SYSTEM_NAME}"  # noqa: E501
        if version.is_devrelease:
            return (
                "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}"
                f".dev{version.dev}"
            )
        prerelease = ''.join(map(str, version.pre if version.pre else []))
        return "${CPACK_PACKAGE_NAME}-" \
               "${CPACK_PACKAGE_VERSION}." f"{prerelease}" \
               "-${CPACK_SYSTEM_NAME}"  # noqa: E501

    def get_license_path(self) -> str:
        """Get path to License file."""
        strategy_attempt_order: List[Callable[[], Optional[str]]]
        if self.license_file is not None:
            strategy_attempt_order = [lambda: str(self.license_file)]
        else:
            strategy_attempt_order = [
                LocateLicenseFile(),
                GenerateNoLicenseGivenFile(
                    os.path.join(self.output_path, "LICENSE")
                )
            ]
        return get_license(strategies_list=strategy_attempt_order)

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
        self.toml_config_file: Optional[pathlib.Path] = \
            pathlib.Path('pyproject.toml')

        self.command_line_args = cl_args
        self.license_file: Optional[pathlib.Path] = None

    @staticmethod
    def _get_first_author_from_package_metadata(
            package_metadata: metadata.PackageMetadata
    ) -> str:
        author_email: Union[str, List[str]] = package_metadata.get_all(
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
        string = self.package_metadata['version']
        version = packaging.version.Version(string)
        major_version, minor_version, patch_version = (
            version.major,
            version.minor,
            version.micro
        )
        try:
            if self.license_file is None:
                license_path = self.get_license_path()
            else:
                license_path = str(self.license_file)
        except FileNotFoundError:
            license_path = os.path.join(self.output_path, "LICENSE")
            with open(license_path, 'w') as f:
                f.write("No License provided")

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
            "cpack_package_file_name":
                self.get_cpack_package_file_name(version),
            "cpack_resource_file_license": os.path.abspath(
                license_path
            ).replace(os.sep, '/'),
            "cpack_package_description_file": os.path.abspath(
                generate_package_description_file(
                    self.package_metadata,
                    output_path=self.output_path
                )
            ).replace(os.sep, '/')
        }
        return CPackGenerator.general_cpack_template % specs


class WixToolsetPackageGenerator(CPackGenerator):
    """Windows Package Generator.

    Uses Wix toolset to generate msi file.
    """
    wix_cpack_template = """
set(CPACK_WIX_SIZEOF_VOID_P "%(cpack_wix_sizeof_void_p)s")
set(CPACK_WIX_ARCHITECTURE "%(cpack_wix_architecture)s")
"""

    @property
    def default_license_find_strategies(
        self
    ) -> List[Callable[[], Optional[str]]]:
        expected_license_file = os.path.join(self.output_path, "LICENSE.txt")
        return [
            CopyLicenseFile(
                source_file='LICENSE',
                output_file=expected_license_file
            ),
            GenerateNoLicenseGivenFile(expected_license_file),
        ]

    def get_license_path(
        self,
        strategies: Optional[List[Callable[[], Optional[str]]]] = None
    ) -> str:
        if strategies is None:
            strategies = self.default_license_find_strategies
        return get_license(strategies)

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
        toml_data = utils.read_toml_data(self.toml_config_file)
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

    @staticmethod
    def get_wix_specific_configs(
        architecture: Tuple[str, str] = platform.architecture()
    ) -> Dict[str, Optional[str]]:

        if architecture[0] == '64bit':
            return {
                "cpack_wix_architecture": "x64",
                "cpack_wix_sizeof_void_p": "8"
            }
        elif architecture[0] == '32bit':
            return {
                "cpack_wix_sizeof_void_p": "4",
                "cpack_wix_architecture": "x86",
            }
        return {
            "cpack_wix_sizeof_void_p": None,
            "cpack_wix_architecture": None,
        }

    def package_specific_config_lines(self) -> str:
        cpack_wix_specs = self.get_wix_specific_configs()
        required_specs = {
            "cpack_wix_architecture":
                cpack_wix_specs['cpack_wix_architecture'],
            "cpack_wix_sizeof_void_p":
                cpack_wix_specs['cpack_wix_sizeof_void_p'],
        }
        package_data = self.get_pyproject_toml_metadata_windows_packager_data()
        optional_lines = []
        for k, v in package_data.items():
            if not k.startswith('CPACK_'):
                continue
            optional_lines.append(f'set({k} "{v}")')

        if self.command_line_args.installer_icon:
            installer_icon = \
                os.path.abspath(
                    self.command_line_args.installer_icon
                ).replace(os.sep, "/")
            optional_lines.append(
                f'set(CPACK_WIX_PRODUCT_ICON "{installer_icon}")'
            )

        return "\n".join(
            [
                WixToolsetPackageGenerator.wix_cpack_template % required_specs,
                '\n'.join(optional_lines),
                ''
            ]
        )


class MacOSDragNDropPackageGenerator(CPackGenerator):
    """Generate Mac installer package."""

    def cpack_generator_name(self) -> str:
        return 'DragNDrop'

    def package_specific_config_lines(self) -> str:
        return ''

    def get_cpack_package_file_name(
        self,
        version: packaging.version.Version
    ) -> str:
        arch = 'x86_64' if platform.processor() == 'i386' else "arm64"
        system = f'macos-{arch}'
        if not version.is_prerelease:
            return \
                "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-" f"{system}"
        if version.is_devrelease:
            return (
                "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}"
                f".dev{version.dev}"
                f"-{system}"
            )

        prerelease = ''.join(map(str, version.pre if version.pre else []))
        return "${CPACK_PACKAGE_NAME}-" \
               "${CPACK_PACKAGE_VERSION}." f"{prerelease}-" \
               f"{system}"  # noqa: E501


cpack_config_generators: Dict[str, Type[CPackGenerator]] = {
    'DragNDrop': MacOSDragNDropPackageGenerator,
    'Wix': WixToolsetPackageGenerator
}


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


DEFAULT_CPACK_FINDING_STRATEGIES = [
    locate_cpack_on_path_env_var,
    locate_cpack_in_python_packages
]


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
        strategies = DEFAULT_CPACK_FINDING_STRATEGIES
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
