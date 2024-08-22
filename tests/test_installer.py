import os
import pathlib
from unittest.mock import Mock, patch, mock_open

import pytest
import packaging.version
import platform
from package_speedwagon import installer, utils


def test_get_license_get_result_of_first_successful_callable_skips_rest():
    alternative_license_getting_strategy = Mock(return_value='dummy_license 2')
    successful_license_getting_strategy = Mock(return_value='dummy_license')
    result = installer.get_license(
        strategies_list=[
            successful_license_getting_strategy,
            alternative_license_getting_strategy,
        ]
    )
    alternative_license_getting_strategy.assert_not_called()
    assert result == 'dummy_license'


def test_get_license_get_result_of_first_successful_callable():
    unsuccessful_license_getting_strategy = Mock(return_value=None)
    successful_license_getting_strategy = Mock(return_value='dummy_license')
    result = installer.get_license(
        strategies_list=[
            unsuccessful_license_getting_strategy,
            successful_license_getting_strategy
        ]
    )
    successful_license_getting_strategy.assert_called_once()
    assert result == 'dummy_license'


def test_get_license_throws_file_not_found_exception_if_exhausts_strategies():
    with pytest.raises(FileNotFoundError):
        installer.get_license(
            strategies_list=[Mock(return_value=None)]
        )


class TestCopyLicenseFile:
    def test_create_calls_write_file(self):
        output_path = os.path.join("dummy", "path", "license.txt")
        strategy = installer.CopyLicenseFile("License", output_path)
        strategy.pre_check = Mock(return_value=True)
        strategy.copy_file = Mock(return_value=None)
        strategy()
        strategy.copy_file.assert_called_once()

    @pytest.mark.parametrize(
        "file_exists, expected_validity",
        [
            (False, False),
            (True, True)
        ]
    )
    def test_precheck_failure_not_when_not(
            self,
            monkeypatch,
            file_exists,
            expected_validity
    ):
        input_path = os.path.join("source", "path", "license.txt")
        output_path = os.path.join("output", "path", "license.txt")
        monkeypatch.setattr(
            installer.os.path,
            "exists",
            Mock(return_value=file_exists)
        )
        strategy = installer.CopyLicenseFile(input_path, output_path)
        assert strategy.pre_check() is expected_validity

    def test_call_returns_value_on_success(self, monkeypatch):
        input_path = os.path.join("source", "path", "license.txt")
        output_path = os.path.join("output", "path", "license.txt")
        monkeypatch.setattr(
            installer.os.path,
            "exists",
            Mock(return_value=True)
        )
        strategy = installer.CopyLicenseFile(input_path, output_path)
        strategy.copy_file = Mock(name="copy_file")
        assert strategy()

    def test_call_returns_none_when_fail_precheck(self, monkeypatch):
        input_path = os.path.join("source", "path", "license.txt")
        output_path = os.path.join("output", "path", "license.txt")
        monkeypatch.setattr(
            installer.os.path, "exists",
            Mock(return_value=False)
        )
        strategy = installer.CopyLicenseFile(input_path, output_path)
        assert strategy() is None


class TestGenerateNoLicenseGivenFile:
    def test_call_calls_write_license_file(self):
        output_path = os.path.join("dummy", "path", "license.txt")
        strategy = installer.GenerateNoLicenseGivenFile(output_path)
        strategy.write_license_file = Mock()
        strategy()
        strategy.write_license_file.assert_called_once()

    def test_write_license_file_opens_file(self):
        output_path = os.path.join("dummy", "path", "license.txt")
        strategy = installer.GenerateNoLicenseGivenFile(output_path)
        m = mock_open()
        with patch('package_speedwagon.installer.open', m):
            strategy.write_license_file()
        m.assert_called_once()


class TestLocateLicenseFile:
    def test_call(self):
        strategy = installer.LocateLicenseFile()
        strategy.locate_license_file = Mock(return_value="license")
        result = strategy()
        assert result.endswith("license")

    def test_locate_license_file(self, monkeypatch):
        strategy = installer.LocateLicenseFile()
        strategy.search_paths = ["somewhere"]
        monkeypatch.setattr(
            installer.os.path,
            "exists",
            Mock(return_value=True)
        )
        assert strategy.locate_license_file() == os.path.join(
            "somewhere",
            strategy.potential_file_name
        )

    def test_locate_license_file_returns_none_when_exhausts_search_path(
        self,
        monkeypatch
    ):
        strategy = installer.LocateLicenseFile()
        strategy.search_paths = []
        monkeypatch.setattr(
            installer.os.path,
            "exists",
            Mock(return_value=True)
        )
        assert strategy.locate_license_file() is None


def test_get_cpack_path():
    strategies_list = [
        Mock(return_value="cpack_path")
    ]
    assert installer.get_cpack_path(strategies_list) == 'cpack_path'


