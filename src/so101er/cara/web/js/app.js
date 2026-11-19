// Cara del robot: escucha /eventos (SSE) del programa y dibuja cara, subtítulos y
// la imagen con su zona resaltada. Todo sale de un único reloj: la posición de la
// voz que manda el programa (evento `reloj`), interpolada en cada fotograma.

import { Face } from "./eyes.js";
import { Linea, SubtitleView } from "./subtitulos.js";

const params = new URLSearchParams(location.search);
const DEBUG = params.has("debug") && params.get("debug") !== "0";
const DESFASE_URL = params.has("desfase") ? Number(params.get("desfase")) : null;
const HOLD_MS = 2000;      // subtítulos e imagen se quedan esto tras acabar
const USUARIO_MS = 6000;   // la pregunta del visitante se ve unos segundos
const IDLE_MS = 200;       // un IDLE entre dos estados seguidos no se llega a ver

const $ = (id) => document.getElementById(id);
const face = new Face($("face"));
const subs = new SubtitleView($("subs"), { holdMs: HOLD_MS });
const card = $("card"), img = $("obra"), svg = $("marca");

let conectado = false;
let estado = "IDLE", estadoTexto = "";
let idleTimer = null;
let turno = null;          // último evento `turno`
let linea = null;
let fin = null;            // {interrumpido, at}
const reloj = { base: null, at: 0 };

// --- Reloj de la voz -------------------------------------------------------
function desfaseMs() {
  if (DESFASE_URL !== null && Number.isFinite(DESFASE_URL)) return DESFASE_URL;
  return Number(turno?.desfase_ms) || 0;
}

function recibirReloj(pos, now = performance.now()) {
  if (reloj.base !== null) {
    const previsto = reloj.base + (now - reloj.at) / 1000;
    if (pos < previsto && previsto - pos < 0.05) return; // pequeño salto atrás: se ignora
  }
  reloj.base = pos;
  reloj.at = now;
}

function posicion(now) {
  if (reloj.base === null) return null;
  return reloj.base + (now - reloj.at) / 1000 - desfaseMs() / 1000;
}

// --- Estado de la cara --------------------------------------------------------
function ponerEstado(e, texto = "") {
  clearTimeout(idleTimer);
  estadoTexto = texto;
  if (e === "IDLE") {
    idleTimer = setTimeout(() => { estado = "IDLE"; face.setState("IDLE"); }, IDLE_MS);
    return;
  }
  estado = e;
  face.setState(e);
}

let userTimer = null;
function mostrarUsuario(texto) {
  const el = $("user");
  el.textContent = texto;
  el.classList.add("show");
  clearTimeout(userTimer);
  userTimer = setTimeout(() => el.classList.remove("show"), USUARIO_MS);
}

// --- Tarjeta de la imagen ---------------------------------------------------------
const obra = { v: null, listo: false, W: 0, H: 0, hueco: null, borde: null };
const marca = { x: 0, y: 0, w: 0, h: 0, rx: 0, velo: 0, punto: 0, vacia: true };
let tarjeta = { visible: false, ocultarDesde: null };

function cargarObra(v) {
  if (obra.v === v) return;
  obra.v = v;
  obra.listo = false;
  img.onload = () => {
    obra.W = img.naturalWidth;
    obra.H = img.naturalHeight;
    const m = Math.min(obra.W, obra.H);
    svg.setAttribute("viewBox", `0 0 ${obra.W} ${obra.H}`);
    svg.setAttribute("preserveAspectRatio", "none");
    svg.innerHTML = `
      <defs>
        <filter id="suave" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="${(m * 0.012).toFixed(1)}"/></filter>
        <mask id="hueco" maskUnits="userSpaceOnUse" x="0" y="0" width="${obra.W}" height="${obra.H}">
          <rect width="${obra.W}" height="${obra.H}" fill="white"/>
          <rect id="hueco-r" fill="black" filter="url(#suave)"/>
        </mask>
      </defs>
      <rect id="velo" width="${obra.W}" height="${obra.H}" fill="#000" mask="url(#hueco)"/>
      <rect id="borde" fill="none"/>`;
    obra.hueco = svg.querySelector("#hueco-r");
    obra.velo = svg.querySelector("#velo");
    obra.borde = svg.querySelector("#borde");
    marca.vacia = true;
    marca.velo = 0;
    obra.listo = true;
  };
  img.onerror = () => { obra.listo = false; };
  img.src = `/obra.jpg?v=${encodeURIComponent(v)}`;
}

