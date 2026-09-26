import os
import pytest

from file_reader import read_source_files

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def test_reads_py_and_php_files():
    result = read_source_files(FIXTURES)
    keys = set(result.keys())
    assert any(k.endswith(".py") for k in keys), "Expected at least one .py file"
    assert any(k.endswith(".php") for k in keys), "Expected at least one .php file"


def test_returns_file_content():
    result = read_source_files(FIXTURES)
    py_file = next(k for k in result if k.endswith(".py"))
    assert len(result[py_file]) > 0, "File content should not be empty"


def test_keys_are_relative_paths():
    result = read_source_files(FIXTURES)
    for key in result:
        assert not os.path.isabs(key), f"Key '{key}' should be a relative path"


def test_invalid_directory_raises():
    with pytest.raises(NotADirectoryError):
        read_source_files("/nonexistent/path/that/does/not/exist")


def test_returns_dict():
    result = read_source_files(FIXTURES)
    assert isinstance(result, dict)
