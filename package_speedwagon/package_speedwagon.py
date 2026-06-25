"""Packaging script for Speedwagon distribution with bundled plugins."""

import abc
import hashlib
import logging
import pathlib
import shutil
import sys
import tempfile
import typing
import venv
import argparse
import subprocess
import os
import tomlkit

from typing import Optional, Mapping, Type, List, Callable, Dict
import zipfile
from package_speedwagon import defaults, freeze, installer, utils

from importlib import metadata

if sys.version_info < (3, 11):
    from pip._vendor import tomli as tomllib
else:
    import tomllib

logger = logging.getLogger(__name__)


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


class TomlFileAction(argparse.Action):
    @staticmethod
    def check_valid_toml_file(path: pathlib.Path) -> bool:
        try:
            utils.read_toml_data(path)
            return True
        except tomllib.TOMLDecodeError:
            return False

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values,
        option_string: Optional[str] = None
    ):
        values = typing.cast(pathlib.Path, values)
        if not values.exists():
            parser.error(f"'{values}' does not exist.")
        if not self.check_valid_toml_file(values):
            parser.error(f"{values} does not appear to be a valid TOML file.")
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
    )

    parser.add_argument(
        "--hidden-import",
        action='append',
        dest='hidden_imports',
    )

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
    )

    parser.add_argument(
        "--app-bootstrap-script",
        default=os.path.relpath(
            os.path.normcase(defaults.DEFAULT_BOOTSTRAP_SCRIPT),
            start=os.getcwd()
        ),
        help="Python script used to launch Speedwagon (default: %(default)s)"
    )

    parser.add_argument(
        "--app-icon",
        default=pathlib.Path(
            os.path.relpath(defaults.DEFAULT_APP_ICON, start=os.getcwd())
        ),
        action=AppIconValidate,
        type=pathlib.Path,
        help="Application icon (default: %(default)s)"
    )

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
        "--license-file",
        type=pathlib.Path,
        help="File used for application's EULA "
    )
    # Only default config file if one exists on pwd
    if os.path.exists("pyproject.toml"):
        default_installer_config_file = "pyproject.toml"
        config_file_help_message = "config file (default: %(default)s)"
    else:
        default_installer_config_file = None
        config_file_help_message = "config file"

    parser.add_argument(
        "--config-file",
        default=default_installer_config_file,
        action=TomlFileAction,
        type=pathlib.Path,
        help=config_file_help_message
    )
    return parser


