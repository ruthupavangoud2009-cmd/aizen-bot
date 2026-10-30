import { getRealtimeApiBase } from './api.js';

const query = new URLSearchParams(location.search);
const fragment = new URLSearchParams(location.hash.slice(1));
const roomId = query.get('room') || '';
const key = fragment.get('key') || '';
const clientStorageKey = `kyoka-watch-${roomId}`;
let clientId = localStorage.getItem(clientStorageKey);
if (!clientId || !/^[A-Za-z0-9_-]{12,64}$/.test(clientId)) {
  clientId = crypto.randomUUID().replaceAll('-', '');
  localStorage.setItem(clientStorageKey, clientId);
}

const apiBase = getRealtimeApiBase().replace(/\/$/, '');
const video = document.querySelector('#video');
const statusBadge = document.querySelector('#status-badge');
const emptyState = document.querySelector('#empty-state');
const sourceWrap = document.querySelector('#host-source');
const screenMessage = document.querySelector('#screen-message');
const connectionLabel = document.querySelector('#connection-label');
const seek = document.querySelector('#seek');
const timeLabel = document.querySelector('#time-label');
const playButton = document.querySelector('#play-btn');
const stopButton = document.querySelector('#stop-btn');
const membersNode = document.querySelector('#members');
const audioGate = document.querySelector('#audio-gate');
const toastNode = document.querySelector('#toast');

let socket;
let host = false;
let status = 'idle';
let currentSource = '';
let pendingState = null;
let reconnectDelay = 1000;
let reconnectTimer;
let tickTimer;
let suppressSeek = false;
let toastTimer;
let joined = false;

function toast(message, error = false) {
  toastNode.textContent = message;
  toastNode.classList.toggle('error', error);
  toastNode.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastNode.classList.remove('show'), 2800);
}

function fmt(seconds) {
  if (!Number.isFinite(seconds)) return '00:00';
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h ? `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function setStatus(value) {
  status = value || 'idle';
  statusBadge.textContent = status.toUpperCase();
  playButton.textContent = status === 'playing' ? 'Ⅱ' : '▶';
  stopButton.hidden = !host;
}

function updateTime() {
  const duration = Number.isFinite(video.duration) ? video.duration : 0;
  timeLabel.textContent = `${fmt(video.currentTime)} / ${fmt(duration)}`;
  if (!seek.matches(':active')) {
    seek.max = String(duration);
    seek.value = String(video.currentTime || 0);
  }
}

function setMembers(members = []) {
  membersNode.replaceChildren();
  members.forEach((member) => {
    const item = document.createElement('li');
    const avatar = document.createElement('span');
    avatar.className = 'avatar';
    avatar.textContent = (member.display_name || 'V').slice(-1).toUpperCase();
    const label = document.createElement('span');
    label.textContent = member.display_name || 'Viewer';
    item.append(avatar, label);
    if ((member.display_name || '').startsWith('Host ')) {
      const badge = document.createElement('span');
      badge.className = 'host-tag';
      badge.textContent = 'HOST';
      item.append(badge);
    }
    membersNode.append(item);
  });
  document.querySelector('#member-count').textContent = String(members.length);
  document.querySelector('#viewer-count').textContent = `${members.length} / ${window.roomMax || 25}`;
}

function sendControl(action, currentTime = video.currentTime || 0, source = undefined) {
  if (!host || !socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: 'control', action, currentTime, ...(source ? { source } : {}) }));
}

async function applyState(state) {
  if (typeof state.isHost === 'boolean') host = state.isHost;
  sourceWrap.hidden = !host;
  if (host) {
    const inviteToken = fragment.get('invite');
    document.querySelector('#copy-invite').dataset.link = inviteToken
      ? `${location.origin}${location.pathname}?room=${encodeURIComponent(roomId)}#key=${encodeURIComponent(inviteToken)}`
      : location.href;
  }
  window.roomMax = state.maxMembers || 25;
  document.querySelector('#room-id').textContent = state.roomId || roomId;
  document.querySelector('#host-label').textContent = state.hostId ? `Discord user ${state.hostId}` : 'KYOKA host';
  if (state.members) setMembers(state.members);

  const source = state.source || '';
  emptyState.hidden = Boolean(source);
  seek.disabled = !source || !host;
  playButton.disabled = !source || !host;
  if (source && source !== currentSource) {
    currentSource = source;
    video.src = source;
    document.querySelector('#source-url').value = host ? source : '';
    pendingState = state;
    video.load();
  } else {
    pendingState = state;
    if (video.readyState >= 1) syncMedia(state);
  }
  setStatus(state.status);
  if (state.status === 'playing' && !joined) audioGate.hidden = false;
}

function syncMedia(state) {
  const expected = Number(state.currentTime || 0);
  if (Math.abs(video.currentTime - expected) > 0.8) {
    suppressSeek = true;
    try { video.currentTime = expected; } catch { /* Metadata may still be loading. */ }
    setTimeout(() => { suppressSeek = false; }, 250);
  }
  if (state.status === 'playing') {
    video.play().then(() => { audioGate.hidden = true; }).catch(() => { audioGate.hidden = false; });
  } else {
    video.pause();
    if (state.status === 'stopped') {
      suppressSeek = true;
      video.currentTime = 0;
      setTimeout(() => { suppressSeek = false; }, 250);
    }
    audioGate.hidden = true;
  }
  updateTime();
}

