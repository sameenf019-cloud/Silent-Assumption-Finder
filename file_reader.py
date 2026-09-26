import os
from typing import Dict

SUPPORTED_EXTENSIONS = {".py", ".php"}


def read_source_files(folder: str) -> Dict[str, str]:
    """
    Recursively read all .py and .php files inside *folder*.

    Args:
        folder: Path to the root directory to scan.

    Returns:
        A dictionary mapping each file's path (relative to *folder*) to its
        text content.  Files that cannot be decoded as UTF-8 are skipped.

    Raises:
        NotADirectoryError: If *folder* does not point to an existing directory.
    """
    if not os.path.isdir(folder):
        raise NotADirectoryError(f"'{folder}' is not a valid directory.")

    sources: Dict[str, str] = {}

    for dirpath, _dirnames, filenames in os.walk(folder):
        for filename in filenames:
            _, ext = os.path.splitext(filename)
            if ext.lower() not in SUPPORTED_EXTENSIONS:
                continue

            absolute_path = os.path.join(dirpath, filename)
            relative_path = os.path.relpath(absolute_path, folder)

            try:
                with open(absolute_path, "r", encoding="utf-8") as fh:
                    sources[relative_path] = fh.read()
            except UnicodeDecodeError:
                # Skip files that cannot be read as UTF-8
                continue

    return sources
