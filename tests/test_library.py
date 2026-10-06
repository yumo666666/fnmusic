import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

SERVER = Path(__file__).resolve().parents[1] / 'app' / 'server'
sys.path.insert(0, str(SERVER))
import library
from mutagen.id3 import APIC
from mutagen.flac import Picture
from mutagen.mp4 import MP4Cover
from mutagen.wave import WAVE

spec = importlib.util.spec_from_file_location('fnmusic_test_app', SERVER / 'app.py')
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')


def audio_file(path):
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(8000)
        f.writeframes(b'\0\0' * 800)
    return path


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.first = self.root / 'first'
        self.second = self.root / 'second'
        self.first.mkdir()
        self.second.mkdir()
        self.one = audio_file(self.first / 'one.wav')
        self.two = audio_file(self.second / 'two.wav')
        backend.config_path = str(self.root / 'config.json')
        backend.favorites_file = str(self.root / 'favorites.json')
        Path(backend.config_path).write_text(json.dumps({'music_directory': str(self.first)}))
        self.env = patch.dict(os.environ, {'MUSIC_DIR': str(self.first)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = backend.app.test_client()

    def save(self, directories):
        return self.client.post('/api/config/music_directories', json={'music_directories': directories})

    def cover(self, path=None):
        response = self.client.get('/api/cover', query_string={'path': str(path or self.one)})
        self.addCleanup(response.close)
        return response

    def test_live_add_remove_and_persistent_config_without_restart(self):
        original_app = backend.app
        response = self.save([str(self.first), str(self.second)])
        self.assertEqual(response.status_code, 200)
        songs = self.client.get('/api/files').get_json()
        self.assertEqual({song['name'] for song in songs}, {'one.wav', 'two.wav'})
        self.assertIs(backend.app, original_app)
        # The startup environment still points at first; saved configuration wins.
        self.assertEqual(os.environ['MUSIC_DIR'], str(self.first))
        self.assertEqual(backend.get_music_dirs(), [str(self.first), str(self.second)])
        self.assertEqual(json.loads(Path(backend.config_path).read_text())['music_directories'], [str(self.first), str(self.second)])
        with self.client.get('/api/play', query_string={'path': str(self.two)}, headers={'Range': 'bytes=0-31'}) as response:
            self.assertEqual(response.status_code, 206)
        (self.second / 'two.lrc').write_text('[00:00]test')
        self.assertEqual(self.client.get('/api/lyrics', query_string={'song_path': str(self.two)}).get_json()['lyrics'], ['[00:00]test'])
        self.assertEqual(self.save([str(self.second)]).status_code, 200)
        self.assertEqual({song['name'] for song in self.client.get('/api/files').get_json()}, {'two.wav'})
        self.assertEqual(self.client.get('/api/play', query_string={'path': str(self.one)}).status_code, 403)
        self.assertEqual(self.cover(self.one).status_code, 403)

    def test_legacy_config_and_api(self):
        self.assertEqual(self.client.get('/api/config').get_json()['music_directories'], [str(self.first)])
        response = self.client.post('/api/config/music_directory', json={'music_directory': str(self.second)})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(backend.get_music_dirs(), [str(self.second)])

    def test_invalid_or_unreadable_directory_does_not_replace_config(self):
        original = Path(backend.config_path).read_bytes()
        for value in [[], [42], ['relative/path'], [str(self.root / 'missing')]]:
            self.assertEqual(self.save(value).status_code, 400)
            self.assertEqual(Path(backend.config_path).read_bytes(), original)
        with patch.object(backend, 'directory_readable', return_value=False):
            self.assertEqual(self.save([str(self.second)]).status_code, 400)
        self.assertEqual(Path(backend.config_path).read_bytes(), original)

    def test_overlapping_directories_and_symlinks_are_deduplicated(self):
        child = self.first / 'album'
        child.mkdir()
        audio_file(child / 'three.wav')
        (self.first / 'alias.wav').symlink_to(child / 'three.wav')
        self.assertEqual(self.save([str(self.first), str(child), str(self.first) + '/']).status_code, 200)
        self.assertEqual(len(self.client.get('/api/files').get_json()), 2)

    def test_embedded_front_cover_takes_priority(self):
        (self.first / 'one.png').write_bytes(PNG + b'external')
        audio = WAVE(self.one)
        audio.add_tags()
        audio.tags.add(APIC(mime='image/png', type=4, desc='back', data=PNG + b'back'))
        audio.tags.add(APIC(mime='image/png', type=3, desc='front', data=PNG + b'front'))
        audio.save()
        response = self.cover()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        self.assertEqual(response.data, PNG + b'front')
        self.assertIn('no-cache', response.headers['Cache-Control'])
        songs = self.client.get('/api/files').get_json()
        self.assertTrue(songs[0]['cover_url'].startswith('/api/cover?'))

    def test_same_name_then_standard_cover_then_local_default(self):
        (self.first / 'unrelated.png').write_bytes(PNG + b'unrelated')
        self.assertEqual(self.cover().mimetype, 'image/svg+xml')
        (self.first / 'cover.png').write_bytes(PNG + b'album')
        self.assertEqual(self.cover().data, PNG + b'album')
        (self.first / 'ONE.PNG').write_bytes(PNG + b'song')
        self.assertEqual(self.cover().data, PNG + b'song')

    def test_other_embedded_cover_formats(self):
        picture = Picture()
        picture.type = 3
        picture.mime = 'image/png'
        picture.data = PNG
        for audio in [
            SimpleNamespace(pictures=[picture], tags={}),
            SimpleNamespace(tags={'covr': [MP4Cover(PNG, imageformat=MP4Cover.FORMAT_PNG)]}),
            SimpleNamespace(tags={'metadata_block_picture': [base64.b64encode(picture.write()).decode()]})
        ]:
            with patch.object(library.mutagen, 'File', return_value=audio):
                self.assertEqual(library.embedded_cover(str(self.one)), (PNG, 'image/png'))

    def test_cover_and_lyrics_cannot_escape_library_by_symlink(self):
        outside = self.root / 'outside.png'
        outside.write_bytes(PNG)
        (self.first / 'one.png').symlink_to(outside)
        (self.first / 'one.lrc').symlink_to(self.root / 'private.txt')
        (self.root / 'private.txt').write_text('private')
        self.assertEqual(self.cover().mimetype, 'image/svg+xml')
        self.assertEqual(self.client.get('/api/lyrics', query_string={'song_path': str(self.one)}).status_code, 403)
        self.assertEqual(self.cover(self.two).status_code, 403)


if __name__ == '__main__':
    unittest.main()
