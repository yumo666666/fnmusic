# fnmusic（飞牛桌面应用）

基于 Flask 的本地音乐播放器，已适配为飞牛桌面应用入口（iframe 打开）。默认扫描指定音乐目录，提供播放、收藏与歌词读取能力。
|                      |                      |
| -------------------- | -------------------- |
| ![Demo](./app/ui/images/1.png) | ![Demo](./app/ui/images/2.png) |
| ![Demo](./app/ui/images/3.png) | ![Demo](./app/ui/images/4.png) |
## 功能

- 扫描音乐目录并生成播放列表（按目录聚合，支持常见音频格式）
- 播放控制：播放/暂停、上一首/下一首、进度与音量控制
- 静音按钮：点击切换静音，静音时显示红色带叉喇叭；再次点击恢复原音量，调高音量会取消静音，刷新后保留静音状态
- 播放速度：0.5、0.75、1、1.25、1.5、1.75、2、2.5、3 倍速，保留音调，切歌和刷新后恢复上次选择
- 手机布局：窄屏下调整封面、控制按钮和播放列表布局
- 循环模式：顺序循环 / 随机播放 / 单曲循环
- 收藏（心动模式）：收藏歌曲、仅播放收藏列表
- 歌词：读取同名 `.lrc` 并在前端展示
- 状态记忆：播放器状态写入浏览器本地存储，刷新后可恢复
- 封面：优先读取音频内嵌封面，再匹配同名图片、标准专辑封面；无封面时显示本地默认图
- 设置页：可添加、移除多个扫描目录，保存后立即重新扫描，无需重启

## 端口说明

- 当前版本端口固定为 `8090`（不再在安装向导中填写端口）。
- 飞牛桌面入口配置同样固定为 `8090`：`app/ui/config`。

访问地址：`http://<设备IP>:8090/`

## 配置与数据文件

- 配置文件：`config.json`（路径通常为 `${TRIM_PKGVAR}/config.json`）
  - `music_directories`：多个音乐扫描目录（在设置页管理）
  - `music_directory`：首个音乐目录，兼容旧版单目录配置和安装向导
  - `port`：会写入 `8090`，但启动端口仍以固定值 `8090` 为准
- 收藏文件：`favorites.json`（路径通常为 `${TRIM_PKGVAR}/favorites.json`）

## 后端 API

后端位于 `app/server/app.py`，主要接口如下：

- `GET /`：前端入口页面
- `GET /api/files`：扫描音乐目录并返回歌曲列表（包含封面/歌词/元数据字段）
- `GET /api/play?path=<文件绝对路径>`：读取并返回音频/封面文件
- `GET /api/cover?path=<音频文件绝对路径>`：读取内嵌封面、匹配外部封面或返回本地默认图
- `GET /api/lyrics?song_path=<文件绝对路径>`：返回 `.lrc` 歌词行数组
- `GET /api/status`：返回配置与扫描统计（最多统计 20000 个文件）
- `GET /api/config`：返回当前配置（用于设置页展示）
- `POST /api/config/music_directory`：更新音乐目录并立刻生效
- `POST /api/config/music_directories`：通过 `{"music_directories":["/路径一","/路径二"]}` 更新多个目录并立刻生效
- `GET/POST/DELETE /api/favorites`：获取/新增/删除收藏项

说明：后端对 `path` / `song_path` 做了真实路径边界校验，仅允许访问已配置扫描目录下的文件。
重叠目录和指向相同文件的链接会去重；移除目录后，该目录中未被其他扫描目录覆盖的文件不能继续通过接口访问。

## 本地运行（可选）

在本机调试时可直接运行 Flask 服务：

Windows（PowerShell）：

```powershell
python -m venv .venv
\.venv\Scripts\pip install -r fnmusic\app\server\requirements.txt
$env:MUSIC_DIR = "D:\\Music"
python fnmusic\app\server\app.py
```

Linux/macOS：

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r fnmusic/app/server/requirements.txt
MUSIC_DIR="/path/to/Music" python fnmusic/app/server/app.py
```

浏览器访问：`http://127.0.0.1:8090/`

## 倍速版安装与更新

