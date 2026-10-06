"""Library scanning and deterministic album artwork selection."""
import base64
import os
from urllib.parse import urlencode

import mutagen
from mutagen.flac import Picture
from mutagen.id3 import ID3

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.opus', '.ape', '.wma')
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif')


def normalize_directories(paths):
    result = []
    for path in paths:
        value = str(path).strip().replace('\\', '/') if isinstance(path, str) else ''
        if value.startswith('vol'):
            value = '/' + value
        if not value or not os.path.isabs(value):
            raise ValueError('请填写音乐目录的完整路径，例如 /vol2/1000/音乐')
        value = os.path.realpath(value)
        if value not in result:
            result.append(value)
    return result


def contains(path, directories):
    candidate = os.path.realpath(path)
    for directory in directories:
        try:
            if os.path.commonpath([candidate, os.path.realpath(directory)]) == os.path.realpath(directory):
                return True
        except ValueError:
            pass
    return False


def directory_readable(path):
    try:
        with os.scandir(path):
            return True
    except OSError:
        return False


def external_cover(audio_path, image_paths):
    """Use a matching song image, then an exact conventional album image name."""
    stem = os.path.splitext(os.path.basename(audio_path))[0].casefold()
    images = sorted(image_paths, key=lambda path: path.casefold())
    for image in images:
        if os.path.splitext(os.path.basename(image))[0].casefold() == stem:
            return image
    for name in ('cover', 'folder', 'front', 'album', '封面'):
        for image in images:
            if os.path.splitext(os.path.basename(image))[0].casefold() == name:
                return image
    return None


def image_mime(data):
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith((b'GIF87a', b'GIF89a')):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    return None


def embedded_cover(path):
    """Read ID3, FLAC, MP4, Vorbis and APE cover data without fetching URLs."""
    try:
        audio = mutagen.File(path)
        tags = getattr(audio, 'tags', None)
    except Exception:
        audio, tags = None, None
    if tags is None and path.lower().endswith('.mp3'):
        try:
            tags = ID3(path)
        except Exception:
            pass
    pictures = list(getattr(audio, 'pictures', ()) or ())
    if tags is not None:
        if hasattr(tags, 'getall'):
            pictures.extend(tags.getall('APIC'))
        for encoded in tags.get('metadata_block_picture', []):
            try:
                pictures.append(Picture(base64.b64decode(encoded)))
            except Exception:
                continue
    # Prefer front-cover artwork over back covers and other embedded pictures.
    pictures.sort(key=lambda picture: getattr(picture, 'type', 0) != 3)
    candidates = [picture.data for picture in pictures]
    if tags is not None:
        candidates.extend(bytes(cover) for cover in tags.get('covr', []))
        for encoded in tags.get('coverart', []):
            try:
                candidates.append(base64.b64decode(encoded))
            except Exception:
                continue
        ape_cover = tags.get('Cover Art (Front)')
        if ape_cover is not None:
            try:
                candidates.append(bytes(ape_cover.value).split(b'\0', 1)[1])
            except (AttributeError, IndexError, TypeError):
                pass
    for data in candidates:
        mime = image_mime(data)
        if mime:
            return data, mime
    return None


def folder_images(folder, directories):
    try:
        return [entry.path for entry in os.scandir(folder)
                if entry.is_file() and os.path.splitext(entry.name)[1].lower() in IMAGE_EXTENSIONS
                and contains(entry.path, directories)]
    except OSError:
        return []


def scan(directories, metadata):
    songs, seen = [], set()
    for directory in directories:
        for folder, _, filenames in os.walk(directory):
            images = [os.path.join(folder, name) for name in filenames
                      if os.path.splitext(name)[1].lower() in IMAGE_EXTENSIONS
                      and contains(os.path.join(folder, name), directories)]
            lyrics = {os.path.splitext(name)[0].casefold(): os.path.join(folder, name)
                      for name in filenames if os.path.splitext(name)[1].lower() == '.lrc'}
            for name in sorted(filenames, key=str.casefold):
                extension = os.path.splitext(name)[1].lower()
                if extension not in AUDIO_EXTENSIONS:
                    continue
                path = os.path.join(folder, name)
                real = os.path.realpath(path)
                if real in seen or not contains(path, directories) or not os.path.isfile(path):
                    continue
                seen.add(real)
                artist, album = metadata(path)
                lrc = lyrics.get(os.path.splitext(name)[0].casefold())
                if lrc and not contains(lrc, directories):
                    lrc = None
                try:
                    version = os.stat(path).st_mtime_ns
                except OSError:
                    continue
                songs.append({
                    'name': name, 'path': path, 'type': extension, 'parent': folder,
                    'cover_path': external_cover(path, images),
                    'cover_url': '/api/cover?' + urlencode({'path': path, 'v': version}),
                    'lrc_path': lrc, 'artist': artist, 'album': album
                })
    return songs
