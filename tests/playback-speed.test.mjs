import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';

class Element extends EventTarget {
  constructor() {
    super(); this.value = ''; this.style = {}; this.textContent = ''; this.children = [];
    const classes = new Set();
    this.classList = { add: (...xs) => xs.forEach(x => classes.add(x)), remove: (...xs) => xs.forEach(x => classes.delete(x)), contains: x => classes.has(x) };
    this.parentElement = { classList: this.classList };
  }
  appendChild(e) { this.children.push(e); }
  set textContent(value) { this._textContent = value; this.children = []; }
  get textContent() { return this._textContent; }
  focus() {}
  getBoundingClientRect() { return { left: 0, width: 100 }; }
  setAttribute(k, v) { this[k] = v; }
  removeAttribute(k) { delete this[k]; }
}
class Audio extends Element {
  constructor() { super(); this.src = ''; this.currentTime = 0; this.volume = .7; this.muted = false; this.duration = 180; this.readyState = 1; this.playbackRate = 1; }
  play() { return Promise.resolve(); }
  pause() {}
  load() { this.dispatchEvent(new Event('loadedmetadata')); }
}
const storage = new Map();
const elements = new Map();
const get = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
const document = { getElementById: get, querySelector: get, createElement: () => new Element(), addEventListener() {} };
const ctx = vm.createContext({ document, Audio, console, setTimeout, clearTimeout,
  localStorage: { getItem: k => storage.get(k) ?? null, setItem: (k,v) => storage.set(k,v) },
  window: { addEventListener() {}, location: { origin: 'http://localhost:8090' } } });
const html = fs.readFileSync(new URL('../app/ui/index.html', import.meta.url), 'utf8');
const script = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)][0][1];
new vm.Script(script); // Syntax-check the actual inline script.
vm.runInContext(script.replace('const player = new MusicPlayer();', 'globalThis.MusicPlayer = MusicPlayer;'), ctx);
const Player = ctx.MusicPlayer;
Player.prototype.init = async function () {}; // Skip network startup; exercise the actual player methods below.
const p = new Player();
p.fullPlaylist = p.displayPlaylist = [
  { path: '/music/one.mp3', name: 'one.mp3', type: '.mp3', artist: 'test', album: 'test' },
  { path: '/music/two.mp3', name: 'two.mp3', type: '.mp3', artist: 'test', album: 'test' }
];
p.setupEventListeners();
const select = get('playback-speed');
select.value = '1.75'; select.dispatchEvent(new Event('change'));
assert.equal(p.audio.playbackRate, 1.75);
assert.equal(p.audio.defaultPlaybackRate, 1.75);
assert.equal(p.audio.preservesPitch, true);
assert.equal(JSON.parse(storage.get('fnmusic.playerState')).playbackSpeed, 1.75);
await p.loadSong(0, true);
await p.loadSong(1, true);
assert.equal(p.audio.playbackRate, 1.75, 'next song keeps speed');
p.audio.playbackRate = 1;
p.audio.dispatchEvent(new Event('loadedmetadata'));
assert.equal(p.audio.playbackRate, 1.75, 'metadata reload reapplies speed');
const saved = p.readPersistedState();
const restored = new Player();
restored.fullPlaylist = restored.displayPlaylist = p.fullPlaylist;
await restored.restoreFromState(saved);
assert.equal(restored.audio.playbackRate, 1.75, 'refresh restores speed together with song');
await restored.restoreFromState({ ...saved, playbackSpeed: undefined });
assert.equal(restored.audio.playbackRate, 1, 'older saved state defaults to normal speed');
for (const invalid of [0, -1, 99, 'invalid', null]) {
  restored.setPlaybackSpeed(invalid, false);
  assert.equal(restored.audio.playbackRate, 1, 'invalid speed cannot corrupt player');
}
select.value = '1'; select.dispatchEvent(new Event('change'));
assert.equal(p.audio.playbackRate, 1);
console.log('PASS: actual player handles speed selection, pitch preservation, persistence, next song, metadata reload, restore, old state, invalid state, and 1× reset.');