def create_virtualenv(
    package: str,
    build_path: str,
    *requirements_files: str
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

def read_pkg_info(raw_data: str):
    data: Dict[str, Optional[str]] = {
        "name": None,
        "version": None,
        "license": None,
        "summary": None,
        "project_url": None
    }
    for line in raw_data.split("\n"):
        match line.split():
            case ["Name:", name]:
                data["name"] = name

            case ["Version:", version]:
                data["version"] = version

            case ["License-Expression:", license_type]:
                data["license"] = license_type

            case["Summary:", *values]:
                data["summary"] = " ".join(values)

            case["Project-URL:", "project,", url]:
                data["project_url"] = url
    return data


def read_whl_metadata(wheel):
    with zipfile.ZipFile(wheel) as zip_file:
        for compressed_file in zip_file.infolist():
            if compressed_file.is_dir():
                continue
            path, filename = os.path.split(compressed_file.filename)
            if "dist-info" not in path.split(os.path.sep)[0]:
                continue
            if "METADATA" != filename:
                continue
            return read_pkg_info(zip_file.read(compressed_file).decode("utf-8"))
        else:
            raise FileNotFoundError("Unable to find whl metadata")


def create_virtualenv_from_pylock(
    package: str,
    build_path: str,
    lock_file: str
) -> None:
    """Create Python virtual environment using the package provided."""
    try:
        venv.create(build_path, with_pip=False)
        with open(package, "rb") as f:
            digest = hashlib.file_digest(f, "sha256")
            package_hash = digest.hexdigest()

        with tempfile.TemporaryDirectory() as tmp_dir_path:
            generated_pylockfile = os.path.join(tmp_dir_path, "pylock.toml")
            with open(lock_file, "r") as lock_file_fp:
                lock_file_content = tomlkit.parse(lock_file_fp.read())

            wheel_metadata = read_whl_metadata(package)
            new_package = {
                "name": wheel_metadata['name'],
                "version": wheel_metadata['version'],
                "archive":
                    {
                        "path": os.path.relpath(package, start=tmp_dir_path),
                        "hashes": {
                            "sha256": package_hash
                        }
                    }
            }

            lock_file_content['packages'].append(new_package)
            with open(generated_pylockfile, "w") as output_fp:
                output_fp.write(tomlkit.dumps(lock_file_content))

            args = [
                    "pip",
                    "install",
                    "--upgrade",
                    f"--target={build_path}",
                    "-r", generated_pylockfile
                ]
            subprocess.run(
                args,
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


def generate_hook_for_hidden(hidden_imports, top_level_package, additional_hooks_path):
    for package in hidden_imports:

        if package == top_level_package:
            continue

        freeze.create_hook_for_wheel(
            path=additional_hooks_path,
            strategy=lambda: package,
        )

class AbsFreezeConfigGenerator(abc.ABC):
    @abc.abstractmethod
    def build_specs(self, user_args: argparse.Namespace) -> freeze.SpecsData:
        """Build specs dataclass from the user_args."""

    @abc.abstractmethod
    def generate_freeze_config(self, specs: freeze.SpecsData) -> str:
        """Generate the string data from the specs dataclass."""


def use_license_file_from_user_args(
    args: argparse.Namespace
) -> Optional[pathlib.Path]:
    return typing.cast(Optional[pathlib.Path], args.license_file)


def extract_license_file_from_wheel(
    args: argparse.Namespace
) -> Optional[pathlib.Path]:
    md = get_package_metadata(args.python_package_file)
    generated_license_file = os.path.join(args.build_path, "license.txt")
    license_data = md.get_all('license')

    if license_data:
        data = license_data[0]
        with open(generated_license_file, "w", encoding="utf-8") as fp:
            fp.write(data)
        logger.info(
            "Extracted license file %s from %s",
            generated_license_file, args.python_package_file
        )
        return pathlib.Path(generated_license_file)
    return None


DEFAULT_LICENSE_FILE_FINDING_ORDER: List[
    Callable[[argparse.Namespace], Optional[pathlib.Path]],
] = [
    use_license_file_from_user_args,
    extract_license_file_from_wheel
]


def generate_cpack_config_file_string(
        source_application_path: str,
        args: argparse.Namespace,
        generator_type: Type[installer.CPackGenerator]
) -> str:
    generator = generator_type(
        args.app_name,
        frozen_application_path=source_application_path,
        output_path=args.dist,
        package_metadata=get_package_metadata(args.python_package_file),
        cl_args=args
    )
    generator.toml_config_file = args.config_file

    for strategy in DEFAULT_LICENSE_FILE_FINDING_ORDER:
        logger.debug("trying %s", strategy.__name__)
        result = strategy(args)
        if result:
            generator.license_file = result
            break
    else:
        logger.warning("No license file found")
    generator.package_vendor = defaults.DEFAULT_PACKAGE_VENDOR_STRING
    return generator.generate()


class AbsPlatformPackager(abc.ABC):
    @abc.abstractmethod
    def generate_config_file(
        self,
        source_application_path: str,
        args: argparse.Namespace
    ) -> pathlib.Path:
        """Generate config file for packaging."""

    @abc.abstractmethod
    def create_system_package(
        self,
        config_file: pathlib.Path,
        output_path: pathlib.Path = pathlib.Path("dist")
    ) -> pathlib.Path:
        """Create a system package."""


class AppleDMGPlatformPackager(AbsPlatformPackager):

    def generate_config_file(
        self,
        source_application_path: str,
        args: argparse.Namespace
    ) -> pathlib.Path:
        cpack_config_file = os.path.join(args.dist, "CPackConfig.cmake")
        with open(cpack_config_file, "w") as f:
            f.write(
                generate_cpack_config_file_string(
                    source_application_path,
                    args,
                    installer.cpack_config_generators['DragNDrop']
                )
            )
        return pathlib.Path(cpack_config_file)

    @staticmethod
    def locate_installer_artifact(path: pathlib.Path) -> pathlib.Path:
        for i in os.scandir(path):
            if i.is_dir():
                continue
            if i.name.endswith(".dmg"):
                return pathlib.Path(i.path)
        raise FileNotFoundError(f"No dmg file in {path}")

    def create_system_package(
        self,
        config_file: pathlib.Path,
        output_path: pathlib.Path = pathlib.Path("dist")
    ) -> pathlib.Path:
        installer.run_cpack(str(config_file), str(output_path))
        try:
            return self.locate_installer_artifact(output_path)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"No dmg found for {config_file}"
            ) from error


class AbsConfigFactory(abc.ABC):
    @abc.abstractmethod
    def get_freeze_config_generator(self) -> AbsFreezeConfigGenerator:
        """Create a freeze config."""

    @abc.abstractmethod
    def get_application_packager(self) -> AbsPlatformPackager:
        """Create a platform specific application packager."""


class WindowsFreezeConfigGenerator(AbsFreezeConfigGenerator):

    SpecsDataClass = freeze.DefaultGenerateSpecs.SpecsDataClass
    FreezeConfigClass = freeze.DefaultGenerateSpecs

    def __init__(self) -> None:
        super().__init__()
        self.python_package_file: Optional[pathlib.Path] = None
        self.additional_hooks_path: Optional[str] = None

    def build_specs(self, user_args: argparse.Namespace) -> freeze.SpecsData:
        package_env = os.path.join(user_args.build_path, "speedwagon")
        logo =\
            os.path.abspath(
                os.path.join(package_env, "speedwagon", 'logo.png')
            )
        data_files = [
            (
                os.path.abspath(user_args.app_icon).replace(os.sep, '/'),
                'speedwagon'
            ),
            (logo, 'speedwagon'),
        ]
        hook_paths: str = os.path.join(user_args.build_path, "hooks")
        self.additional_hooks_path = hook_paths

        self.python_package_file = user_args.python_package_file

        hidden_imports: List[str] = [
            get_package_top_level(
                user_args.python_package_file
            )
        ]
        if user_args.hidden_imports:
            hidden_imports.extend(user_args.hidden_imports)

        specs = self.SpecsDataClass(
            bootstrap_script=os.path.abspath(user_args.app_bootstrap_script),
            app_executable_name=user_args.app_executable_name,
            data_files=data_files,
            collection_name=defaults.DEFAULT_COLLECTION_NAME,
            bundle_name=user_args.app_name,
            app_icon=os.path.abspath(user_args.app_icon),
            installer_icon=os.path.abspath(user_args.installer_icon),
            top_level_package_folder_name=get_package_top_level(
                user_args.python_package_file
            ),
            hidden_imports=hidden_imports,
            hookspath=[
                os.path.abspath(os.path.dirname(__file__)),
                os.path.abspath(hook_paths)
            ],
            search_paths=[package_env],
        )
        return specs

    def generate_freeze_config(self, specs: freeze.SpecsData) -> str:
        if self.additional_hooks_path is None:
            raise ValueError("No hooks path specified")

        if not os.path.exists(self.additional_hooks_path):
            os.makedirs(self.additional_hooks_path)

        if self.python_package_file is None:
            raise ValueError("No python package file specified")
        else:
            package_file: pathlib.Path = self.python_package_file
        top_level_package = get_package_top_level(package_file)
        generate_hook_for_hidden(specs.hidden_imports, top_level_package, self.additional_hooks_path)

        freeze.create_hook_for_wheel(
            path=self.additional_hooks_path,
            strategy=lambda: top_level_package,
        )

        specs_file_generator = self.FreezeConfigClass(specs)
        return specs_file_generator.generate()


class MacFreezeConfigGenerator(AbsFreezeConfigGenerator):
    SpecsDataClass = freeze.DefaultGenerateSpecs.SpecsDataClass
    FreezeConfigClass = freeze.DefaultGenerateSpecs

    def __init__(self) -> None:
        super().__init__()
        self.python_package_file: Optional[pathlib.Path] = None
        self.additional_hooks_path: Optional[str] = None

    def build_specs(self, user_args: argparse.Namespace) -> freeze.SpecsData:
        package_env = os.path.join(user_args.build_path, "speedwagon")
        logo = os.path.abspath(
            os.path.join(package_env, "speedwagon", 'logo.png')
        )
        data_files = [
            (
                os.path.abspath(user_args.app_icon).replace(os.sep, '/'),
                'speedwagon'),
            (logo, 'speedwagon'),
        ]
        hook_path: str = os.path.join(
            user_args.build_path,
            "hooks"
        )
        self.additional_hooks_path = hook_path
        self.python_package_file = user_args.python_package_file
        hidden_imports: List[str] = [
            get_package_top_level(
                user_args.python_package_file
            )
        ]
        if user_args.hidden_imports:
            hidden_imports.extend(user_args.hidden_imports)

        specs = self.SpecsDataClass(
            bootstrap_script=os.path.abspath(user_args.app_bootstrap_script),
            app_executable_name=user_args.app_executable_name,
            data_files=data_files,
            collection_name=defaults.DEFAULT_COLLECTION_NAME,
            bundle_name=f"{user_args.app_name}.app",
            app_icon=os.path.abspath(user_args.app_icon),
            installer_icon=os.path.abspath(user_args.installer_icon),
            top_level_package_folder_name=get_package_top_level(
                user_args.python_package_file
            ),
            hidden_imports=hidden_imports,
            hookspath=[
                os.path.abspath(os.path.dirname(__file__)),
                os.path.abspath(hook_path)
            ],
            search_paths=[package_env],
        )
        return specs

    def generate_freeze_config(self, specs: freeze.SpecsData) -> str:
        if self.additional_hooks_path is None:
            raise ValueError("No hooks path specified")

        if not os.path.exists(self.additional_hooks_path):
            os.makedirs(self.additional_hooks_path)
        if not self.python_package_file:
            raise ValueError("No python package file specified")
        else:
            package_file: pathlib.Path = self.python_package_file

        top_level_package = get_package_top_level(package_file)
        generate_hook_for_hidden(specs.hidden_imports, top_level_package, self.additional_hooks_path)
        freeze.create_hook_for_wheel(
            path=self.additional_hooks_path,
            strategy=lambda: top_level_package,
        )
        specs_file_generator = self.FreezeConfigClass(specs)
        return specs_file_generator.generate()


class MSIPlatformPackager(AbsPlatformPackager):

    def generate_config_file(
        self,
        source_application_path: str,
        args: argparse.Namespace
    ) -> pathlib.Path:

        cpack_config_file = os.path.join(args.dist, "CPackConfig.cmake")
        with open(cpack_config_file, "w") as f:
            f.write(
                generate_cpack_config_file_string(
                    source_application_path,
                    args,
                    installer.cpack_config_generators['Wix']
                )
            )
        return pathlib.Path(cpack_config_file)

    @staticmethod
    def locate_installer_artifact(path: pathlib.Path) -> pathlib.Path:
        for i in os.scandir(path):
            if i.is_dir():
                continue
            if i.name.endswith(".msi"):
                return pathlib.Path(i.path)
        raise FileNotFoundError(f"No .msi found in {path}")

    def create_system_package(
        self,
        config_file: pathlib.Path,
        output_path: pathlib.Path = pathlib.Path("dist")
    ) -> pathlib.Path:
        installer.run_cpack(str(config_file), str(output_path))
        try:
            return self.locate_installer_artifact(output_path)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                f"No .msi found for {config_file}"
            ) from error