本分支基于 [yumo666666/fnmusic](https://github.com/yumo666666/fnmusic) 修改，
当前应用版本为 `1.0.3`，应用中心名称为“音乐播放器（倍速版）”，应用 ID 仍为 `fnmusic`。
在播放按钮下方选择“播放速度”即可调整速度；设置保存于当前浏览器、当前网站地址的本地存储中。
Android 手机可以使用 Chrome 访问 `http://<NAS局域网IP>:8090/`。
这是 fnmusic 的独立网页入口，与官方飞牛 App 自带的音乐播放器界面独立。

### 首次安装

先在飞牛应用中心安装并启动 `Python 3.12`（应用 ID 为 `python312`）。
从仓库获取源码，或使用仓库根目录中已构建的 `fnmusic.fpk`。

```bash
git clone git@github.com:yuliyang2023/fnmusic.git
cd fnmusic
```

在安装向导中填写实际的音乐目录。也可以在 NAS 终端使用命令行安装：

```bash
printf '%s\n' 'wizard_music_directory=/vol2/1000/youtube/' > install.env
sudo appcenter-cli install-fpk ./fnmusic.fpk --env ./install.env --volume 3
sudo appcenter-cli start fnmusic
```

`--volume 3` 表示将应用安装到存储空间 3，请按自己的 NAS 修改，或省略以使用系统默认位置。
上述音乐路径是本机示例，可以在安装向导或应用内的设置页修改。
应用账号 `fnmusic` 需要音乐目录及其中文件的读取权限，并需要各级父目录的穿越权限。
若扫描结果为空，请先通过飞牛的文件权限设置确认应用账号权限。

### 管理扫描目录与封面

打开播放器中的齿轮“设置”，在“新增扫描目录”输入完整路径并点击“添加”，
也可以点击已有目录旁的“移除”；最后点击“保存并扫描”。支持多个目录，至少保留一个。
新增、移除目录和重新扫描均立即生效，**无需重启应用**。目录必须存在且允许应用账号读取；
保存失败时保留原配置。配置保存在 NAS 上，应用以后重启也会保留所有目录。
新增目录后，仍在曲库中的当前歌曲会继续播放；若当前歌曲所在目录被移除，播放器会暂停并重新选择歌曲。

封面优先级为：音频内嵌封面 → 与音频同名的图片 → 同目录中命名为
`cover`、`folder`、`front`、`album` 或 `封面` 的图片 → 本地默认音乐图。
支持 MP3、FLAC、M4A、WAV、Ogg/Opus 等常见格式的内嵌封面，优先选择正面封面。
不会随意使用同目录中不相关的图片，也不再加载网络猫图。
更新音频标签或替换封面后，点击“重新扫描”以刷新显示。

### 修改后重新打包

在飞牛 NAS 上使用 `fnpack` 构建。本版本为 x86_64、Python 3.12 打包；
安装包包含 `app/server/wheels` 中的依赖，安装和启动时无需在线下载 Python 包。

1. 修改 `app/ui/index.html` 中的界面或播放器逻辑，或修改 `app/server/app.py` 中的后端。
2. 每次发布更新前，提高 `manifest` 中的 `version`，例如将 `1.0.3` 改为 `1.0.4`；保持 `appname = fnmusic` 不变。
3. 在仓库根目录执行检查并重新构建：

```bash
/var/apps/python312/target/bin/python3 -m venv .venv
.venv/bin/python -m pip install --no-index --find-links app/server/wheels -r app/server/requirements.txt
node tests/playback-speed.test.mjs
.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
bash -n cmd/main cmd/install_callback cmd/upgrade_callback
fnpack build -d .
```

`fnpack` 将 `fnmusic.fpk` 写入**当前工作目录**，在仓库根目录运行会替换根目录中的旧安装包。
务必部署本次生成的文件。打包需要大小写准确的 `ICON.PNG` 和 `ICON_256.PNG`，仓库已提供。

也可以将构建产物放到单独目录：

```bash
mkdir -p dist
cd dist
fnpack build -d ..
cd ..
```

此时生成的文件是 `dist/fnmusic.fpk`，后续部署命令应使用该路径。

如果修改了 `app/server/requirements.txt`，请先更新离线依赖包。在本机 Python 3.12、
x86_64 Linux 环境执行：

```bash
/var/apps/python312/target/bin/python3 -m venv .venv
.venv/bin/python -m pip download --index-url https://pypi.org/simple \
  --dest app/server/wheels -r app/server/requirements.txt
```

检查并移除被替代的旧版 wheel，再重新打包。在其他系统上下载时，需要明确指定
Python 3.12 和 x86_64 Linux 的目标平台，不能直接将其他平台的二进制 wheel 放入安装包。

### 部署更新

更新前备份 `/var/apps/fnmusic/var/config.json` 和 `favorites.json`（若存在），并保留上一版 FPK。
应用数据目录独立于程序目录，升级回调会更新依赖，并保留现有曲库配置和收藏。

通过飞牛应用中心的“手动安装”选择新 FPK。
本机 `appcenter-cli install-fpk` 对已存在的应用只提示“已安装”，不会替换应用文件，
因此这条命令适用于首次安装，不能用它确认更新成功。

建议通过应用中心的手动安装界面完成更新。
本机实测 `install-local` 会先卸载旧应用，可能清除应用数据，并在重新安装阶段返回
`code 10237`，因此不建议用它直接更新正在使用的应用。
若应用已被卸载，可用已构建的 FPK 恢复；请**明确指定原存储空间**，
本机应用位于存储空间 3：

```bash
sudo appcenter-cli install-fpk ./fnmusic.fpk --volume 3 --env ./install.env
sudo appcenter-cli start fnmusic
sudo appcenter-cli status fnmusic
```

使用首次安装时保存的 `install.env`，或按上面的示例创建。
重新安装后核对并恢复备份中的 `config.json` 和 `favorites.json`（若存在），
保持应用用户对这些文件的读写权限；配置恢复后重启应用以加载原扫描目录。
安装成功后，在浏览器中强制刷新页面；Chrome 桌面端可按 `Ctrl+Shift+R`，
Mac 可按 `Command+Shift+R`。手机端若仍显示旧界面，可清除该网站的缓存后重新打开。

### 验证更新

在 NAS 终端检查网页与实际生效目录：

```bash
curl -fsS http://127.0.0.1:8090/api/config
curl -fsS http://127.0.0.1:8090/api/status
```

打开网页播放音频，依次检查速度选择、切换歌曲后保留速度、刷新后恢复速度，以及切回 `1×`。
再检查歌曲封面和扫描目录的添加、移除、保存后即时生效。
检查喇叭按钮能否切换静音、显示红色带叉图标，并在再次点击后恢复原音量。
可通过 `/var/apps/fnmusic/var/info.log` 查看启动与请求日志。
仓库中的播放器测试使用模拟音频对象，不替代真实浏览器中的布局和听感验证。
