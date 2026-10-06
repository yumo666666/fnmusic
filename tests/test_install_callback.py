import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CALLBACK = Path(__file__).resolve().parents[1] / 'cmd' / 'install_callback'


class InstallCallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.var = Path(self.temp.name)
        binaries = self.var / '.venv' / 'bin'
        binaries.mkdir(parents=True)
        (binaries / 'python').symlink_to(sys.executable)
        pip = binaries / 'pip'
        pip.write_text('#!/bin/sh\nexit 0\n')
        pip.chmod(0o755)

    def run_callback(self):
        return subprocess.run(['bash', str(CALLBACK)], capture_output=True, text=True,
            env={**os.environ, 'TRIM_PKGVAR': str(self.var), 'TRIM_APPDEST': str(self.var),
                 'wizard_music_directory': '/new/default'})

    def test_first_install_saves_wizard_directory(self):
        result = self.run_callback()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.var / 'config.json').read_text())['music_directory'], '/new/default')

    def test_reinstall_keeps_all_existing_directories(self):
        config = {'music_directory': '/original/one', 'music_directories': ['/original/one', '/original/two'], 'port': 8090}
        (self.var / 'config.json').write_text(json.dumps(config))
        result = self.run_callback()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.var / 'config.json').read_text()), config)

    def test_invalid_existing_config_is_not_overwritten(self):
        path = self.var / 'config.json'
        path.write_text('invalid original config')
        result = self.run_callback()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(path.read_text(), 'invalid original config')


if __name__ == '__main__':
    unittest.main()