class WindowsConfigFactory(AbsConfigFactory):
    def get_freeze_config_generator(self) -> AbsFreezeConfigGenerator:
        return WindowsFreezeConfigGenerator()

    def get_application_packager(self) -> AbsPlatformPackager:
        return MSIPlatformPackager()


class MacConfigFactory(AbsConfigFactory):
    def get_freeze_config_generator(self) -> AbsFreezeConfigGenerator:
        return MacFreezeConfigGenerator()

    def get_application_packager(self) -> AbsPlatformPackager:
        return AppleDMGPlatformPackager()


config_os_mappings: Mapping[str, AbsConfigFactory] = {
    "darwin": MacConfigFactory(),
    "win32": WindowsConfigFactory()
}


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
        if len(args.requirement) == 1 and pathlib.Path(args.requirement[0]).name == "pylock.toml":
            create_virtualenv_from_pylock(
                args.python_package_file,
                package_env,
                args.requirement[0]
            )
        else:
            create_virtualenv(
                args.python_package_file,
                package_env,
                *args.requirement,
            )

    specs_file_name = os.path.join(args.build_path, "specs.spec")
    config_generator = config_os_mappings.get(sys.platform)
    if config_generator is None:
        raise ValueError(f"Unsupported platform: {sys.platform}")
    freeze_config_generator = config_generator.get_freeze_config_generator()

    with open(specs_file_name, "w", encoding="utf-8") as spec_file:
        spec_file.write(
            freeze_config_generator.generate_freeze_config(
                freeze_config_generator.build_specs(args)
            )
        )
    with open(specs_file_name) as f:
        print(f.read())

    frozen_app_build_path = os.path.join(args.build_path, "frozen")

    freeze.freeze_env(
        specs_file=specs_file_name,
        work_path=os.path.join(args.build_path, 'workpath'),
        dest=frozen_app_build_path
    )
    expected_frozen_path = freeze.find_frozen_folder(frozen_app_build_path, args=args)
    if not expected_frozen_path:
        raise FileNotFoundError(
            "Unable to find folder containing frozen application"
        )
    platform_packager = config_generator.get_application_packager()
    packaging_config_file = platform_packager.generate_config_file(
        source_application_path=expected_frozen_path,
        args=args
    )
    package_file =\
        platform_packager.create_system_package(packaging_config_file)

    print(f"Created {package_file}")


if __name__ == '__main__':
    main()
