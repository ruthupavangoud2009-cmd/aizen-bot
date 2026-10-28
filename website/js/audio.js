/**
 * KYOKA 3.0 — Aizen Atmospheric Ambient Music Engine
 * Sovereign Bleach/Kyōka Suigetsu Soundscape with Full User Controls
 * 
 * Features:
 * - 100% compliant with browser autoplay policies: only plays after explicit user interaction.
 * - Dual-mode engine: checks for local atmospheric audio asset (/assets/audio/aizen_ambient.mp3),
 *   and seamlessly falls back to procedural Web Audio API spiritual-pressure drone if no file is present.
 * - Equalizer visualizer, play/pause, volume slider (default: 20%), and mute controls.
 * - Smooth exponential gain ramping (zero pops/clicks).
 * - State persisted in localStorage across pages.
 */

class AizenAtmosphericAudio {
  constructor() {
    this.audioEl = null;
    this.webAudioCtx = null;
    this.proceduralNodes = null;
    this.isPlaying = false;
    this.isMuted = localStorage.getItem('aizen_music_muted') === 'true';
    this.volume = parseFloat(localStorage.getItem('aizen_music_vol') || '0.20');
    this.userHasEngaged = false;
    this.domMounted = false;
  }

  init() {
    if (this.domMounted) return;
    this.createControlsDOM();
    this.attachEvents();
    this.domMounted = true;
  }

  createControlsDOM() {
    let dock = document.getElementById('aizen-audio-dock');
    if (!dock) {
      dock = document.createElement('div');
      dock.id = 'aizen-audio-dock';
      dock.className = 'aizen-audio-dock';
      dock.setAttribute('role', 'region');
      dock.setAttribute('aria-label', 'Atmospheric Audio Player');
      document.body.appendChild(dock);
    }

    dock.innerHTML = `
      <div class="audio-pill">
        <button id="audio-play-btn" class="audio-ctrl-btn" aria-label="Play or Pause Ambient Music" title="Play / Pause Spiritual Pressure Ambient">
          <span class="audio-icon-play">▶</span>
          <span class="audio-icon-pause" style="display: none;">❚❚</span>
        </button>

        <div class="audio-meta">
          <div class="audio-title">
            <span class="audio-title-text">Kyōka Suigetsu Ambient</span>
            <div class="audio-eq" id="audio-eq" aria-hidden="true">
              <span class="eq-bar"></span>
              <span class="eq-bar"></span>
              <span class="eq-bar"></span>
            </div>
          </div>
          <div class="audio-status" id="audio-status-text">Click to enable soundtrack</div>
        </div>

        <div class="audio-volume-group">
          <button id="audio-mute-btn" class="audio-ctrl-btn" aria-label="Mute or Unmute" title="Mute / Unmute">
            <span id="audio-mute-icon">${this.isMuted ? '🔇' : '🔊'}</span>
          </button>
          <input type="range" id="audio-volume-slider" class="audio-slider" min="0" max="100" value="${Math.round(this.volume * 100)}" aria-label="Soundtrack Volume" title="Volume Slider" />
        </div>

        <button id="audio-minimize-btn" class="audio-ctrl-btn audio-min-btn" aria-label="Minimize or Expand Player" title="Minimize Soundtrack Dock" style="width: 26px; height: 26px; font-size: 0.7rem; background: rgba(255,255,255,0.06); border: 1px solid rgba(168,85,247,0.25); margin-left: 0.2rem;">
          <span id="audio-min-icon">▾</span>
        </button>
      </div>
    `;

    this.updateUIState();
  }

  attachEvents() {
    const playBtn = document.getElementById('audio-play-btn');
    const muteBtn = document.getElementById('audio-mute-btn');
    const slider = document.getElementById('audio-volume-slider');
    const minBtn = document.getElementById('audio-minimize-btn');
    const dock = document.getElementById('aizen-audio-dock');

    minBtn?.addEventListener('click', (e) => {
      e.stopPropagation();
      dock?.classList.toggle('minimized');
      const icon = document.getElementById('audio-min-icon');
      if (icon) {
        icon.textContent = dock?.classList.contains('minimized') ? '🎵' : '▾';
      }
    });

    playBtn?.addEventListener('click', () => {
      this.userHasEngaged = true;
      this.togglePlay();
    });

    muteBtn?.addEventListener('click', () => {
      this.toggleMute();
    });

    slider?.addEventListener('input', (e) => {
      const val = parseFloat(e.target.value) / 100;
      this.setVolume(val);
    });
  }

