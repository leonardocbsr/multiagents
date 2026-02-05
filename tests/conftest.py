from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_real_claude_cli():
    """Prevent memory tests from invoking the real claude CLI.

    Tests that want to exercise the CLI path should mock subprocess.run
    explicitly and patch shutil.which to return a path.
    """
    with patch("src.memory.manager.shutil.which", return_value=None):
        yield
