from unittest.mock import Mock, patch, mock_open
import pathlib

from package_speedwagon import utils


def test_read_toml_data():
    m = mock_open(read_data=b'')
    mock_load = Mock()
    with patch('package_speedwagon.utils.open', m):
        utils.read_toml_data(
            pathlib.Path('dummy.toml'),
            loader=mock_load
        )
    mock_load.assert_called_once()
