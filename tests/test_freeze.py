import argparse
import sys
from unittest.mock import Mock, MagicMock


if sys.version_info >= (3, 9):
    import importlib.resources as importlib_resources
else:
    import importlib_resources

import PyInstaller.__main__
import pytest

from package_speedwagon import freeze


class TestDefaultGenerateSpecs:

    @pytest.fixture
    def sample_bootstrap_script_name(self):
        return 'speedwagon-bootstrap.py'

    @pytest.fixture
    def sample_collection_name(self):
        return 'collection'

    @pytest.fixture
    def sample_bundle_name(self):
        return 'bundle'

    @pytest.fixture
    def sample_specs(
        self,
        sample_bootstrap_script_name,
        sample_collection_name,
        sample_bundle_name
    ):
        return freeze.DefaultGenerateSpecs.SpecsDataClass(
            bootstrap_script=sample_bootstrap_script_name,
            app_executable_name="dummy",
            collection_name=sample_collection_name,
            bundle_name=sample_bundle_name

        )

    def test_generate(self, sample_specs, sample_bootstrap_script_name):
        specs_generator = freeze.DefaultGenerateSpecs(sample_specs)
        generate_specs = specs_generator.generate()
        assert sample_bootstrap_script_name in generate_specs

    @pytest.mark.slow
    def test_is_valid(self, tmp_path, sample_specs, sample_collection_name):
        specs_generator = freeze.DefaultGenerateSpecs(sample_specs)
        generate_specs = specs_generator.generate()
        dummy_project = tmp_path / "project"
        specs_file = dummy_project / "specs.spec"
        bootstrap_file = dummy_project / "speedwagon-bootstrap.py"
        dummy_project.mkdir()
        specs_file.write_text(generate_specs)

        bootstrap_source_file =\
            importlib_resources.files(
                'package_speedwagon'
            ) / 'speedwagon-bootstrap.py'

        bootstrap_file.write_text(bootstrap_source_file.read_text())

        output_path = tmp_path / "output"
        output_path.mkdir()

        workpath = tmp_path / "workpath"

        PyInstaller.__main__.run([
            '--noconfirm',
            str(specs_file),
            '--distpath', str(output_path),
            "--workpath", str(workpath),
        ])
        assert (output_path / sample_collection_name).exists()


def test_find_frozen_folder():
    strategy = Mock()
    args = argparse.Namespace()
    freeze.find_frozen_folder("some_path", args, strategy=strategy)
    strategy.assert_called_with("some_path", args)


def test_find_frozen_folder_use_defaults(monkeypatch):
    args = argparse.Namespace()
    strategies = MagicMock()
    strategy = Mock(name='strategy')
    strategies.get.return_value = strategy
    monkeypatch.setattr(
        freeze,
        "default_search_frozen_strategy_mapping",
        strategies
    )
    freeze.find_frozen_folder("some_path", args)
    strategy.assert_called_with("some_path", args)


def test_find_frozen_folder_use_defaults_invalid_raises(monkeypatch):
    args = argparse.Namespace()
    strategies = MagicMock()
    strategies.get.return_value = None
    monkeypatch.setattr(
        freeze,
        "default_search_frozen_strategy_mapping",
        strategies
    )
    with pytest.raises(ValueError):
        freeze.find_frozen_folder("some_path", args)
