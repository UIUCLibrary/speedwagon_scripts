import argparse
import os.path
import pathlib
from typing import List
from unittest.mock import Mock, mock_open, patch

import pytest

from package_speedwagon import package_speedwagon, installer, utils


class TestAppleDMGPlatformPackager:

    @pytest.fixture
    def packager(self):
        return package_speedwagon.AppleDMGPlatformPackager()

    def test_generate_config_file(
        self,
        monkeypatch,
        packager,
        make_command_line_args
    ):
        cpack_packagers = {"DragNDrop": Mock()}
        monkeypatch.setattr(
            installer, "cpack_config_generators",
            cpack_packagers
        )
        monkeypatch.setattr(package_speedwagon, "get_package_metadata", Mock())
        monkeypatch.setattr(
            package_speedwagon,
            "DEFAULT_LICENSE_FILE_FINDING_ORDER",
            []
        )
        with patch("builtins.open", mock_open()):
            assert packager.generate_config_file(
                "my/frozen/app/path",
                make_command_line_args(
                    [
                        "--app-name=dummy",
                        "--dist=dummy_dist",
                        "--config-file=pyproject.toml",
                        "somewheel.whl"
                    ]
                )
            ).name.endswith("CPackConfig.cmake")

    def test_create_system_package(self, packager, monkeypatch):
        packager.locate_installer_artifact =\
            Mock(return_value=pathlib.Path("dummy.dmg"))

        monkeypatch.setattr(installer, 'run_cpack', Mock(name="run_cpack"))
        assert packager.create_system_package(
            Mock(name='config_file'), Mock(name="output_path")
        ) == pathlib.Path("dummy.dmg")

    def test_create_system_package_failing_to_find_artifact(
        self,
        packager,
        monkeypatch
    ):
        packager.locate_installer_artifact =\
            Mock(side_effect=FileNotFoundError)

        monkeypatch.setattr(installer, 'run_cpack', Mock(name="run_cpack"))
        with pytest.raises(FileNotFoundError) as error:
            packager.create_system_package(
                Mock(name='config_file'), Mock(name="output_path")
            )
        assert "No dmg found" in str(error.value)

    def test_locate_installer_artifact(self, monkeypatch):

        valid_item = Mock(
            is_dir=Mock(return_value=False),
            path=os.path.join("somepath", "something.dmg"),
        )
        valid_item.name = "something.dmg"

        monkeypatch.setattr(
            package_speedwagon.os, "scandir",
            Mock(return_value=[
                Mock(
                    is_dir=Mock(return_value=True),
                    path=os.path.join("somepath", "subfolder"),
                ),
                valid_item
            ]
            )
        )
        assert (
                package_speedwagon
                .AppleDMGPlatformPackager
                .locate_installer_artifact(
                    pathlib.Path(".")
                ).name == "something.dmg"
        )

    def test_locate_installer_artifact_throws_on_failure(self, monkeypatch):
        monkeypatch.setattr(
            package_speedwagon.os, "scandir",
            Mock(
                return_value=[
                    Mock(
                        is_dir=Mock(return_value=True),
                        path=os.path.join("somepath", "subfolder"),
                    ),
                ]
            )
        )
        packager = package_speedwagon.AppleDMGPlatformPackager
        with pytest.raises(FileNotFoundError):
            packager.locate_installer_artifact(pathlib.Path("."))


@pytest.fixture()
def make_command_line_args(monkeypatch):
    def _make_command_line_args(args: List[str]):
        with monkeypatch.context() as ctx:
            ctx.setattr(pathlib.Path, "is_file", Mock(return_value=True))
            ctx.setattr(pathlib.Path, "exists", Mock(return_value=True))
            ctx.setattr(utils, "read_toml_data", Mock(return_value="data"))
            return package_speedwagon.get_args_parser().parse_args(args)
    return _make_command_line_args