  async togglePlay() {
    if (this.isPlaying) {
      this.pause();
    } else {
      await this.play();
    }
  }

  async play() {
    this.initWebAudio();
    if (this.webAudioCtx && this.webAudioCtx.state === 'suspended') {
      try {
        await this.webAudioCtx.resume();
      } catch {}
    }

    // Attempt local file first
    if (!this.audioEl) {
      this.audioEl = new Audio('/assets/audio/aizen_ambient.mp3');
      this.audioEl.loop = true;
      this.audioEl.volume = this.isMuted ? 0 : this.volume;
      this.audioEl.addEventListener('error', () => {
        // Fall back to procedural ambient synthesis seamlessly
        this.startProceduralAmbient();
      });
    }

    try {
      await this.audioEl.play();
      this.isPlaying = true;
    } catch {
      // Autoplay or 404 blocked audio element; start synthetic procedural ambient
      this.startProceduralAmbient();
      this.isPlaying = true;
    }

    this.updateUIState();
  }

  pause() {
    if (this.audioEl) {
      try { this.audioEl.pause(); } catch {}
    }
    this.stopProceduralAmbient();
    this.isPlaying = false;
    this.updateUIState();
  }

  toggleMute() {
    this.isMuted = !this.isMuted;
    localStorage.setItem('aizen_music_muted', this.isMuted ? 'true' : 'false');

    if (this.audioEl) {
      this.audioEl.volume = this.isMuted ? 0 : this.volume;
    }
    if (this.proceduralNodes && this.proceduralNodes.masterGain) {
      const now = this.webAudioCtx.currentTime;
      const targetGain = this.isMuted ? 0 : this.volume * 0.15;
      this.proceduralNodes.masterGain.gain.linearRampToValueAtTime(targetGain, now + 0.1);
    }

    this.updateUIState();
  }

  setVolume(vol) {
    this.volume = Math.max(0, Math.min(1, vol));
    localStorage.setItem('aizen_music_vol', this.volume.toString());

    if (this.isMuted && this.volume > 0) {
      this.isMuted = false;
      localStorage.setItem('aizen_music_muted', 'false');
    }

    if (this.audioEl) {
      this.audioEl.volume = this.isMuted ? 0 : this.volume;
    }
    if (this.proceduralNodes && this.proceduralNodes.masterGain) {
      const now = this.webAudioCtx.currentTime;
      const targetGain = this.isMuted ? 0 : this.volume * 0.15;
      this.proceduralNodes.masterGain.gain.linearRampToValueAtTime(targetGain, now + 0.05);
    }

    this.updateUIState();
  }

