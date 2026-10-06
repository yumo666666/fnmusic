import os
import json
import hashlib
from io import BytesIO
import mutagen
from mutagen.easyid3 import EasyID3
from flask import Flask, jsonify, send_file, request, abort
from flask_cors import CORS
from library import (AUDIO_EXTENSIONS, contains, directory_readable, embedded_cover,
                     external_cover, folder_images, normalize_directories, scan)


def load_config(config_path: str):
    """加载配置文件。

    - 优先读取指定路径的 JSON 配置。
    - 读取失败或文件不存在时返回空字典。
    """
    if not config_path:
        return {}
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(config_path: str, updates: dict):
    """保存配置文件。

    - 会与原有 JSON 配置合并（updates 覆盖同名字段）。
    - 保存失败时抛出异常，由调用方决定如何处理。
    """
    current = load_config(config_path)
    if not isinstance(current, dict):
        current = {}
    if isinstance(updates, dict):
        current.update(updates)

    parent = os.path.dirname(config_path) if config_path else ''
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    return current


def realpath_or_empty(path: str):
    """返回规范化后的真实路径。

    - 失败时返回空字符串，用于安全校验与容错。
    """
    if not path:
        return ''
    try:
        return os.path.realpath(path)
    except Exception:
        return ''


def is_safe_child_path(candidate_path: str, base_dir: str):
    """校验 candidate_path 是否位于 base_dir 目录之下。

    用于防止通过路径参数访问 base_dir 之外的任意文件（路径穿越）。
    """
    if not candidate_path or not base_dir:
        return False
    candidate = realpath_or_empty(candidate_path)
    base = realpath_or_empty(base_dir)
    if not candidate or not base:
        return False
    try:
        common = os.path.commonpath([candidate, base])
    except Exception:
        return False
    return common == base


def get_metadata(file_path: str):
    """读取音频元数据并返回（艺术家, 专辑）。

    - 支持 MP3/FLAC/WAV/AAC 等格式（依赖 mutagen）。
    - 读取失败时返回“未知艺术家/未知专辑”。
    """
    artist = None
    album = None
    try:
        if file_path.lower().endswith('.mp3'):
            try:
                audio = EasyID3(file_path)
            except Exception:
                audio = mutagen.File(file_path, easy=True)
        else:
            audio = mutagen.File(file_path, easy=True)

        if not audio:
            audio = mutagen.File(file_path)

        if audio:
            if 'artist' in audio:
                artist = audio['artist'][0]
            elif 'TPE1' in audio:
                artist = str(audio['TPE1'])
            elif 'author' in audio:
                artist = str(audio['author'][0])

            if 'album' in audio:
                album = audio['album'][0]
            elif 'TALB' in audio:
                album = str(audio['TALB'])
            elif 'wm/albumtitle' in audio:
                album = str(audio['wm/albumtitle'][0])

    except Exception:
        pass

    return artist or '未知艺术家', album or '未知专辑'


def normalize_music_dir(path: str):
    if path is None:
        return ''
    value = str(path).strip()
    if not value:
        return ''
    value = value.replace('\\', '/')
    if value.startswith('vol'):
        value = '/' + value
    return value


def get_music_dirs():
    cfg = load_config(config_path)
    cfg = cfg if isinstance(cfg, dict) else {}
    raw = cfg.get('music_directories')
    if not isinstance(raw, list):
        raw = [cfg.get('music_directory') or os.environ.get('MUSIC_DIR') or '']
    try:
        return normalize_directories([path for path in raw if path])
    except ValueError:
        return []


def get_music_dir():
    directories = get_music_dirs()
    return directories[0] if directories else ''


def is_library_path(path):
    return bool(path) and contains(path, get_music_dirs())


server_dir = os.path.dirname(os.path.abspath(__file__))
app_root = os.path.dirname(server_dir)