function onSocketMessage(event) {
  let message;
  try { message = JSON.parse(event.data); } catch { return; }
  if (message.type === 'state') {
    applyState(message);
  } else if (message.type === 'members') {
    setMembers(message.members || []);
  } else if (message.type === 'closed') {
    setStatus('closed');
    video.pause();
    video.removeAttribute('src');
    emptyState.hidden = false;
    emptyState.querySelector('h2').textContent = 'This room is closed';
    audioGate.hidden = true;
    connectionLabel.textContent = 'Room closed';
    if (socket) socket.close();
  } else if (message.type === 'host_changed') {
    host = false;
    sourceWrap.hidden = true;
    playButton.disabled = true;
    seek.disabled = true;
    stopButton.hidden = true;
    toast('Room ownership changed. Playback controls are now host-only.');
  } else if (message.type === 'error') {
    toast(message.message || 'Playback action was rejected.', true);
  }
}

function connect() {
  if (!roomId || !key) {
    statusBadge.textContent = 'INVALID LINK';
    screenMessage.textContent = 'This invitation is incomplete. Ask the host for a new link.';
    return;
  }
  const wsBase = new URL(apiBase, location.href).href.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
  socket = new WebSocket(`${wsBase}/watch/${encodeURIComponent(roomId)}/ws?key=${encodeURIComponent(key)}&client=${encodeURIComponent(clientId)}`);
  socket.addEventListener('open', () => {
    reconnectDelay = 1000;
    connectionLabel.textContent = 'Connected · syncing room state';
    screenMessage.textContent = '';
  });
  socket.addEventListener('message', onSocketMessage);
  socket.addEventListener('error', () => { connectionLabel.textContent = 'Connection interrupted'; });
  socket.addEventListener('close', () => {
    connectionLabel.textContent = 'Reconnecting…';
    if (status !== 'closed' && !joined) {
      clearTimeout(reconnectTimer);
      reconnectTimer = setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(30000, reconnectDelay * 2);
    }
  });
}

function installControls() {
  playButton.addEventListener('click', () => {
    if (!host) return;
    if (status === 'playing') sendControl('pause');
    else if (currentSource) sendControl('play', video.currentTime || 0, currentSource);
  });
  document.querySelector('#load-btn').addEventListener('click', () => {
    const source = document.querySelector('#source-url').value.trim();
    if (!/^https:\/\/[^ ]+\.(mp4|m4v|webm|ogv|ogg)(\?.*)?$/i.test(source)) {
      toast('Use a direct HTTPS MP4, M4V, WebM, OGV or OGG URL.', true);
      return;
    }
    sendControl('play', 0, source);
  });
  document.querySelector('#stop-btn').addEventListener('click', () => sendControl('stop', 0));
  seek.addEventListener('change', () => {
    if (!host) return;
    const position = Number(seek.value);
    sendControl('seek', position);
  });
  seek.addEventListener('input', () => { timeLabel.textContent = `${fmt(Number(seek.value))} / ${fmt(video.duration || 0)}`; });
  document.querySelector('#volume').addEventListener('input', (event) => { video.volume = Number(event.target.value); });
  document.querySelector('#fullscreen-btn').addEventListener('click', () => {
    const target = document.querySelector('.screen');
    if (document.fullscreenElement) document.exitFullscreen();
    else target.requestFullscreen?.();
  });
  audioGate.addEventListener('click', async () => {
    video.muted = false;
    try {
      await video.play();
      audioGate.hidden = true;
      if (status !== 'playing') video.pause();
    } catch { toast('The source could not start. Check its URL and playback permissions.', true); }
  });
  document.querySelector('#copy-invite').addEventListener('click', async () => {
    const link = document.querySelector('#copy-invite').dataset.link || location.href;
    try {
      let invitation = link;
      if (host) {
        const response = await fetch(`${apiBase}/watch/${encodeURIComponent(roomId)}/invite`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key }),
        });
        if (!response.ok) throw new Error('Could not generate an invitation link.');
        invitation = (await response.json()).inviteUrl;
      }
      await navigator.clipboard.writeText(invitation);
      toast('Invitation link copied.');
    } catch {
      toast('Clipboard access is unavailable in this browser.', true);
    }
  });
  document.querySelector('#leave-btn').addEventListener('click', () => {
    joined = true;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: 'leave' }));
    socket?.close();
    video.pause();
    connectionLabel.textContent = 'You left the room';
    toast('You left the Watch Party.');
  });
  video.addEventListener('loadedmetadata', () => { if (pendingState) syncMedia(pendingState); });
  video.addEventListener('durationchange', updateTime);
  video.addEventListener('timeupdate', updateTime);
  video.addEventListener('error', () => {
    screenMessage.textContent = 'The video could not load. The source may be unavailable or block browser playback.';
    toast('Video load failed. Check source availability and CORS/media permissions.', true);
  });
}

async function initialize() {
  installControls();
  if (!roomId || !key) {
    connect();
    return;
  }
  try {
    const response = await fetch(`${apiBase}/watch/${encodeURIComponent(roomId)}/state?key=${encodeURIComponent(key)}`);
    if (!response.ok) throw new Error(response.status === 410 ? 'This room expired.' : 'Invitation invalid or room unavailable.');
    const state = await response.json();
    await applyState(state);
    connect();
  } catch (error) {
    statusBadge.textContent = 'UNAVAILABLE';
    screenMessage.textContent = error.message || 'Could not load this Watch Party.';
  }
  if (host) {
    tickTimer = setInterval(() => {
      if (status === 'playing') sendControl('tick', video.currentTime || 0);
    }, 4000);
  }
}

initialize();
window.addEventListener('beforeunload', () => {
  clearInterval(tickTimer);
  clearTimeout(reconnectTimer);
  if (socket?.readyState === WebSocket.OPEN) socket.close();
});