def test_get_cpack_path_first_successful():
    strategies_list = [
        Mock(side_effect=FileNotFoundError),
        Mock(return_value='first'),
        Mock(return_value='second'),
    ]
    assert installer.get_cpack_path(strategies_list) == 'first'
    strategies_list[2].assert_not_called()


def test_get_cpack_path_throws_on_failure():
    strategies_list = [
        Mock(side_effect=FileNotFoundError),
    ]
    with pytest.raises(FileNotFoundError):
        installer.get_cpack_path(strategies_list)


def test_get_cpack_path_uses_default_strategies_with_no_args():
    installer.DEFAULT_CPACK_FINDING_STRATEGIES = [
        Mock(return_value='default cpack'),
    ]
    assert installer.get_cpack_path() == 'default cpack'


@pytest.mark.parametrize(
    "generator_name",
    installer.cpack_config_generators.keys()
)
def test_cpack_generators_app_name(monkeypatch, generator_name):
    metadata_content = {
        'author_email': ["<EMAIL>"],
        "version": "0.1.1"
    }
    package_metadata = Mock(
        get=metadata_content.get,
        get_all=metadata_content.get,
        __getitem__=lambda _self, name: metadata_content[name]
    )
    cpack_generator = installer.cpack_config_generators[generator_name](
        app_name="dummy app",
        frozen_application_path="frozen path",
        output_path="output path",
        package_metadata=package_metadata,
        cl_args=Mock(installer_icon="dummy.icon")
    )
    cpack_generator.get_license_path = Mock(return_value="dummy_license")
    monkeypatch.setattr(
        installer,
        "generate_package_description_file",
        lambda *args, **kwargs: "description_file.txt"
    )
    assert 'set(CPACK_PACKAGE_NAME "dummy app")' in cpack_generator.generate()


class TestMacOSDragNDropPackageGenerator:
    @pytest.mark.parametrize(
        "is_prerelease, is_devrelease, pre, dev, expect_excerpt",
        [
            (
                True,
                False,
                "123",
                None,
                "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}.123-macos"
            ),
            (
                False,
                False,
                None,
                None,
                "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}-macos"
            ),
            (
                True,
                True,
                None,
                "2",
                "${CPACK_PACKAGE_NAME}-${CPACK_PACKAGE_VERSION}.dev2-macos"
            )
        ]
    )
    def test_get_cpack_package_file_name(
        self,
        is_prerelease,
        is_devrelease,
        pre,
        dev,
        expect_excerpt
    ):
        metadata_content = {
            'author_email': ["<EMAIL>"],
            "version": "0.1.1"
        }
        package_metadata = Mock(
            get=metadata_content.get,
            get_all=metadata_content.get,
            __getitem__=lambda _self, name: metadata_content[name]
        )
        cpack_generator = installer.MacOSDragNDropPackageGenerator(
            app_name="dummy app",
            frozen_application_path="frozen path",
            output_path="output path",
            package_metadata=package_metadata,
            cl_args=Mock(installer_icon="dummy.icon")
        )
        version = Mock(
            spec=packaging.version,
            is_prerelease=is_prerelease,
            is_devrelease=is_devrelease,
            pre=pre,
            dev=dev,
        )
        result = cpack_generator.get_cpack_package_file_name(
            version=version
        )
        assert expect_excerpt in result