class TestMSIPlatformPackager:
    @pytest.fixture
    def packager(self):
        return package_speedwagon.MSIPlatformPackager()

    def test_generate_config_file(
        self,
        monkeypatch,
        packager,
        make_command_line_args
    ):
        monkeypatch.setattr(
            installer, "cpack_config_generators", {"Wix": Mock()}
        )

        monkeypatch.setattr(
            package_speedwagon,
            "get_package_metadata",
            Mock(name="get_package_metadata")
        )
        monkeypatch.setattr(
            package_speedwagon,
            "DEFAULT_LICENSE_FILE_FINDING_ORDER",
            []
        )
        with patch("builtins.open", mock_open()):

            assert packager.generate_config_file(
                "somepath",
                make_command_line_args(
                    [
                        "--app-name=dummy",
                        "--dist=dummy_dist",
                        "--config-file=pyproject.toml",
                        "package_file.whl",
                    ]
                )
            ).name == "CPackConfig.cmake"

    def test_create_system_package(self, monkeypatch, packager):
        packager.locate_installer_artifact =\
            Mock(return_value=pathlib.Path("dummy.msi"))

        monkeypatch.setattr(installer, 'run_cpack', Mock(name="run_cpack"))
        assert packager.create_system_package(
            Mock(name='config_file'), Mock(name="output_path")
        ) == pathlib.Path("dummy.msi")

    def test_create_system_package_raises_on_failure(
        self,
        monkeypatch,
        packager
    ):
        packager.locate_installer_artifact =\
            Mock(side_effect=FileNotFoundError)

        monkeypatch.setattr(installer, 'run_cpack', Mock(name="run_cpack"))
        with pytest.raises(FileNotFoundError):
            packager.create_system_package(
                Mock(name='config_file'), Mock(name="output_path")
            )

    def test_locate_installer_artifact(self, monkeypatch):
        valid_item = Mock(
            is_dir=Mock(return_value=False),
            path=os.path.join("somepath", "something.msi"),
        )
        valid_item.name = "something.msi"

        monkeypatch.setattr(
            package_speedwagon.os, "scandir",
            Mock(return_value=[
                Mock(
                    is_dir=Mock(return_value=True),
                    path=os.path.join("somepath", "subfolder"),
                ),
                valid_item
            ]
            )
        )
        packager = package_speedwagon.MSIPlatformPackager
        assert packager.locate_installer_artifact(
            pathlib.Path('.')
        ).name == "something.msi"

    def test_locate_installer_artifact_failure_raises(self, monkeypatch):

        monkeypatch.setattr(
            package_speedwagon.os, "scandir",
            Mock(return_value=[
                Mock(
                    is_dir=Mock(return_value=True),
                    path=os.path.join("somepath", "subfolder"),
                ),
            ]
            )
        )
        with pytest.raises(FileNotFoundError):
            package_speedwagon.MSIPlatformPackager().locate_installer_artifact(
                pathlib.Path('.')
            )


class TestWindowsFreezeConfigGenerator:
    def test_build_specs_uses_specs_data_class(self, monkeypatch):
        config_generator = package_speedwagon.WindowsFreezeConfigGenerator()

        monkeypatch.setattr(
            package_speedwagon, "get_package_top_level",
            Mock(name="get_package_top_level", return_value=".")
        )

        config_generator.SpecsDataClass = Mock(name="SpecsDataClass")
        config_generator.build_specs(
            user_args=argparse.Namespace(
                build_path="build",
                app_icon="icon.ico",
                installer_icon="installer.ico",
                python_package_file="package_file.whl",
                app_bootstrap_script="bootstrap.py",
                app_name="dummy_app",
                app_executable_name="dummy",
            )
        )
        config_generator.SpecsDataClass.assert_called_once()

    def test_generate_freeze_config(self, monkeypatch):
        config_generator = package_speedwagon.WindowsFreezeConfigGenerator()
        config_generator.FreezeConfigClass.generate = Mock(
            name="FreezeConfigClass.generate",
            return_value="something"
        )
        monkeypatch.setattr(os.path, "exists", Mock(return_value=True))
        monkeypatch.setattr(
            package_speedwagon.freeze, "create_hook_for_wheel",
            Mock(name="create_hook_for_wheel")
        )
        config_generator.additional_hooks_path = "hooks"

        specs = Mock()
        config_generator.generate_freeze_config(specs)
        config_generator.FreezeConfigClass.generate.assert_called_once()


