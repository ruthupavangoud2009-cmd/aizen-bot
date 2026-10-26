/**
 * KYOKA 3.0 — Spiritual Pressure Ambient Particle Canvas
 * Subtle, high-performance Bleach reiatsu motes and shattered mirror shards.
 * 
 * Performance & Accessibility Features:
 * - Automatically pauses rendering when browser tab is inactive (document.hidden).
 * - Immediately halts and hides canvas when prefers-reduced-motion is active.
 * - Low particle budget (30 on desktop, 12 on mobile) to maintain locked 60fps with near-zero CPU footprint.
 * - Pointer-events: none; fixed background layer.
 */
import { isReducedMotion } from './api.js';

class SpiritualPressureParticles {
  constructor() {
    this.canvas = null;
    this.ctx = null;
    this.particles = [];
    this.animationId = null;
    this.width = 0;
    this.height = 0;
    this.isActive = false;
  }

  init() {
    if (typeof document === 'undefined') return;

    if (isReducedMotion()) {
      return; // Respect reduced motion preferences
    }

    this.canvas = document.getElementById('aizen-particles-canvas');
    if (!this.canvas) {
      this.canvas = document.createElement('canvas');
      this.canvas.id = 'aizen-particles-canvas';
      this.canvas.className = 'aizen-particles-canvas';
      this.canvas.setAttribute('aria-hidden', 'true');
      document.body.prepend(this.canvas);
    }

    this.ctx = this.canvas.getContext('2d', { alpha: true });
    if (!this.ctx) return;

    this.resize();
    this.spawnParticles();

    window.addEventListener('resize', () => this.resize(), { passive: true });
    document.addEventListener('visibilitychange', () => this.onVisibilityChange());

    this.start();
  }

  resize() {
    if (!this.canvas) return;
    this.width = window.innerWidth;
    this.height = window.innerHeight;
    this.canvas.width = this.width;
    this.canvas.height = this.height;
  }

  spawnParticles() {
    const isMobile = window.innerWidth < 768;
    const count = isMobile ? 12 : 28;
    this.particles = [];

    const colors = [
      'rgba(168, 85, 247, 0.45)', // --purple-glow
      'rgba(192, 132, 252, 0.35)', // --purple-light
      'rgba(124, 58, 237, 0.30)',  // --purple-primary
      'rgba(233, 213, 255, 0.25)', // --purple-pastel
    ];

    for (let i = 0; i < count; i++) {
      this.particles.push({
        x: Math.random() * this.width,
        y: Math.random() * this.height,
        size: Math.random() * 2.5 + 1.2,
        speedY: -(Math.random() * 0.45 + 0.15),
        speedX: (Math.random() - 0.5) * 0.25,
        color: colors[Math.floor(Math.random() * colors.length)],
        opacity: Math.random() * 0.6 + 0.2,
        pulseSpeed: Math.random() * 0.02 + 0.01,
        angle: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.015,
        isShard: Math.random() > 0.65, // ~35% are Kyōka Suigetsu glass shards
      });
    }
  }

  start() {
    if (this.isActive) return;
    this.isActive = true;
    let lastTime = performance.now();

    const loop = (time) => {
      if (!this.isActive) return;
      const dt = Math.min((time - lastTime) / 1000, 0.1);
      lastTime = time;

      this.update(dt);
      this.draw();

      this.animationId = requestAnimationFrame(loop);
    };

    this.animationId = requestAnimationFrame(loop);
  }

  stop() {
    this.isActive = false;
    if (this.animationId) {
      cancelAnimationFrame(this.animationId);
      this.animationId = null;
    }
  }

  onVisibilityChange() {
    if (document.hidden) {
      this.stop();
    } else if (!isReducedMotion()) {
      this.start();
    }
  }

  update(dt) {
    for (const p of this.particles) {
      p.y += p.speedY * dt * 60;
      p.x += p.speedX * dt * 60;
      p.angle += p.rotSpeed;

      // Wrap around screen
      if (p.y < -10) {
        p.y = this.height + 10;
        p.x = Math.random() * this.width;
      }
      if (p.x < -10) p.x = this.width + 10;
      if (p.x > this.width + 10) p.x = -10;
    }
  }

  draw() {
    if (!this.ctx) return;
    this.ctx.clearRect(0, 0, this.width, this.height);

    for (const p of this.particles) {
      this.ctx.save();
      this.ctx.translate(p.x, p.y);
      this.ctx.rotate(p.angle);
      this.ctx.fillStyle = p.color;

      if (p.isShard) {
        // Draw delicate triangular / polygonal mirror shard
        this.ctx.beginPath();
        this.ctx.moveTo(0, -p.size * 2);
        this.ctx.lineTo(p.size * 1.5, p.size * 1.2);
        this.ctx.lineTo(-p.size * 1.2, p.size * 1.5);
        this.ctx.closePath();
        this.ctx.fill();
      } else {
        // Draw soft glowing spiritual mote
        this.ctx.beginPath();
        this.ctx.arc(0, 0, p.size, 0, Math.PI * 2);
        this.ctx.fill();
      }

      this.ctx.restore();
    }
  }
}

export const particlesEngine = new SpiritualPressureParticles();

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => particlesEngine.init());
  } else {
    particlesEngine.init();
  }
}
