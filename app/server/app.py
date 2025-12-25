import os
import json
import mutagen
from mutagen.easyid3 import EasyID3
from flask import Flask, jsonify, send_file, request, abort
from flask_cors import CORS


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


def get_music_dir():
    raw = os.environ.get('MUSIC_DIR')
    if raw is None or str(raw).strip() == '':
        cfg = load_config(config_path)
        raw = cfg.get('music_directory', '') if isinstance(cfg, dict) else ''
    raw = normalize_music_dir(raw)
    if not raw:
        return ''
    try:
        return os.path.abspath(raw)
    except Exception:
        return ''


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
    """扫描音乐目录并返回歌曲列表（含封面/歌词/元数据）。"""
    base_dir = get_music_dir()
    if not base_dir or not os.path.exists(base_dir):
        return jsonify([])

    songs = []
    supported_audio = ['.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.opus', '.ape', '.wma']
    supported_img = ['.jpg', '.png', '.jpeg']

    dir_files = {}

    for root, dirs, filenames in os.walk(base_dir):
        if root not in dir_files:
            dir_files[root] = {'audio': [], 'img': [], 'lrc': []}

        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext in supported_audio:
                dir_files[root]['audio'].append(filename)
            elif ext in supported_img:
                dir_files[root]['img'].append(filename)
            elif ext == '.lrc':
                dir_files[root]['lrc'].append(filename)

    for root, data in dir_files.items():
        data['audio'].sort()
        data['img'].sort()

        default_cover = None
        for img in data['img']:
            if 'cover' in img.lower() or 'folder' in img.lower() or 'front' in img.lower():
                default_cover = os.path.join(root, img)
                break
        if not default_cover and data['img']:
            default_cover = os.path.join(root, data['img'][0])

        for audio_file in data['audio']:
            base_name = os.path.splitext(audio_file)[0]
            audio_path = os.path.join(root, audio_file)

            lrc_path = os.path.join(root, base_name + '.lrc')
            if not os.path.exists(lrc_path):
                found_lrc = False
                for lrc in data['lrc']:
                    if os.path.splitext(lrc)[0].lower() == base_name.lower():
                        lrc_path = os.path.join(root, lrc)
                        found_lrc = True
                        break
                if not found_lrc:
                    lrc_path = None

            cover_path = default_cover
            for img in data['img']:
                if os.path.splitext(img)[0].lower() == base_name.lower():
                    cover_path = os.path.join(root, img)
                    break

            artist, album = get_metadata(audio_path)

            songs.append({
                'name': audio_file,
                'path': audio_path,
                'type': os.path.splitext(audio_file)[1].lower(),
                'parent': root,
                'cover_path': cover_path,
                'lrc_path': lrc_path,
                'artist': artist,
                'album': album
            })

    return jsonify(songs)


@app.route('/api/status')
def status():
    base_dir = get_music_dir()
    cfg = load_config(config_path)
    cfg_music = cfg.get('music_directory') if isinstance(cfg, dict) else None
    supported_audio = ['.mp3', '.flac', '.wav', '.aac', '.m4a', '.ogg', '.opus', '.ape', '.wma']

    counts = None
    if base_dir and os.path.exists(base_dir):
        ext_count = {ext: 0 for ext in supported_audio}
        total = 0
        for root, dirs, filenames in os.walk(base_dir):
            for filename in filenames:
                total += 1
                ext = os.path.splitext(filename)[1].lower()
                if ext in ext_count:
                    ext_count[ext] += 1
            if total >= 20000:
                break
        counts = {
            'total_files_scanned': total,
            'audio_by_ext': ext_count
        }

    return jsonify({
        'config_path': config_path,
        'config_exists': bool(config_path) and os.path.exists(config_path),
        'config_music_directory': cfg_music,
        'env_music_dir': os.environ.get('MUSIC_DIR'),
        'music_dir_effective': base_dir,
        'music_dir_exists': bool(base_dir) and os.path.exists(base_dir),
        'supported_audio': supported_audio,
        'counts': counts
    })


@app.route('/api/config', methods=['GET'])
def get_config_api():
    """获取应用配置（用于前端设置页展示）。"""
    cfg = load_config(config_path)
    if not isinstance(cfg, dict):
        cfg = {}
    return jsonify({
        'config_path': config_path,
        'music_directory': cfg.get('music_directory', ''),
        'music_dir_effective': get_music_dir(),
    })


@app.route('/api/config/music_directory', methods=['POST'])
def set_music_directory_api():
    """更新音乐目录。

    - 写入 config.json 的 music_directory。
    - 同步更新进程内环境变量 MUSIC_DIR，使修改立刻生效。
    """
    data = request.json or {}
    raw = data.get('music_directory')
    if raw is None:
        raw = data.get('musicDirectory')

    value = normalize_music_dir(raw)
    if not value:
        return jsonify({'error': 'music_directory is required'}), 400

    try:
        abs_dir = os.path.abspath(value)
    except Exception:
        return jsonify({'error': 'invalid path'}), 400

    if not os.path.isdir(abs_dir):
        return jsonify({'error': 'directory not found'}), 400

    if not config_path:
        return jsonify({'error': 'config path not set'}), 500

    try:
        save_config(config_path, {'music_directory': value})
        os.environ['MUSIC_DIR'] = value
    except Exception:
        return jsonify({'error': 'failed to save config'}), 500

    return jsonify({
        'ok': True,
        'music_directory': value,
        'music_dir_effective': get_music_dir(),
    })


@app.route('/api/play')
def play_file():
    """读取并返回音频或封面文件。

    仅允许访问 music_dir 目录下的文件。
    """
    path = request.args.get('path')
    base_dir = get_music_dir()
    if not path or not os.path.exists(path):
        return jsonify({'error': 'File not found'}), 404
    if not is_safe_child_path(path, base_dir):
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
    if not is_safe_child_path(path, base_dir):
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
    if not is_safe_child_path(song_path, base_dir):
        return jsonify({'error': 'Forbidden'}), 403

    base, _ = os.path.splitext(song_path)
    lrc_path = base + '.lrc'

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
