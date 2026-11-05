import unittest
import sys
from unittest.mock import patch

import robo_ava_console


class ConsoleTest(unittest.TestCase):
    def test_one_starts_full_run(self):
        commands = []
        with patch("builtins.input", side_effect=["1", "0"]), \
             patch("robo_ava_console.main", side_effect=lambda: commands.append(sys.argv[1:])), \
             patch("sys.argv", ["RoboAVA.exe"]):
            robo_ava_console.menu()
        self.assertEqual(commands, [["run", "--profile", "principal"]])


if __name__ == "__main__":
    unittest.main()
