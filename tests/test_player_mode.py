"""Le lecteur est un mode séparé ; le traitement enfant n'ouvre pas de GUI."""
import unittest
from unittest.mock import patch
from add_dub.cli.args import parse_args, want_interactive
from add_dub.__main__ import main


class PlayerModeTests(unittest.TestCase):
    def test_modes_are_exclusive(self):
        self.assertFalse(want_interactive(parse_args(['--player'])[0]))
        for mode in ('--gui', '--batch', '--interactive'):
            with self.subTest(mode=mode), self.assertRaises(SystemExit):
                parse_args(['--player', mode])

    def test_player_dispatch_and_input(self):
        with patch('add_dub.player.gui.run.main', return_value=0) as player:
            self.assertEqual(main(['--player', '-i', 'film.mkv']), 0)
            self.assertEqual(player.call_args.args[0].input, ['film.mkv'])

    def test_worker_dispatch(self):
        with patch('add_dub.player.core.generation.main', return_value=7) as worker:
            self.assertEqual(main(['--player-generate', 'request.json']), 7)
            worker.assert_called_once_with('request.json')
