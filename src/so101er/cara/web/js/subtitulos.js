// Subtítulos sincronizados con el reloj de la voz. `layoutLines`, `pageFor` y
// `SubtitleView` vienen del display anterior (robot-face/face/js/subtitles.js);
// aquí las palabras ya llegan con sus tiempos desde el programa (evento `turno`).

// Palabras de un turno con tiempos en ms del reloj de la voz.
export class Linea {
  constructor(palabras) {
    this.todas = palabras.map((p) => ({ text: String(p.t).normalize("NFC"), start: p.ini * 1000, end: p.fin * 1000 }));
    this.cutAt = null;
    this.ended = false;
    this.endMs = this.todas.length ? this.todas[this.todas.length - 1].end : 0;
  }

  get empty() {
    return this.todas.length === 0;
  }

  get interrupted() {
    return this.cutAt !== null;
  }

  words() {
    return this.cutAt === null ? this.todas : this.todas.filter((w) => w.start <= this.cutAt);
  }

  // Última palabra que ya ha empezado a sonar (-1 si ninguna). Nunca va por delante de la voz.
  currentIndex(nowMs) {
    const words = this.words();
    let idx = -1;
    for (let i = 0; i < words.length; i++) {
      if (words[i].start <= nowMs) idx = i;
      else break;
    }
    return idx;
  }

  isDone(nowMs) {
    return this.cutAt !== null || this.ended || nowMs >= this.endMs;
  }

  // Interrupción: se queda lo ya dicho.
  cut(nowMs) {
    if (this.cutAt === null) this.cutAt = nowMs;
  }
}

// Reparte las palabras en líneas que caben en `maxWidth`, sin cortarlas.
// `measure(text)` devuelve el ancho en px. Devuelve listas de índices.
export function layoutLines(words, measure, maxWidth) {
  const lines = [];
  let line = [];
  let width = 0;
  const space = measure(" ");
  words.forEach((w, i) => {
    const ww = measure(w.text);
    const needed = line.length ? width + space + ww : ww;
    if (line.length && needed > maxWidth) {
      lines.push(line);
      line = [i];
      width = ww;
    } else {
      line.push(i);
      width = needed;
    }
  });
  if (line.length) lines.push(line);
  return lines;
}

// Página de 2 líneas que contiene la palabra `idx` (la primera si idx < 0).
export function pageFor(lines, idx, linesPerPage = 2) {
  let lineNo = 0;
  if (idx >= 0) {
    lineNo = lines.findIndex((l) => l.includes(idx));
    if (lineNo < 0) lineNo = lines.length - 1;
  }
  const page = Math.floor(Math.max(0, lineNo) / linesPerPage);
  return lines.slice(page * linesPerPage, page * linesPerPage + linesPerPage);
}

export class SubtitleView {
  constructor(el, { holdMs = 2000, fadeMs = 600 } = {}) {
    this.el = el;
    this.holdMs = holdMs;
    this.fadeMs = fadeMs;
    this.renderedKey = "";
    this.doneSince = null;
    this.canvas = document.createElement("canvas");
    this.ctx = this.canvas.getContext("2d");
  }

  measureFn() {
    const style = getComputedStyle(this.el);
    this.ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
    return (t) => this.ctx.measureText(t).width;
  }

  maxWidth() {
    const style = getComputedStyle(this.el);
    return this.el.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  }

  clear() {
    this.el.replaceChildren();
    this.el.classList.remove("fading");
    this.renderedKey = "";
    this.doneSince = null;
  }

  // `nowMs` en el reloj de la voz. Devuelve la palabra actual para depurar.
  render(linea, nowMs) {
    if (!linea || linea.empty) {
      if (this.renderedKey) this.clear();
      return { word: null, index: -1 };
    }
    const words = linea.words();
    const idx = linea.currentIndex(nowMs);
    if (idx < 0 && !linea.interrupted) {
      if (this.renderedKey) this.clear(); // aún no suena nada: no adelantamos texto
      return { word: null, index: -1 };
    }
    const lines = layoutLines(words, this.measureFn(), this.maxWidth());
    const page = pageFor(lines, idx);
    const key = page.map((l) => l.join(",")).join("|") + ":" + words.length;
    if (key !== this.renderedKey) {
      this.el.classList.remove("fading");
      const frag = document.createDocumentFragment();
      for (const line of page) {
        const div = document.createElement("div");
        div.className = "line";
        for (const i of line) {
          const span = document.createElement("span");
          span.className = "w";
          span.dataset.i = i;
          span.textContent = words[i].text;
          div.appendChild(span);
          div.appendChild(document.createTextNode(" "));
        }
        frag.appendChild(div);
      }
      this.el.replaceChildren(frag);
      this.renderedKey = key;
    }
    const done = linea.isDone(nowMs);
    for (const span of this.el.querySelectorAll("span.w")) {
      const i = Number(span.dataset.i);
      const cls = i < idx || (done && i <= idx) ? "said" : i === idx ? "now" : "next";
      if (span.className !== "w " + cls) span.className = "w " + cls;
    }
    const wall = performance.now();
    if (done) {
      if (this.doneSince === null) this.doneSince = wall;
      if (wall - this.doneSince > this.holdMs) this.el.classList.add("fading");
    } else {
      this.doneSince = null;
    }
    return { word: idx >= 0 ? words[idx].text : null, index: idx };
  }

  isFaded() {
    return this.doneSince !== null && performance.now() - this.doneSince > this.holdMs + this.fadeMs;
  }
}
