import io
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pysecretary import utils


class UtilsTests(unittest.TestCase):
    def test_timestamp_format(self) -> None:
        self.assertRegex(utils.timestamp(), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")

    def test_append_text_appends_newline(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "history.txt"

            utils.append_text(str(path), "first")
            utils.append_text(str(path), "second")

            self.assertEqual(path.read_text(encoding="utf-8"), "first\nsecond\n")

    def test_print_section_outputs_dividers_title_and_body(self) -> None:
        stream = io.StringIO()

        with patch("sys.stdout", stream):
            utils.print_section("Title", "Body")

        output = stream.getvalue()
        self.assertIn("Title", output)
        self.assertIn("Body", output)
        self.assertTrue(re.search(r"={20,}", output))


if __name__ == "__main__":
    unittest.main()

