import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ava_py.__main__ import unresolved_question_urls


class ProgressTest(unittest.TestCase):
    def test_unreadable_activity_is_explicitly_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = Path(directory) / ".reports"
            reports.mkdir()
            (reports / "test-progress.json").write_text(json.dumps([
                {"url": "https://www.avaeduc.com.br/mod/quiz/view.php?id=1", "event": "questão pendente"},
                {"url": "https://www.avaeduc.com.br/mod/quiz/view.php?id=2", "event": "questão pendente"},
                {"url": "https://www.avaeduc.com.br/mod/quiz/view.php?id=2", "event": "envio confirmado"},
            ]), encoding="utf-8")
            with patch("ava_py.__main__.ROOT", Path(directory)):
                blocked = unresolved_question_urls("test")
        self.assertEqual(blocked, {"https://www.avaeduc.com.br/mod/quiz/view.php?id=1"})


if __name__ == "__main__":
    unittest.main()