p.audio.volume = .4;
p.updateVolumeUI();
const speaker = get('mute-btn');
const normalIcon = speaker.innerHTML;
speaker.dispatchEvent(new Event('click'));
assert.equal(p.audio.muted, true, 'speaker click actually mutes audio');
assert.equal(p.audio.volume, .4, 'mute preserves the selected volume');
assert.equal(speaker['aria-pressed'], 'true');
assert.equal(speaker.style.color, '#f87171');
assert.notEqual(speaker.innerHTML, normalIcon, 'muted icon visibly changes');
assert.equal(JSON.parse(storage.get('fnmusic.playerState')).muted, true);
await restored.restoreFromState(p.readPersistedState());
assert.equal(restored.audio.muted, true, 'refresh restores mute');
await p.loadSong(1, true);
assert.equal(p.audio.muted, true, 'switching songs stays muted');
speaker.dispatchEvent(new Event('click'));
assert.equal(p.audio.muted, false);
assert.equal(p.audio.volume, .4);
assert.equal(speaker.innerHTML, normalIcon);
assert.equal(speaker['aria-pressed'], 'false');
p.audio.volume = 0;
p.audio.dispatchEvent(new Event('volumechange'));
assert.equal(speaker['aria-pressed'], 'true', 'zero volume displays the muted icon');
speaker.dispatchEvent(new Event('click'));
assert.equal(p.audio.volume, .4, 'clicking at zero volume restores the last audible volume');
speaker.dispatchEvent(new Event('click'));
const drag = new Event('mousedown');
Object.defineProperty(drag, 'clientX', { value: 60 });
get('volume-container').dispatchEvent(drag);
assert.equal(p.audio.volume, .6);
assert.equal(p.audio.muted, false, 'raising the volume cancels mute');
await restored.restoreFromState({ ...saved, muted: undefined });
assert.equal(restored.audio.muted, false, 'old saved states default to unmuted');
console.log('PASS: speaker toggles mute, changes icon/color, preserves volume across songs and refresh, restores zero volume, and unmutes on volume adjustment.');

let directories = ['/music'];
const librarySongs = [...p.fullPlaylist, { path: '/more/three.mp3', name: 'three.mp3', type: '.mp3' }];
ctx.fetch = async (url, options) => {
  if (url === '/api/config') return { ok: true, json: async () => ({ music_directories: [...directories] }) };
  if (url === '/api/config/music_directories') {
    directories = JSON.parse(options.body).music_directories;
    return { ok: true, json: async () => ({ music_directories: [...directories] }) };
  }
  if (url === '/api/files') return { ok: true, json: async () => librarySongs.filter(song => directories.some(path => song.path.startsWith(path + '/'))) };
  throw Error(`Unexpected request: ${url}`);
};
await p.loadSong(0, true);
p.audio.currentTime = 25;
p.setPlaybackSpeed(1.5, false);
await p.openSettings();
assert.equal(p.settingsDirectories.length, 1);
get('settings-music-dir').value = '/more/';
p.addScanDirectory();
get('settings-music-dir').value = '/more/';
p.addScanDirectory();
assert.equal(p.settingsDirectories.length, 2, 'duplicate draft directories are ignored');
await p.saveSettings();
assert.deepEqual(directories, ['/music', '/more']);
assert.equal(p.fullPlaylist.length, 3);
assert.equal(p.audio.currentTime, 25, 'adding a directory does not interrupt the current song');
assert.equal(p.isPlaying, true);
assert.equal(p.audio.playbackRate, 1.5);
get('settings-directories').children[0].children[1].dispatchEvent(new Event('click'));
await p.saveSettings();
assert.deepEqual(directories, ['/more']);
assert.equal(p.fullPlaylist.length, 1);
assert.equal(p.getCurrentSongPath(), '/more/three.mp3');
assert.equal(p.isPlaying, false, 'removing the current song directory selects another song without autoplay');
p.updateSongCover({ cover_url: '/api/cover?path=test' });
assert.equal(get('album-cover').src, '/api/cover?path=test');
get('album-cover').onerror();
assert.equal(get('album-cover').src, '/images/default-cover.svg');
assert.equal(html.includes('picsum.photos'), false);
console.log('PASS: settings load, add, deduplicate, save, scan, remove, preserve playback, and use local artwork fallback.');