class TestWixToolsetPackageGenerator:
    @pytest.fixture
    def cpack_generator(self):
        metadata_content = {
            'author_email': ["<EMAIL>"],
            "version": "0.1.1"
        }
        return installer.WixToolsetPackageGenerator(
            app_name="dummy app",
            frozen_application_path="frozen path",
            output_path="output path",
            package_metadata=Mock(
                get=metadata_content.get,
                get_all=metadata_content.get,
                __getitem__=lambda _self, name: metadata_content[name]
            ),
            cl_args=Mock(installer_icon="dummy.icon")
        )

    def test_get_license_path_uses_default_license_find_strategies(
        self,
    ):
        metadata_content = {
            'author_email': ["<EMAIL>"],
            "version": "0.1.1"
        }

        class PatchedGenerator(installer.WixToolsetPackageGenerator):
            default_license_find_strategies = [
                Mock(return_value="dummy_license")
            ]
        cpack_generator = PatchedGenerator(
            app_name="dummy app",
            frozen_application_path="frozen path",
            output_path="output path",
            package_metadata=Mock(
                get=metadata_content.get,
                get_all=metadata_content.get,
                __getitem__=lambda _self, name: metadata_content[name]
            ),
            cl_args=Mock(installer_icon="dummy.icon")
        )
        cpack_generator.get_license_path()
        cpack_generator.default_license_find_strategies[0].assert_called_once()

    def test_default_license_finding_strategies_copy_first(
        self,
        cpack_generator
    ):
        assert isinstance(
            cpack_generator.default_license_find_strategies[0],
            installer.CopyLicenseFile
        )

    @pytest.mark.parametrize(
        "architecture, expected_string",
        [
            (
                ('64bit', ''),
                "win64"
            ),
            (
                ('32bit', ''),
                "win32"
            )
        ]
    )
    def test_get_cpack_system_name(
        self,
        cpack_generator,
        monkeypatch,
        architecture,
        expected_string
    ):
        monkeypatch.setattr(platform, "architecture", lambda: architecture)
        assert expected_string == cpack_generator.get_cpack_system_name()

    def test_get_cpack_system_name_unknown_platform_raises(
        self,
        cpack_generator,
        monkeypatch
    ):
        with pytest.raises(ValueError) as exc:
            monkeypatch.setattr(
                platform,
                "architecture",
                lambda: ("something else", "")
            )
            cpack_generator.get_cpack_system_name()
        assert "something else" in str(exc.value)

    def test_get_pyproject_toml_metadata_windows_packager_data(
        self,
        cpack_generator,
        monkeypatch
    ):
        cpack_generator.toml_config_file = Mock(
            spec_set=pathlib.Path,
            exists=Mock(return_value=True),
        )
        monkeypatch.setattr(
            utils,
            "read_toml_data",
            lambda *_, **__: {
                "tool": {
                    "windows_standalone_packager": {
                        "cpack_config_variables": {
                            "CPACK_SOMETHING": "YES"
                        }
                    }
                }
            }
        )
        assert (
            "CPACK_SOMETHING" in
            cpack_generator.get_pyproject_toml_metadata_windows_packager_data()
        )

    # def test_read_toml_data(self, cpack_generator):
    #     m = mock_open(read_data=b'')
    #     mock_load = Mock()
    #     with patch('package_speedwagon.installer.open', m):
    #         installer.read_toml_data(
    #             pathlib.Path('dummy.toml'),
    #             loader=mock_load
    #         )
    #     mock_load.assert_called_once()

    @pytest.mark.parametrize(
        "arch, expected_key, expected_value",
        [
            (("64bit", ''), "cpack_wix_architecture", "x64"),
            (("64bit", ''), "cpack_wix_sizeof_void_p", "8"),
            (("32bit", ''), "cpack_wix_sizeof_void_p", "4"),
            (("32bit", ''), "cpack_wix_architecture", "x86"),
            (("something_wacky", ''), "cpack_wix_sizeof_void_p", None),
            (("something_wacky", ''), "cpack_wix_architecture", None),
        ]
    )
    def test_get_wix_specific_configs(
        self, cpack_generator,
        arch, expected_key, expected_value
    ):
        wix_specific_configs =\
            cpack_generator.get_wix_specific_configs(architecture=arch)

        assert wix_specific_configs[expected_key] == expected_value, \
            (f"{arch} key: {expected_key}, "
             f"expect value: {expected_value}, "
             f"actual: {wix_specific_configs[expected_key]}")


def test_locate_cpack_on_path_env_var_throws_on_not_finding(monkeypatch):
    monkeypatch.setattr(installer.shutil, 'which', Mock(return_value=None))
    with pytest.raises(FileNotFoundError):
        installer.locate_cpack_on_path_env_var()


def test_locate_cpack_on_path_env_var(monkeypatch):
    monkeypatch.setattr(
        installer.shutil,
        'which',
        Mock(return_value="cpack on path")
    )
    assert installer.locate_cpack_on_path_env_var() == "cpack on path"


def test_locate_cpack_in_python_packages_throws_on_not_finding(monkeypatch):
    monkeypatch.setattr(installer.shutil, 'which', Mock(return_value=None))
    with pytest.raises(FileNotFoundError):
        installer.locate_cpack_in_python_packages()


def test_locate_cpack_in_python_packages(monkeypatch):
    monkeypatch.setattr(
        installer.shutil,
        'which',
        Mock(return_value="cpack on path")
    )
    assert installer.locate_cpack_in_python_packages() == "cpack on path"


def test_run_cpack(monkeypatch):
    get_cpack_path = Mock(return_value="cpack")
    check_call = Mock(name='check_call')
    monkeypatch.setattr(installer, "get_cpack_path", get_cpack_path)
    monkeypatch.setattr(installer.subprocess, "check_call", check_call)
    installer.run_cpack("config_file.cmake", build_path="this/path")
    check_call.assert_called_with(
        ["cpack", "--config", "config_file.cmake", "-B", "this/path"]
    )

def test_generate_package_description_file():
    package_metadata =\
        Mock(name='package_metadata', get_all=Mock(return_value=["some data"]))

    m = mock_open()
    with patch('package_speedwagon.installer.open', m):
        installer.generate_package_description_file(
            package_metadata,
            output_path="dummy"
        )
    m().write.assert_called_once_with("some data")
