"""Exécute la vraie fonction JS avec un DOM minimal, sans navigateur."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node.js nécessaire au test du générateur HTML')
class CommandGeneratorTests(unittest.TestCase):
    def test_visible_defaults_and_disabled_translation_are_explicit(self):
        source = Path('generator/generator.html').read_text(encoding='utf-8')
        function = source[source.index('    function updateCommand()'):source.index('    function copyCommand()')]
        values = {'input-path': 'C:\\films\\video.mp4', 'output-dir': 'C:\\sortie', 'sel-engine': 'onecore',
                  'sel-voice': 'voice', 'sel-sub': 'auto', 'input-ducking': '5.0', 'input-bg-mix': '1.0',
                  'input-tts-mix': '1.0', 'input-offset-audio': '0', 'input-offset-video': '0',
                  'input-min-rate': '1.2', 'input-max-rate': '1.8', 'sel-audio-codec': 'ac3',
                  'sel-audio-bitrate': '256'}
        script = ('const values=' + json.dumps(values) + ';const nodes={};'
                  'const document={getElementById(id){return nodes[id] ||= {value:values[id] || "",checked:false};}};'
                  + function + ';updateCommand();console.log(nodes["command-output"].textContent);')
        command = subprocess.check_output(['node', '-e', script], text=True, timeout=10)
        for expected in ('--no-translate', '--bg-mix 1.0', '--tts-mix 1.0', '--audio-bitrate 256',
                         '--min-rate-tts 1.2', '--audio-codec ac3', '--offset-ms 0'):
            self.assertIn(expected, command)