class TestMacFreezeConfigGenerator:
    def test_build_specs_uses_specs_data_class(self, monkeypatch):
        config_generator = package_speedwagon.MacFreezeConfigGenerator()

        monkeypatch.setattr(
            package_speedwagon, "get_package_top_level",
            Mock(name="get_package_top_level", return_value=".")
        )
        config_generator.SpecsDataClass = Mock(name="SpecsDataClass")
        config_generator.build_specs(
            user_args=argparse.Namespace(
                build_path="build",
                app_icon="icon.ico",
                installer_icon="installer.ico",
                python_package_file="package_file.whl",
                app_bootstrap_script="bootstrap.py",
                app_name="dummy_app",
                app_executable_name="dummy",
            )
        )
        config_generator.SpecsDataClass.assert_called_once()

    def test_generate_freeze_config(self, monkeypatch):
        config_generator = package_speedwagon.MacFreezeConfigGenerator()
        config_generator.additional_hooks_path = "hooks"
        specs = Mock(name="specs")
        monkeypatch.setattr(os.path, "exists", Mock(return_value=True))

        monkeypatch.setattr(
            package_speedwagon, "get_package_top_level",
            Mock(name="get_package_top_level", return_value=".")
        )

        config_generator.FreezeConfigClass.generate =\
            Mock(name="FreezeConfigClass.generate")

        monkeypatch.setattr(
            package_speedwagon.freeze, "create_hook_for_wheel",
            Mock(name="create_hook_for_wheel")
        )

        config_generator.generate_freeze_config(specs)
        config_generator.FreezeConfigClass.generate.assert_called_once()


def test_extract_license_file_from_wheel_returns_none_if_absent(
    make_command_line_args,
    monkeypatch
):
    monkeypatch.setattr(
        package_speedwagon,
        "get_package_metadata",
        Mock(
            return_value=Mock(
                name="get_package_metadata",
                get_all=Mock(
                    name="get_all",
                    return_value=[]
                )
            )
        )
    )
    assert package_speedwagon.extract_license_file_from_wheel(
        make_command_line_args([
            "dummy.whl"
        ])
    ) is None


def test_extract_license_file_from_wheel_write_to_file(
    make_command_line_args,
    monkeypatch
):
    monkeypatch.setattr(
        package_speedwagon,
        "get_package_metadata",
        Mock(
            return_value=Mock(
                name="get_package_metadata",
                get_all=Mock(
                    name="get_all",
                    return_value=['Dummy license file data']
                )
            )
        )
    )
    m = mock_open()
    with patch("builtins.open", m):
        package_speedwagon.extract_license_file_from_wheel(
            make_command_line_args([
                "dummy.whl"
            ])
        )
    m().write.assert_called_once_with('Dummy license file data')


def test_use_license_file_from_user_args(make_command_line_args):
    assert package_speedwagon.use_license_file_from_user_args(
        make_command_line_args(['dummy.whl', "--license-file=mylicense.txt"])
    ).name == "mylicense.txt"


def test_use_license_file_from_user_args_returns_none_if_nothing(
    make_command_line_args
):
    assert package_speedwagon.use_license_file_from_user_args(
        make_command_line_args(['dummy.whl'])
    ) is None


class TestTomlFileAction:
    @pytest.fixture()
    def parser(self):
        my_parser = argparse.ArgumentParser()
        my_parser.error = Mock('error')
        return my_parser

    @pytest.fixture()
    def action(self):
        my_action = package_speedwagon.TomlFileAction("a", "x")
        my_action.check_valid_toml_file = Mock(return_value=True)
        return my_action

    def test_exists(self, action, parser):

        namespace = argparse.Namespace()
        value = Mock(
            name='values',
            spec_set=pathlib.Path,
            return_value="ddd",
            exists=Mock(return_value=True)
        )
        action(
            parser=parser,
            namespace=namespace,
            values=value
        )
        assert namespace.x == value
        parser.error.assert_not_called()

    def test_not_exists(self, action, parser):
        namespace = argparse.Namespace()
        value = Mock(
            name='values',
            spec_set=pathlib.Path,
            return_value="ddd",
            exists=Mock(return_value=False)
        )
        action(
            parser=parser,
            namespace=namespace,
            values=value
        )
        assert namespace.x == value
        parser.error.assert_called()

    def test_not_valid_toml(self, action, parser):
        namespace = argparse.Namespace()
        value = Mock(
            name='values',
            spec_set=pathlib.Path,
            return_value="ddd",
            exists=Mock(return_value=False)
        )
        action.check_valid_toml_file = Mock(return_value=False)
        action(
            parser=parser,
            namespace=namespace,
            values=value
        )
        assert namespace.x == value
        parser.error.assert_called()
