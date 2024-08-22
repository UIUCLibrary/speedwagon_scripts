import argparse
import os.path
import pathlib
from unittest.mock import Mock, mock_open, patch

import pytest

from package_speedwagon import package_speedwagon, installer


class TestAppleDMGPlatformPackager:

    @pytest.fixture
    def packager(self):
        return package_speedwagon.AppleDMGPlatformPackager()

    def test_generate_config_file(self, monkeypatch, packager):
        cpack_packagers = {"DragNDrop": Mock()}
        monkeypatch.setattr(
            installer, "cpack_config_generators",
            cpack_packagers
        )
        monkeypatch.setattr(package_speedwagon, "get_package_metadata", Mock())
        with patch("builtins.open", mock_open()):
            assert packager.generate_config_file(
                "my/frozen/app/path",
                argparse.Namespace(
                    app_name="dummy",
                    dist="dummy_dist",
                    config_file='pyproject.toml',
                    python_package_file="package_file.py"
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


class TestMSIPlatformPackager:
    @pytest.fixture
    def packager(self):
        return package_speedwagon.MSIPlatformPackager()

    def test_generate_config_file(self, monkeypatch, packager):
        monkeypatch.setattr(
            installer, "cpack_config_generators", {"Wix": Mock()}
        )

        monkeypatch.setattr(
            package_speedwagon,
            "get_package_metadata",
            Mock(name="get_package_metadata")
        )

        with patch("builtins.open", mock_open()):
            assert packager.generate_config_file(
                "somepath",
                argparse.Namespace(
                    app_name="dummy",
                    dist="dummy_dist",
                    config_file='pyproject.toml',
                    python_package_file="package_file.whl"
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