function objetivo(b) {
  const { W, H } = obra;
  const m = Math.min(W, H);
  if (b.punto) {
    const r = 0.09 * m;
    const cx = (b.punto[1] / 1000) * W, cy = (b.punto[0] / 1000) * H;
    return { x: cx - r, y: cy - r, w: 2 * r, h: 2 * r, rx: r, punto: 1 };
  }
  const [[y0, x0], [y1, x1]] = b.region;
  const pad = 0.012 * m;
  const x = (Math.min(x0, x1) / 1000) * W - pad, y = (Math.min(y0, y1) / 1000) * H - pad;
  const w = (Math.abs(x1 - x0) / 1000) * W + 2 * pad, h = (Math.abs(y1 - y0) / 1000) * H + 2 * pad;
  return { x, y, w, h, rx: Math.min(0.03 * m, w / 2, h / 2), punto: 0 };
}

const approach = (a, b, dt, k) => a + (b - a) * (1 - Math.exp(-dt * k));

function ocultarTarjeta(rapido) {
  card.classList.toggle("rapido", !!rapido);
  document.body.classList.remove("con-obra");
  tarjeta = { visible: false, ocultarDesde: null };
}

function dibujarTarjeta(posS, dt, t) {
  const bloques = turno?.bloques || [];
  if (!linea || !bloques.length || !obra.listo) {
    if (tarjeta.visible) ocultarTarjeta(fin?.interrumpido);
    return;
  }
  const palabras = turno.palabras;
  const inicio = palabras[bloques[0].p0]?.ini ?? bloques[0].ancla_s;
  if (!tarjeta.visible && posS !== null && posS >= inicio && !fin?.interrumpido && !linea.isDone(posS * 1000)) {
    card.classList.remove("rapido");
    document.body.classList.add("con-obra");
    tarjeta.visible = true;
  }
  if (!tarjeta.visible) return;
  if (fin?.interrumpido) return ocultarTarjeta(true);
  if (linea.isDone(posS * 1000)) {
    tarjeta.ocultarDesde ??= performance.now();
    if (performance.now() - tarjeta.ocultarDesde > HOLD_MS) return ocultarTarjeta(false);
  }
  // El resaltado cambia al sonar la palabra ancla de cada frase con ubicación.
  let activo = null;
  for (const b of bloques) if (posS >= b.ancla_s) activo = b;
  if (activo) {
    const o = objetivo(activo);
    if (marca.vacia) { Object.assign(marca, o); marca.vacia = false; }
    for (const k of ["x", "y", "w", "h", "rx", "punto"]) marca[k] = approach(marca[k], o[k], dt, 9);
  }
  marca.velo = approach(marca.velo, activo ? 1 : 0, dt, 8);
  const m = Math.min(obra.W, obra.H);
  const pulso = marca.punto * Math.sin(t * 4) * 0.05;
  for (const [el, grow] of [[obra.hueco, 0], [obra.borde, pulso]]) {
    const gx = marca.w * grow / 2, gy = marca.h * grow / 2;
    el.setAttribute("x", (marca.x - gx).toFixed(1));
    el.setAttribute("y", (marca.y - gy).toFixed(1));
    el.setAttribute("width", Math.max(0, marca.w + 2 * gx).toFixed(1));
    el.setAttribute("height", Math.max(0, marca.h + 2 * gy).toFixed(1));
    el.setAttribute("rx", Math.max(0, marca.rx * (1 + grow)).toFixed(1));
  }
  obra.velo.setAttribute("opacity", (0.55 * marca.velo).toFixed(3));
  // Anillo amarillo en un punto, marco blanco suave en una región.
  const amarillo = marca.punto;
  obra.borde.setAttribute("stroke", `rgba(${Math.round(255)},${Math.round(255 - 45 * amarillo)},${Math.round(255 - 192 * amarillo)},${(0.6 + 0.4 * amarillo).toFixed(2)})`);
  obra.borde.setAttribute("stroke-width", (m * (0.005 + 0.004 * amarillo)).toFixed(1));
  obra.borde.setAttribute("opacity", marca.velo.toFixed(3));
}