  initWebAudio() {
    if (!this.webAudioCtx && typeof window !== 'undefined') {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.webAudioCtx = new AudioCtx();
      }
    }
  }

  /**
   * Procedural Ambient Soundscape
   * Generates a mysterious, deep Bleach Las Noches atmospheric drone.
   * Low-passed fundamental drone at 108Hz / 162Hz + soothing spiritual pressure whisper.
   */
  startProceduralAmbient() {
    this.initWebAudio();
    if (!this.webAudioCtx) return;
    if (this.proceduralNodes) return; // already active

    try {
      const ctx = this.webAudioCtx;
      const now = ctx.currentTime;

      // Master output gain
      const masterGain = ctx.createGain();
      const initialGain = this.isMuted ? 0 : this.volume * 0.15;
      masterGain.gain.setValueAtTime(0, now);
      masterGain.gain.linearRampToValueAtTime(initialGain, now + 1.2);
      masterGain.connect(ctx.destination);

      // Low-pass filter for dark, warm atmosphere
      const filter = ctx.createBiquadFilter();
      filter.type = 'lowpass';
      filter.frequency.setValueAtTime(260, now);
      filter.Q.setValueAtTime(3.0, now);
      filter.connect(masterGain);

      // Oscillator 1: Root Drone (A2 / 108Hz)
      const osc1 = ctx.createOscillator();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(108, now);
      const osc1Gain = ctx.createGain();
      osc1Gain.gain.setValueAtTime(0.6, now);
      osc1.connect(osc1Gain);
      osc1Gain.connect(filter);
      osc1.start(now);

      // Oscillator 2: Perfect 5th Harmonics (E3 / 162Hz) with subtle detune
      const osc2 = ctx.createOscillator();
      osc2.type = 'triangle';
      osc2.frequency.setValueAtTime(162, now);
      osc2.detune.setValueAtTime(4, now);
      const osc2Gain = ctx.createGain();
      osc2Gain.gain.setValueAtTime(0.35, now);
      osc2.connect(osc2Gain);
      osc2Gain.connect(filter);
      osc2.start(now);

      // LFO for slow atmospheric breathing (0.08Hz)
      const lfo = ctx.createOscillator();
      lfo.type = 'sine';
      lfo.frequency.setValueAtTime(0.08, now);
      const lfoGain = ctx.createGain();
      lfoGain.gain.setValueAtTime(45, now); // modulates filter cutoff +/- 45Hz
      lfo.connect(lfoGain);
      lfoGain.connect(filter.frequency);
      lfo.start(now);

      this.proceduralNodes = {
        masterGain,
        filter,
        osc1,
        osc2,
        lfo,
      };
    } catch (e) {
      console.debug('Procedural ambient audio notice:', e);
    }
  }

  stopProceduralAmbient() {
    if (!this.proceduralNodes || !this.webAudioCtx) return;
    try {
      const ctx = this.webAudioCtx;
      const now = ctx.currentTime;
      const { masterGain, osc1, osc2, lfo } = this.proceduralNodes;

      masterGain.gain.linearRampToValueAtTime(0, now + 0.6);
      setTimeout(() => {
        try {
          osc1.stop();
          osc2.stop();
          lfo.stop();
          osc1.disconnect();
          osc2.disconnect();
          masterGain.disconnect();
        } catch {}
        this.proceduralNodes = null;
      }, 700);
    } catch {
      this.proceduralNodes = null;
    }
  }

  updateUIState() {
    const playIcon = document.querySelector('.audio-icon-play');
    const pauseIcon = document.querySelector('.audio-icon-pause');
    const eq = document.getElementById('audio-eq');
    const statusText = document.getElementById('audio-status-text');
    const muteIcon = document.getElementById('audio-mute-icon');
    const slider = document.getElementById('audio-volume-slider');

    if (playIcon && pauseIcon) {
      playIcon.style.display = this.isPlaying ? 'none' : 'inline-block';
      pauseIcon.style.display = this.isPlaying ? 'inline-block' : 'none';
    }

    if (eq) {
      if (this.isPlaying && !this.isMuted) {
        eq.classList.add('playing');
      } else {
        eq.classList.remove('playing');
      }
    }

    if (statusText) {
      if (this.isPlaying) {
        statusText.textContent = this.isMuted ? 'Atmosphere Muted' : 'Playing Spiritual Pressure';
        statusText.style.color = this.isMuted ? 'var(--amber-accent)' : 'var(--purple-light)';
      } else {
        statusText.textContent = 'Soundtrack Paused';
        statusText.style.color = 'var(--text-dim)';
      }
    }

    if (muteIcon) {
      muteIcon.textContent = (this.isMuted || this.volume === 0) ? '🔇' : (this.volume < 0.4 ? '🔉' : '🔊');
    }

    if (slider) {
      slider.value = Math.round(this.volume * 100);
    }
  }
}

export const aizenAudio = new AizenAtmosphericAudio();

// Auto-mount when DOM is ready
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => aizenAudio.init());
  } else {
    aizenAudio.init();
  }
}
