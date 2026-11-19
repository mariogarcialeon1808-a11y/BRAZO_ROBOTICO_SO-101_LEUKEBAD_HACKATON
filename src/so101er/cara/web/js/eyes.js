// Cara estilo Cozmo/EMO dibujada en canvas. Cada estado define unos
// parámetros objetivo; cada fotograma los interpolamos suavemente hacia ellos.

export const STATES = ["IDLE", "LISTENING", "THINKING", "TALKING", "HAPPY", "SAD", "ERROR", "SLEEP"];

const CYAN = [60, 220, 255];

// w, h: tamaño del ojo (px a 1080p) · r: redondez (0-1)
// lidIn/lidOut: párpado superior en el lado interior/exterior (0-1 del alto)
// happy: recorte inferior en arco (ojos ^ ^) · lookX/lookY: mirada
// mouth: 0 oculta, 1 visible · smile: >0 sonrisa, <0 tristeza
const PRESETS = {
  IDLE:      { w: 250, h: 300, r: 0.32, gap: 170, lidIn: 0,    lidOut: 0,    happy: 0, lookX: 0,   lookY: 0,   color: CYAN,           mouth: 0, smile: 0 },
  LISTENING: { w: 270, h: 330, r: 0.36, gap: 160, lidIn: 0,    lidOut: 0,    happy: 0, lookX: 0,   lookY: -6,  color: [80, 235, 255], mouth: 0, smile: 0 },
  THINKING:  { w: 240, h: 230, r: 0.30, gap: 175, lidIn: 0.12, lidOut: 0.18, happy: 0, lookX: 70,  lookY: -60, color: CYAN,           mouth: 0, smile: 0 },
  TALKING:   { w: 250, h: 270, r: 0.32, gap: 170, lidIn: 0,    lidOut: 0,    happy: 0, lookX: 0,   lookY: -20, color: CYAN,           mouth: 1, smile: 0 },
  HAPPY:     { w: 260, h: 260, r: 0.40, gap: 165, lidIn: 0,    lidOut: 0,    happy: 1, lookX: 0,   lookY: -10, color: [90, 255, 200], mouth: 1, smile: 1 },
  SAD:       { w: 240, h: 220, r: 0.30, gap: 185, lidIn: 0,    lidOut: 0.45, happy: 0, lookX: 0,   lookY: 40,  color: [70, 140, 255], mouth: 1, smile: -1 },
  ERROR:     { w: 230, h: 200, r: 0.18, gap: 190, lidIn: 0.42, lidOut: 0.05, happy: 0, lookX: 0,   lookY: 0,   color: [255, 60, 60],  mouth: 0, smile: 0 },
  SLEEP:     { w: 250, h: 14,  r: 0.50, gap: 170, lidIn: 0,    lidOut: 0,    happy: 0, lookX: 0,   lookY: 50,  color: [40, 110, 140], mouth: 0, smile: 0 },
};

const NUMERIC = ["w", "h", "r", "gap", "lidIn", "lidOut", "happy", "lookX", "lookY", "mouth", "smile"];

// Ánimo que toma la cara mientras habla, según el gesto que hacen los brazos. Son
// incrementos sobre TALKING: la boca sigue hablando.
const ANIMOS = {
  neutro:    {},
  alegre:    { happy: 0.55, smile: 0.35, h: -10, color: [90, 255, 200] },
  serio:     { lidIn: 0.15, lidOut: 0.03, h: -24 },
  atento:    { w: 14, h: 46, lookY: -6 },
  duda:      { lidOut: 0.30, lidIn: 0.04, lookY: 12 },
  pensativo: { lidIn: 0.10, lidOut: 0.16, lookY: -28 },
};
const MIRADA_X = 95;   // cuánto se van los ojos hacia el brazo que gesticula
const MIRADA_Y = 60;   // y hacia arriba o abajo con el gesto

function approach(cur, target, dt, speed) {
  return cur + (target - cur) * (1 - Math.exp(-dt * speed));
}