trim_pkgvar = os.environ.get('TRIM_PKGVAR', '')
default_config_path = os.path.join(trim_pkgvar, 'config.json') if trim_pkgvar else ''
config_path = os.environ.get('CONFIG_FILE', default_config_path)
config = load_config(config_path)

ui_dir = os.path.abspath(os.environ.get('UI_DIR') or os.path.join(app_root, 'ui'))

music_dir = get_music_dir()

port = int(os.environ.get('PORT') or config.get('port', 8090))

host = os.environ.get('HOST') or config.get('host', '0.0.0.0')

favorites_file = os.environ.get('FAVORITES_FILE')
if not favorites_file:
    favorites_file = os.path.join(trim_pkgvar, 'favorites.json') if trim_pkgvar else os.path.join(app_root, 'favorites.json')

app = Flask(__name__, static_folder=ui_dir, static_url_path='')
CORS(app)


def load_favorites():
    """读取收藏列表。

    favorites_file 为 JSON 数组（歌曲绝对路径列表）。
    """
    if not os.path.exists(favorites_file):
        return []
    try:
        with open(favorites_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def save_favorites(favs):
    """保存收藏列表到 favorites_file。"""
    os.makedirs(os.path.dirname(favorites_file), exist_ok=True)
    with open(favorites_file, 'w', encoding='utf-8') as f:
        json.dump(favs, f, ensure_ascii=False, indent=2)


@app.route('/')
def index():
    """返回前端入口页面。"""
    index_path = os.path.join(ui_dir, 'index.html')
    if not os.path.exists(index_path):
        abort(404)
    return send_file(index_path)


@app.route('/api/files')
def list_files():
    return jsonify(scan(get_music_dirs(), get_metadata))


@app.route('/api/cover')
def cover_file():
    path = request.args.get('path')
    directories = get_music_dirs()
    if not path or not contains(path, directories):
        abort(403)
    if not os.path.isfile(path) or os.path.splitext(path)[1].lower() not in AUDIO_EXTENSIONS:
        abort(404)
    cover = embedded_cover(path)
    if cover:
        data, mime = cover
        response = send_file(BytesIO(data), mimetype=mime, etag=hashlib.sha256(data).hexdigest())
    else:
        external = external_cover(path, folder_images(os.path.dirname(path), directories))
        response = send_file(external or os.path.join(ui_dir, 'images', 'default-cover.svg'))
    response.cache_control.no_cache = True
    return response


@app.route('/api/status')
def status():
    directories = get_music_dirs()
    seen = set()
    counts = {'total_files_scanned': 0, 'audio_by_ext': {ext: 0 for ext in AUDIO_EXTENSIONS}}
    for directory in directories:
        for folder, _, files in os.walk(directory):
            for name in files:
                path = os.path.join(folder, name)
                real = os.path.realpath(path)
                if real in seen or not contains(path, directories):
                    continue
                seen.add(real)
                counts['total_files_scanned'] += 1
                extension = os.path.splitext(name)[1].lower()
                if extension in counts['audio_by_ext']:
                    counts['audio_by_ext'][extension] += 1
                if counts['total_files_scanned'] >= 20000:
                    break
            if counts['total_files_scanned'] >= 20000:
                break
        if counts['total_files_scanned'] >= 20000:
            break
    cfg = load_config(config_path)
    return jsonify({
        'config_path': config_path,
        'config_exists': bool(config_path) and os.path.exists(config_path),
        'config_music_directory': cfg.get('music_directory') if isinstance(cfg, dict) else None,
        'env_music_dir': os.environ.get('MUSIC_DIR'),
        'music_dir_effective': get_music_dir(),
        'music_dirs_effective': directories,
        'music_dir_exists': bool(directories) and os.path.isdir(directories[0]),
        'directories': [{'path': path, 'exists': os.path.isdir(path),
                         'readable': directory_readable(path)} for path in directories],
        'supported_audio': list(AUDIO_EXTENSIONS),
        'counts': counts
    })


@app.route('/api/config', methods=['GET'])
def get_config_api():
    directories = get_music_dirs()
    return jsonify({
        'config_path': config_path,
        'music_directory': get_music_dir(),
        'music_directories': directories,
        'music_dir_effective': get_music_dir(),
        'music_dirs_effective': directories
    })


def update_directories(raw):
    if not isinstance(raw, list) or not raw:
        return jsonify({'error': '请至少保留一个音乐扫描目录'}), 400
    try:
        directories = normalize_directories(raw)
    except ValueError as error:
        return jsonify({'error': str(error)}), 400
    for path in directories:
        if not os.path.isdir(path):
            return jsonify({'error': f'目录不存在：{path}'}), 400
        if not directory_readable(path):
            return jsonify({'error': f'目录无法读取：{path}。请在飞牛文件权限中授予 fnmusic 读取权限。'}), 400
    if not config_path:
        return jsonify({'error': '未设置配置文件路径'}), 500
    try:
        save_config(config_path, {'music_directories': directories, 'music_directory': directories[0]})
    except OSError:
        return jsonify({'error': '配置保存失败，请检查应用数据目录的写入权限'}), 500
    return jsonify({
        'ok': True, 'music_directory': directories[0], 'music_directories': directories,
        'music_dir_effective': directories[0], 'music_dirs_effective': directories
    })


@app.route('/api/config/music_directories', methods=['POST'])
def set_music_directories_api():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': '请提供音乐目录列表'}), 400
    return update_directories(data.get('music_directories'))


@app.route('/api/config/music_directory', methods=['POST'])
def set_music_directory_api():
    # Keep the original single-directory API for existing clients.
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': '请提供音乐目录'}), 400
    return update_directories([data.get('music_directory', data.get('musicDirectory'))])


@app.route('/api/play')
def play_file():
    """读取并返回音频或封面文件。

    仅允许访问 music_dir 目录下的文件。
    """
    path = request.args.get('path')
    base_dir = get_music_dir()
    if not path or not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    if not is_library_path(path):
        return jsonify({'error': 'Forbidden'}), 403
    return send_file(path)


@app.route('/api/favorites', methods=['GET', 'POST', 'DELETE'])
def manage_favorites():
    """获取/新增/删除收藏条目。"""
    favs = load_favorites()
    if request.method == 'GET':
        return jsonify(favs)

    data = request.json or {}
    path = data.get('path')
    base_dir = get_music_dir()
    if not path:
        return jsonify({'error': 'No path provided'}), 400
    if not is_library_path(path):
        return jsonify({'error': 'Forbidden'}), 403

    if request.method == 'POST':
        if path not in favs:
            favs.append(path)
            save_favorites(favs)
        return jsonify({'status': 'added', 'favorites': favs})

    if request.method == 'DELETE':
        if path in favs:
            favs.remove(path)
            save_favorites(favs)
        return jsonify({'status': 'removed', 'favorites': favs})

    return jsonify({'error': 'Unsupported method'}), 405


@app.route('/api/lyrics')
def get_lyrics():
    """读取并返回当前歌曲的 LRC 歌词（按行返回，前端解析时间戳）。"""
    song_path = request.args.get('song_path')
    base_dir = get_music_dir()
    if not song_path:
        return jsonify({'error': 'No song path'}), 400
    if not is_library_path(song_path):
        return jsonify({'error': 'Forbidden'}), 403

    base, _ = os.path.splitext(song_path)
    lrc_path = base + '.lrc'

    if not is_library_path(lrc_path):
        return jsonify({'error': 'Forbidden'}), 403
    if os.path.exists(lrc_path):
        try:
            with open(lrc_path, 'r', encoding='utf-8') as f:
                content = f.read()
            lines = content.splitlines()
            lyrics = []
            for line in lines:
                if line.strip():
                    lyrics.append(line)
            return jsonify({'lyrics': lyrics})
        except Exception as e:
            return jsonify({'error': str(e)})

    return jsonify({'lyrics': []})


if __name__ == '__main__':
    app.run(host=host, debug=False, port=port)
