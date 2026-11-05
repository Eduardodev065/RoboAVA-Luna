import unittest
from unittest.mock import MagicMock, patch

from ava_py.__main__ import setup_api_key


class SetupKeyTest(unittest.TestCase):
    def test_openai_key_uses_user_variable(self):
        context = MagicMock()
        context.__enter__.return_value = object()
        with patch("ava_py.__main__.getpass.getpass", return_value="sk-example-openai-secret-value"), \
             patch("winreg.CreateKeyEx", return_value=context), \
             patch("winreg.QueryValueEx", side_effect=FileNotFoundError), \
             patch("winreg.SetValueEx") as save:
            setup_api_key()
        self.assertEqual(save.call_args.args[1], "OPENAI_API_KEY")

    def test_empty_paste_retries_without_saving(self):
        context = MagicMock()
        context.__enter__.return_value = object()
        with patch("ava_py.__main__.getpass.getpass", side_effect=["", "sk-example-openai-secret-value"]) as prompt, \
             patch("winreg.CreateKeyEx", return_value=context), \
             patch("winreg.QueryValueEx", side_effect=FileNotFoundError), \
             patch("winreg.SetValueEx") as save:
            setup_api_key()
        self.assertEqual(prompt.call_count, 2)
        self.assertEqual(save.call_count, 1)


if __name__ == "__main__":
    unittest.main()
