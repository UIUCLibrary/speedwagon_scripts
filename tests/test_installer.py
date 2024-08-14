import os
from unittest.mock import Mock
from package_speedwagon import installer

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


class TestCreateLicenseTXTFile:
    def test_create_calls_write_file(self):
        output_path = os.path.join("dummy", "path", "license.txt")
        strategy = installer.CopyLicenseFile("License", output_path)
        strategy.pre_check = Mock(return_value=True)
        strategy.copy_file = Mock(return_value=None)
        strategy()
        strategy.copy_file.assert_called_once()


class TestCreateNoLicenseFile:
    def test_call_calls_write_license_file(self):
        output_path = os.path.join("dummy", "path", "license.txt")
        strategy = installer.GenerateNoLicenseGivenFile(output_path)
        strategy.write_license_file = Mock()
        strategy()
        strategy.write_license_file.assert_called_once()


class TestLocateLicenseFile:
    def test_call(self):
        strategy = installer.LocateLicenseFile()
        strategy.locate_license_file = Mock(return_value="license")
        result = strategy()
        assert result.endswith("license")