// --- Eventos del programa ----------------------------------------------------------
function clave(t) { return `${t.obra_v}:${t.id}`; }

const manejadores = {
  estado(d) { ponerEstado(d.estado, d.texto || ""); },
  usuario(d) { if (d.texto) mostrarUsuario(d.texto); },
  mirada(d) { face.setGesto(d); },
  turno(d) {
    if (turno && clave(turno) === clave(d) && !fin) {
      // La misma frase otra vez: un reenvío al reconectar o, si trae revisión nueva, sus tiempos definitivos.
      if ((d.rev || 0) > (turno.rev || 0)) {
        turno = d;
        linea = new Linea(d.palabras || []);
      }
      return;
    }
    turno = d;
    linea = new Linea(d.palabras || []);
    fin = null;
    reloj.base = null;
    subs.clear();
    if ((d.bloques || []).length) cargarObra(d.obra_v);
    else if (tarjeta.visible) ocultarTarjeta(true);
  },
  reloj(d) { if (turno && d.id === turno.id && !fin) recibirReloj(d.pos); },
  fin(d) {
    if (!turno || d.id !== turno.id || fin) return;
    const pos = posicion(performance.now());
    fin = { interrumpido: !!d.interrumpido, at: performance.now() };
    if (d.interrumpido) linea.cut(pos === null ? -1 : pos * 1000);
    else linea.ended = true;
  },
};

let es = null;
function conectar() {
  es = new EventSource("/eventos");
  es.onopen = () => { conectado = true; };
  es.onerror = () => {
    conectado = false;
    if (es.readyState === EventSource.CLOSED) { es.close(); setTimeout(conectar, 1000); }
  };
  for (const [nombre, fn] of Object.entries(manejadores)) {
    es.addEventListener(nombre, (e) => {
      try { fn(JSON.parse(e.data)); } catch (err) { console.warn(nombre, err); }
    });
  }
}

// --- Bucle de dibujo: todo con la misma posición, sin temporizadores ------------------
let ultimo = performance.now();
function fotograma(now) {
  const dt = Math.min(0.1, (now - ultimo) / 1000);
  ultimo = now;
  const pos = linea ? posicion(now) : null;
  const posMs = pos === null ? -Infinity : pos * 1000;
  const info = subs.render(linea, posMs);
  if (linea && linea.isDone(posMs) && subs.isFaded()) { linea = null; }
  let vol = 0;
  if (turno && !fin && pos !== null && pos >= 0) vol = turno.boca?.[Math.floor(pos / (turno.paso || 0.02))] ?? 0;
  face.setVolume(vol * 0.3);
  try { dibujarTarjeta(pos, dt, now / 1000); } catch (err) { console.warn("tarjeta", err); }
  face.frame(now);
  if (DEBUG) {
    $("debug").innerHTML =
      `<div>${conectado ? "conectado" : '<span class="off">sin conexión</span>'} · ${estado}${estadoTexto ? " · " + estadoTexto : ""}</div>` +
      `<div>turno ${turno ? turno.id : "—"} · pos <b>${pos === null ? "—" : pos.toFixed(2) + " s"}</b></div>` +
      `<div>palabra <b>${info.word ?? "—"}</b> (${info.index})</div>` +
      `<div>desfase ${desfaseMs()} ms · boca ${vol.toFixed(2)}</div>`;
  }
  requestAnimationFrame(fotograma);
}

if (DEBUG) { document.body.classList.add("debug"); $("debug").hidden = false; }
conectar();
requestAnimationFrame(fotograma);