export class Face {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.state = "IDLE";
    this.p = structuredClone(PRESETS.IDLE);
    this.p.color = [...CYAN];
    this.volume = 0;         // 0-1, volumen real del audio del agente
    this.mouthOpen = 0;
    this.blink = 0;          // 0 abierto, 1 cerrado
    this.blinkPhase = null;
    this.nextBlink = performance.now() + 2000;
    this.gaze = { x: 0, y: 0, tx: 0, ty: 0, next: 0 };
    this.gesto = { lado: 0, vertical: 0, animo: "neutro" };
    this.last = performance.now();
    this.t0 = this.last;
  }

  setState(state) {
    if (PRESETS[state]) this.state = state;
  }

  // Gesto de los brazos en curso: hacia qué lado mirar (-1 izquierda, 1 derecha), si arriba o abajo
  // (1, -1) y con qué ánimo. Solo se nota mientras habla.
  setGesto(g) {
    this.gesto = {
      lado: Math.max(-1, Math.min(1, Number(g?.lado) || 0)),
      vertical: Math.max(-1, Math.min(1, Number(g?.vertical) || 0)),
      animo: ANIMOS[g?.animo] ? g.animo : "neutro",
    };
  }

  setVolume(v) {
    this.volume = Math.max(0, Math.min(1, v || 0));
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const { clientWidth: w, clientHeight: h } = this.canvas;
    if (this.canvas.width !== Math.round(w * dpr) || this.canvas.height !== Math.round(h * dpr)) {
      this.canvas.width = Math.round(w * dpr);
      this.canvas.height = Math.round(h * dpr);
    }
  }

  _updateBlink(now) {
    if (this.state === "SLEEP") {
      this.blink = 0;
      this.blinkPhase = null;
      return;
    }
    if (this.blinkPhase === null && now >= this.nextBlink) {
      this.blinkPhase = now;
    }
    if (this.blinkPhase !== null) {
      const t = now - this.blinkPhase;
      const CLOSE = 70, OPEN = 120;
      if (t < CLOSE) this.blink = t / CLOSE;
      else if (t < CLOSE + OPEN) this.blink = 1 - (t - CLOSE) / OPEN;
      else {
        this.blink = 0;
        this.blinkPhase = null;
        // A veces, doble parpadeo.
        this.nextBlink = now + (Math.random() < 0.15 ? 180 : 2200 + Math.random() * 4000);
      }
    }
  }

  _updateGaze(now, dt) {
    const g = this.gaze;
    if (now >= g.next) {
      if (this.state === "IDLE") {
        g.tx = (Math.random() * 2 - 1) * 70;
        g.ty = (Math.random() * 2 - 1) * 30;
        g.next = now + 1200 + Math.random() * 2800;
      } else if (this.state === "TALKING") {
        g.tx = (Math.random() * 2 - 1) * 18;
        g.ty = (Math.random() * 2 - 1) * 8;
        g.next = now + 600 + Math.random() * 900;
      } else {
        g.tx = 0;
        g.ty = 0;
        g.next = now + 500;
      }
    }
    g.x = approach(g.x, g.tx, dt, 7);
    g.y = approach(g.y, g.ty, dt, 7);
  }

  frame(now = performance.now()) {
    const dt = Math.min(0.1, (now - this.last) / 1000);
    this.last = now;
    const base = PRESETS[this.state];
    const hablando = this.state === "TALKING";
    const animo = hablando ? ANIMOS[this.gesto.animo] : ANIMOS.neutro;
    const target = { ...base };
    for (const k of NUMERIC) target[k] = base[k] + (animo[k] || 0);
    if (hablando) {
      target.lookX += this.gesto.lado * MIRADA_X;
      target.lookY -= this.gesto.vertical * MIRADA_Y;
    }
    const color = animo.color || base.color;
    for (const k of NUMERIC) this.p[k] = approach(this.p[k], target[k], dt, 9);
    for (let i = 0; i < 3; i++) this.p.color[i] = approach(this.p.color[i], color[i], dt, 6);
    this._updateBlink(now);
    this._updateGaze(now, dt);
    this.mouthOpen = approach(this.mouthOpen, this.state === "TALKING" ? this.volume : 0, dt, 22);
    this.resize();
    this._draw(now);
  }

  _draw(now) {
    const { ctx, canvas } = this;
    const W = canvas.width, H = canvas.height;
    const s = Math.min(W / 1150, H / 756); // 1 a 1080p; los ojos caben en ~1150 px de ancho (cara estrecha)
    const p = this.p;
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, W, H);

    const t = (now - this.t0) / 1000;
    let bobY = 0, shakeX = 0, breathe = 1;
    if (this.state === "THINKING") bobY = Math.sin(t * 2.2) * 8;
    if (this.state === "LISTENING") breathe = 1 + Math.sin(t * 3) * 0.015;
    if (this.state === "SLEEP") bobY = Math.sin(t * 1.1) * 6;
    if (this.state === "ERROR") shakeX = Math.sin(t * 40) * 3 * (Math.sin(t * 1.7) > 0.6 ? 1 : 0);

    const cx = W / 2 + (p.lookX + this.gaze.x + shakeX) * s;
    const cy = H * 0.46 + (p.lookY + this.gaze.y + bobY) * s;
    const ew = p.w * s * breathe;
    const eh = Math.max(4 * s, p.h * s * breathe * (1 - 0.92 * this.blink));
    const color = `rgb(${p.color.map(Math.round).join(",")})`;

    ctx.save();
    ctx.shadowColor = color;
    ctx.shadowBlur = 30 * s;
    for (const side of [-1, 1]) {
      const ex = cx + side * (p.gap * s + ew / 2);
      this._eye(ex, cy, ew, eh, p, side, color, s);
    }
    ctx.restore();

    this._mouth(W / 2 + this.gaze.x * 0.4 * s, H * 0.86 + bobY * 0.5 * s, s, color);

    if (this.state === "SLEEP") this._zzz(W / 2 + 420 * s, H * 0.30, t, s, color);
  }

  _eye(x, y, w, h, p, side, color, s) {
    const ctx = this.ctx;
    const r = Math.min(w, h) * p.r;
    const pad = 80 * s; // margen para que el brillo no se recorte por los lados
    ctx.save();
    // Párpados y ojos felices se hacen recortando la zona visible, así el
    // brillo sigue el contorno en vez de quedar cortado por un bloque negro.
    ctx.beginPath();
    const inner = x - side * w / 2; // borde hacia la nariz
    const outer = x + side * w / 2;
    const top = y - h / 2;
    const lidIn = p.lidIn > 0.005 ? top + h * p.lidIn : top - pad;
    const lidOut = p.lidOut > 0.005 ? top + h * p.lidOut : top - pad;
    ctx.moveTo(inner - side * pad, lidIn);
    ctx.lineTo(outer + side * pad, lidOut);
    ctx.lineTo(outer + side * pad, y + h / 2 + pad);
    ctx.lineTo(inner - side * pad, y + h / 2 + pad);
    ctx.closePath();
    if (p.happy > 0.01) {
      // Ojos felices: un óvalo tapa la parte de abajo (forma ^).
      ctx.ellipse(x, y + h / 2 + h * 0.15, w * 0.75, h * 0.62 * p.happy, 0, 0, Math.PI * 2);
      ctx.clip("evenodd");
    } else {
      ctx.clip();
    }
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.roundRect(x - w / 2, y - h / 2, w, h, r);
    ctx.fill();
    ctx.restore();
  }

  _mouth(x, y, s, color) {
    const ctx = this.ctx;
    const p = this.p;
    if (p.mouth < 0.02) return;
    ctx.save();
    ctx.globalAlpha = Math.min(1, p.mouth);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.shadowColor = color;
    ctx.shadowBlur = 20 * s;
    const talk = Math.max(0, 1 - Math.abs(p.smile));
    if (talk > 0.05) {
      // Boca que se abre con el volumen real.
      const open = Math.min(1, this.mouthOpen * 3.2);
      const w = (120 + 40 * open) * s;
      const h = (12 + 78 * open) * s;
      ctx.globalAlpha *= talk;
      ctx.beginPath();
      ctx.roundRect(x - w / 2, y - h / 2, w, h, Math.min(w, h) / 2);
      ctx.fill();
      ctx.globalAlpha = Math.min(1, p.mouth) * (1 - talk);
    }
    if (Math.abs(p.smile) > 0.05) {
      ctx.lineWidth = 16 * s;
      ctx.lineCap = "round";
      ctx.beginPath();
      const w = 170 * s, curve = 50 * s * p.smile;
      ctx.moveTo(x - w / 2, y - curve / 2);
      ctx.quadraticCurveTo(x, y + curve * 1.5, x + w / 2, y - curve / 2);
      ctx.stroke();
    }
    ctx.restore();
  }

  _zzz(x, y, t, s, color) {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = color;
    ctx.font = `bold ${Math.round(60 * s)}px system-ui, sans-serif`;
    for (let i = 0; i < 3; i++) {
      const k = (t * 0.35 + i / 3) % 1;
      ctx.globalAlpha = Math.sin(k * Math.PI);
      ctx.fillText("z", x + k * 80 * s + i * 10 * s, y - k * 160 * s);
    }
    ctx.restore();
  }
}
