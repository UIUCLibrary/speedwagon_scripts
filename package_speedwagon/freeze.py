import abc
import argparse
import dataclasses
import os
import sys
import typing
from typing import Callable, Optional, Dict, List, Generic, TypeVar, Tuple, \
    Type, Any

import PyInstaller.__main__

from package_speedwagon.defaults import DEFAULT_COLLECTION_NAME


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


class MetaClassWithAbstractClassAttrs(abc.ABCMeta):
    def __call__(cls, *args: object, **kwargs: object) -> object:
        instance: object = super().__call__(*args, **kwargs)
        abstract_attributes = {
            name
            for name in dir(instance)
            if getattr(
                getattr(instance, name), '__is_abstract_attribute__', False
            )
        }
        if abstract_attributes:
            raise NotImplementedError(
                f"Can't instantiate abstract class {cls.__name__} with"
                f" abstract attributes: {', '.join(abstract_attributes)}"
            )
        return instance


T = TypeVar('T')
R = TypeVar('R')
DataType = TypeVar('DataType')


def abstract_attribute(obj: Optional[Callable[[Any], T]] = None) -> T:
    """Create an attribute an abstract class attribute.

    provides the extra attribute __is_abstract_attribute__
    """
    class DummyAttribute:
        pass
    _obj = typing.cast(Any, obj)
    if obj is None:
        _obj = DummyAttribute()
    _obj.__is_abstract_attribute__ = True
    return typing.cast(T, _obj)


class AbsGenerateSpecs(
    abc.ABC,
    Generic[DataType],
    metaclass=MetaClassWithAbstractClassAttrs
):
    SpecsDataClass: Type[DataType] = abstract_attribute()
    key_mapping: Dict[str, str] = {}

    @abc.abstractmethod
    def generate(self) -> str:
        """Create the text for a new specs config file use to freeze."""

    @classmethod
    def map_data(cls, fields: List[Tuple[str, R]]) -> Dict[str, R]:
        def mapping(key: str, value: R) -> Tuple[str, R]:
            if key in cls.key_mapping:
                return cls.key_mapping[key], value
            return key, value
        return dict(map(lambda field: mapping(*field), fields))


@dataclasses.dataclass
class SpecsData:
    app_executable_name: str
    collection_name: str
    bundle_name: str

    installer_icon: Optional[str] = None
    bootstrap_script: Optional[str] = None
    app_icon: Optional[str] = None
    search_paths: List[str] = dataclasses.field(default_factory=list)
    data_files: List[Tuple[str, str]] = dataclasses.field(default_factory=list)
    hookspath: List[str] = dataclasses.field(default_factory=list)
    top_level_package_folder_name: Optional[str] = None


class DefaultGenerateSpecs(AbsGenerateSpecs[SpecsData]):
    """Generator for default specs document"""
    # ruff: noqa: E501
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
             hiddenimports=['%(hidden_imports)s'],
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
    SpecsDataClass = SpecsData
    key_mapping = {
        "data_files": "datas",
        'top_level_package_folder_name': "hidden_imports"
    }

    def __init__(self, data: SpecsData) -> None:
        super().__init__()
        self.data = data

    def generate(self) -> str:
        return DefaultGenerateSpecs.SPEC_TEMPLATE % dataclasses.asdict(
            self.data, dict_factory=self.map_data
        )