import unittest
from unittest.mock import MagicMock

from textual.widgets import Button

from pysync_maria.tui.screens.connection_screen import ConnectionScreen


class TestConnectionScreen(unittest.TestCase):
    def test_check_all_ready(self):
        # Instantiate without calling __init__ or compose if possible,
        # or just mock what we need.
        screen = ConnectionScreen()
        mock_button = MagicMock(spec=Button)
        mock_button.disabled = True # initial state

        # Mock query_one to return our mock button
        # We use a side effect to check the ID passed
        def mock_query_one(selector, type):
            if selector == "#connect-btn":
                return mock_button
            return MagicMock()

        screen.query_one = mock_query_one

        # Test 1: both False
        screen.source_ok = False
        screen.target_ok = False
        screen.check_all_ready()
        self.assertTrue(mock_button.disabled)

        # Test 2: one True
        screen.source_ok = True
        screen.target_ok = False
        screen.check_all_ready()
        self.assertTrue(mock_button.disabled)

        # Test 3: both True
        screen.source_ok = True
        screen.target_ok = True
        screen.check_all_ready()
        self.assertFalse(mock_button.disabled)

if __name__ == "__main__":
    unittest.main()
