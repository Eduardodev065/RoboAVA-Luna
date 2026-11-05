import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ava_py.openai_solver import OpenAISolver, _api_key


class OpenAISolverTest(unittest.TestCase):
    def test_sends_question_and_image_and_checks_chosen_text(self):
        class Responses:
            def create(self, **kwargs):
                self.request = kwargs
                return type("Response", (), {
                    "status": "completed",
                    "output_text": json.dumps({
                        "answerable": True,
                        "choice_index": 2,
                        "choice_text": "4",
                        "explanation": "A soma de dois com dois resulta em quatro unidades.",
                        "missing_information": "",
                    }),
                })()

        solver = object.__new__(OpenAISolver)
        solver.client = type("Client", (), {"responses": Responses()})()
        solver.model = "gpt-6-luna"
        decision = solver.answer(
            course="Matemática",
            question={"number": "1", "stem": "Quanto é 2 + 2?", "options": [{"text": "5"}, {"text": "4"}]},
            screenshot=b"\x89PNG\r\n\x1a\n",
        )
        self.assertEqual(decision.index, 1)
        request = solver.client.responses.request
        self.assertEqual(request["model"], "gpt-6-luna")
        self.assertFalse(request["store"])
        content = request["input"][0]["content"]
        self.assertIn("Quanto é 2 + 2?", content[0]["text"])
        self.assertTrue(content[1]["image_url"].startswith("data:image/png;base64,"))
        self.assertTrue(request["text"]["format"]["strict"])

    def test_frozen_key_reads_bundled_key_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ava_api.json"
            path.write_text(json.dumps({"openai_api_key": "example-key"}), encoding="utf-8")
            with patch("sys.frozen", True, create=True), patch("sys._MEIPASS", directory, create=True):
                self.assertEqual(_api_key(), "example-key")
                path.unlink()
                self.assertIsNone(_api_key())


if __name__ == "__main__":
    unittest.main()
