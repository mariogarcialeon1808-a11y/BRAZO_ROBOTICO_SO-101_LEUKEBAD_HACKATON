"""Ventana emergente de imágenes: recorrer la carpeta, añadir fotos, encuadrar y vídeo en directo.

No bloquea la ventana principal (PARAR y Soltar siguen a mano) y no decide nada sobre los
brazos: solo propone una imagen ya adaptada al cuadro a quien la abrió.
"""
from __future__ import annotations

from pathlib import Path

import cv2

from ..galeria import (EJEMPLO, ErrorImagen, FuenteVideo, Galeria, adaptar, ventana_recorte)

ANCHO_VISTA = 760
CAMARAS = 4
VIDEOS = "*.mp4 *.avi *.mov *.mkv *.webm *.wmv *.m4v *.mpg"
FOTOS = "*.png *.jpg *.jpeg *.bmp *.webp *.tif *.tiff *.gif"
TEXTO_MODO = {"igual": "encaja tal cual",
              "recortar": "recortada para llenar el cuadro (arrástrala para moverla)",
              "ajustar": "entera, con bandas a los lados"}


def foto_tk(tk, bgr):
    """Imagen BGR → PhotoImage. PPM sin comprimir: Tk lo carga tres veces más rápido que un PNG."""
    alto, ancho = bgr.shape[:2]
    return tk.PhotoImage(data=b"P6\n%d %d\n255\n" % (ancho, alto) + cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).tobytes())


class VentanaImagenes:
    """`en_uso()` → nombre en la galería, None (cuadro de ejemplo) o False (imagen de fuera).
    `al_usar(nombre, imagen)` aplica la imagen adaptada; si lanza, se muestra el motivo.
    `al_directo(fuente, rotulo)` recibe el vídeo para usarlo en directo como imagen del cuadro (a
    partir de ahí la fuente es suya); `tomar_directo()` devuelve la que tenga en uso, o None."""

    def __init__(self, padre, galeria: Galeria, objetivo: float, en_uso, al_usar, al_cerrar=None,
                 al_directo=None, tomar_directo=None) -> None:
        import tkinter as tk
        from tkinter import ttk
        self.tk, self.ttk = tk, ttk
        self.galeria, self.objetivo, self.en_uso, self.al_usar, self.al_cerrar = galeria, objetivo, en_uso, al_usar, al_cerrar
        self.al_directo, self.tomar_directo = al_directo, tomar_directo
        self.pw, self.ph = ANCHO_VISTA, round(ANCHO_VISTA * objetivo)
        self.entradas: list[str | None] = [None]
        self.i = 0
        self.adaptada = None            # imagen que se aplicaría con «Usar esta imagen»
        self.modo = "igual"
        self.fuente: FuenteVideo | None = None
        self._visto = -1
        self._arrastre = None
        self._foto = None
        self.cerrada = False

        self.top = top = tk.Toplevel(padre)
        top.title("Imágenes de la obra")
        top.resizable(False, False)
        try:
            top.transient(padre.winfo_toplevel())
        except tk.TclError:
            pass
        ttk.Style(top).configure("Usar.TButton", font=("Segoe UI", 10, "bold"))
        # Sin foco de teclado en los botones: Espacio e Intro son siempre de la ventana, no del último botón pulsado.
        class Boton(ttk.Button):
            def __init__(self, *a, **k):
                super().__init__(*a, takefocus=False, **k)
        self.lienzo = tk.Canvas(top, width=self.pw, height=self.ph, bg="#202020", highlightthickness=0)
        self.lienzo.pack(padx=12, pady=(12, 6))
        self._item = self.lienzo.create_image(0, 0, anchor="nw")
        self._rotulo = self.lienzo.create_text(self.pw // 2, self.ph // 2, fill="white", font=("Segoe UI", 13),
                                               width=self.pw - 80, justify="center")
        self.info = tk.StringVar()
        ttk.Label(top, textvariable=self.info, font=("Segoe UI", 10, "bold"), wraplength=self.pw).pack(padx=12, anchor="w")
        self.aviso = tk.StringVar()
        ttk.Label(top, textvariable=self.aviso, wraplength=self.pw, foreground="#555").pack(padx=12, anchor="w")

        # -- galería
        self.barra_galeria = g = ttk.Frame(top)
        Boton(g, text="◀  Anterior", command=lambda: self.mover(-1)).pack(side="left")
        Boton(g, text="Siguiente  ▶", command=lambda: self.mover(1)).pack(side="left", padx=(4, 14))
        Boton(g, text="Explorar…", command=self.explorar).pack(side="left")
        Boton(g, text="Vídeo en directo", command=self.entrar_video).pack(side="left", padx=4)
        self.boton_encuadre = Boton(g, text="Ver entera", command=self.cambiar_encuadre)
        self.boton_encuadre.pack(side="left", padx=(14, 4))
        self.boton_quitar = Boton(g, text="Quitar", command=self.quitar)
        self.boton_quitar.pack(side="left")
        Boton(g, text="Cerrar", command=self.cerrar).pack(side="right")
        self.boton_usar = Boton(g, text="Usar esta imagen", style="Usar.TButton", command=self.usar)
        self.boton_usar.pack(side="right", padx=6)

        # -- vídeo
        self.barra_video = v = ttk.Frame(top)
        ttk.Label(v, text="Fuente:").pack(side="left")
        self.origen = tk.StringVar()
        self.selector = ttk.Combobox(v, textvariable=self.origen, state="readonly", width=22,
                                     values=[f"Cámara {n + 1}" for n in range(CAMARAS)] + ["Archivo de vídeo…"])
        self.selector.pack(side="left", padx=4)
        self.selector.bind("<<ComboboxSelected>>", lambda e: self.elegir_fuente())
        self.boton_pausa = Boton(v, text="Congelar", command=self.pausa)
        self.boton_pausa.pack(side="left", padx=4)
        Boton(v, text="Volver a las imágenes", command=self.salir_video).pack(side="right")
        Boton(v, text="Tomar instantánea y usarla", style="Usar.TButton",
                   command=self.instantanea).pack(side="right", padx=6)
        if al_directo is not None:
            Boton(v, text="Usar en directo", style="Usar.TButton", command=self.directo).pack(side="right")

        self.lienzo.bind("<ButtonPress-1>", self._pulsar)
        self.lienzo.bind("<B1-Motion>", self._arrastrar)
        self.lienzo.bind("<ButtonRelease-1>", self._soltar)
        for tecla, accion in (("<Left>", lambda: self.mover(-1)), ("<Right>", lambda: self.mover(1)),
                              ("<Return>", self._intro), ("<space>", self._espacio), ("<Escape>", self.cerrar)):
            top.bind(tecla, lambda e, a=accion: (a(), "break")[1])
        top.protocol("WM_DELETE_WINDOW", self.cerrar)
        top.bind("<Destroy>", lambda e: e.widget is top and self._limpiar())

        self.recargar(self.en_uso())
        self._modo_galeria()
        top.update_idletasks()
        try:                                                     # centrada sobre la ventana principal
            raiz = padre.winfo_toplevel()
            x = raiz.winfo_rootx() + (raiz.winfo_width() - top.winfo_reqwidth()) // 2
            y = raiz.winfo_rooty() + (raiz.winfo_height() - top.winfo_reqheight()) // 3
            top.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        except tk.TclError:
            pass
        top.focus_set()

    # ------------------------------------------------------------ galería
    @property
    def en_video(self) -> bool:
        return self.fuente is not None

    @property
    def nombre(self) -> str | None:
        return self.entradas[self.i]

    def recargar(self, seleccionar=False) -> None:
        """Vuelve a leer la carpeta y se coloca en `seleccionar` (o se queda donde estaba)."""
        actual = self.nombre if seleccionar is False else seleccionar
        self.entradas = [None] + self.galeria.nombres()
        self.i = self.entradas.index(actual) if actual in self.entradas else 0
        self.mostrar()

    def mover(self, paso: int) -> None:
        if self.en_video:
            return
        self.i = (self.i + paso) % len(self.entradas)
        self.aviso.set("")
        self.mostrar()

    def _pintar(self, bgr, texto: str = "") -> None:
        if bgr is not None:
            if bgr.shape[1] != self.pw or bgr.shape[0] != self.ph:
                bgr = cv2.resize(bgr, (self.pw, self.ph), interpolation=cv2.INTER_AREA)
            self._foto = foto_tk(self.tk, bgr)
            self.lienzo.itemconfigure(self._item, image=self._foto)
        else:
            self._foto = None
            self.lienzo.itemconfigure(self._item, image="")
        self.lienzo.itemconfigure(self._rotulo, text=texto)

    def mostrar(self) -> None:
        nombre = self.nombre
        cabecera = f"{self.i + 1} de {len(self.entradas)}  ·  {nombre or EJEMPLO}"
        try:
            original = self.galeria.original(nombre)
            self.adaptada, self.modo = self.galeria.imagen(nombre, self.objetivo)
        except (ErrorImagen, OSError) as e:
            self.adaptada, self.modo = None, "igual"
            self._pintar(None, f"No se puede mostrar esta imagen.\n{e}")
            self.info.set(cabecera)
        else:
            self._pintar(self.adaptada)
            en_uso = "  ·  EN USO" if self.en_uso() == nombre and self.en_uso() is not False else ""
            self.info.set(f"{cabecera}  ·  {original.shape[1]}×{original.shape[0]} px  ·  {TEXTO_MODO[self.modo]}{en_uso}")
        self.boton_usar.state(["!disabled"] if self.adaptada is not None else ["disabled"])
        self.boton_quitar.state(["!disabled"] if nombre is not None else ["disabled"])
        self.boton_encuadre.state(["disabled"] if self.modo == "igual" or self.adaptada is None else ["!disabled"])
        self.boton_encuadre.config(text="Recortar para llenar" if self.modo == "ajustar" else "Ver entera")
        self.lienzo.config(cursor="fleur" if self.modo == "recortar" and self.adaptada is not None else "")

    def cambiar_encuadre(self) -> None:
        if self.en_video or self.adaptada is None or self.modo == "igual":
            return
        _, centro = self.galeria.ajuste(self.nombre)
        self._guardar_encuadre("ajustar" if self.modo == "recortar" else "recortar", centro)

    def _guardar_encuadre(self, modo: str, centro) -> None:
        try:
            self.galeria.fijar_ajuste(self.nombre, modo, centro)
        except OSError as e:
            self.aviso.set(f"No se pudo guardar el encuadre: {e}")
        self.mostrar()
        if self.en_uso() == self.nombre and self.en_uso() is not False:
            self.aviso.set("Encuadre cambiado. Pulsa «Usar esta imagen» para aplicarlo.")

    # -- mover el recorte arrastrando
    def _pulsar(self, e) -> None:
        self._arrastre = None
        if self.en_video or self.modo != "recortar" or self.adaptada is None:
            return
        try:
            original = self.galeria.original(self.nombre)
        except (ErrorImagen, OSError):
            return
        h, w = original.shape[:2]
        _, centro = self.galeria.ajuste(self.nombre)
        self._arrastre = (e.x, e.y, original, ventana_recorte(h, w, self.objetivo, centro), centro)

    def _centro_arrastrado(self, e):
        ex, ey, original, (x0, y0, an, al), _ = self._arrastre
        h, w = original.shape[:2]
        x = min(max(x0 - (e.x - ex) * an / self.pw, 0), w - an)
        y = min(max(y0 - (e.y - ey) * al / self.ph, 0), h - al)
        return (x + an / 2) / w, (y + al / 2) / h

    def _arrastrar(self, e) -> None:
        if self._arrastre is None:
            return
        centro = self._centro_arrastrado(e)
        self._pintar(adaptar(self._arrastre[2], self.objetivo, "recortar", centro, ancho=self.pw)[0])

    def _soltar(self, e) -> None:
        if self._arrastre is None:
            return
        centro, previo = self._centro_arrastrado(e), self._arrastre[4]
        self._arrastre = None
        if abs(centro[0] - previo[0]) + abs(centro[1] - previo[1]) > 1e-4:
            self._guardar_encuadre("recortar", centro)

    # -- añadir y quitar
    def explorar(self) -> None:
        from tkinter import filedialog
        recuerdo = self.galeria.recuerdo("carpeta_fotos")
        rutas = filedialog.askopenfilenames(parent=self.top, title="Añadir imágenes a la galería",
                                            initialdir=recuerdo if recuerdo and Path(recuerdo).is_dir() else None,
                                            filetypes=[("Imágenes", FOTOS), ("Todos los archivos", "*.*")])
        if not rutas or self.cerrada:
            return
        try:
            self.galeria.recordar("carpeta_fotos", str(Path(rutas[0]).parent))
            dentro, avisos = self.galeria.anadir(rutas)
        except OSError as e:
            self.aviso.set(f"No se pudo copiar a la carpeta de la obra: {e}")
            return
        self.recargar(dentro[0] if dentro else False)
        partes = ([f"{len(dentro)} imagen(es) en la galería. Pulsa «Usar esta imagen» para cargarla."] if dentro else [])
        self.aviso.set(" ".join(partes + ["No añadidas: " + "; ".join(avisos) + "."] if avisos else partes))

    def quitar(self) -> None:
        from tkinter import messagebox
        nombre = self.nombre
        if self.en_video or nombre is None:
            return
        if not messagebox.askyesno("Quitar de la galería", f"¿Quitar «{nombre}» de la galería?\n\nNo se borra: se "
                                   "mueve a la subcarpeta _quitadas de la carpeta de la obra.", parent=self.top):
            return
        estaba_en_uso = self.en_uso() == nombre
        try:
            self.galeria.quitar(nombre)
        except (ErrorImagen, OSError) as e:
            self.aviso.set(f"No se pudo quitar: {e}")
            return
        self.i = max(0, self.i - 1)
        self.recargar()
        self.aviso.set(f"«{nombre}» está en _quitadas." + (" Sigue cargada en esta sesión hasta que uses otra."
                                                          if estaba_en_uso else ""))

    def usar(self) -> None:
        if self.en_video or self.adaptada is None:
            return
        nombre = self.nombre
        try:
            self.al_usar(nombre, self.adaptada)
        except Exception as e:
            self.aviso.set(f"No se pudo cargar: {e}")
            return
        if self.cerrada:
            return
        self.mostrar()
        self.aviso.set(f"Cargada: {nombre or EJEMPLO}. La IA la verá en la próxima pregunta.")

    # ------------------------------------------------------------ vídeo
    def _modo_galeria(self) -> None:
        self.barra_video.pack_forget()
        self.barra_galeria.pack(fill="x", padx=12, pady=(6, 12))

    def entrar_video(self) -> None:
        if self.en_video:
            return
        self.barra_galeria.pack_forget()
        self.barra_video.pack(fill="x", padx=12, pady=(6, 12))
        self.lienzo.config(cursor="")
        en_uso = self.tomar_directo() if self.tomar_directo is not None else None
        if en_uso is not None and not en_uso.error:              # el directo de la sesión vuelve aquí: la cámara no se reabre
            self.fuente = en_uso
            self._visto = -1
            en_uso.pausar(False)
            self.boton_pausa.config(text="Congelar")
            self.origen.set(self._rotulo_de(en_uso.origen))
            self.info.set("Vídeo en directo  ·  " + self._rotulo_de(en_uso.origen))
            self.aviso.set("El directo se ha detenido en su última imagen. Pulsa «Usar en directo» para seguir con él.")
        else:
            if en_uso is not None:
                en_uso.cerrar(esperar=False)
            recuerdo = self.galeria.recuerdo("camara")
            camara = recuerdo if isinstance(recuerdo, int) and 0 <= recuerdo < CAMARAS else 0
            self.origen.set(f"Cámara {camara + 1}")
            self._abrir_fuente(camara)
        self._tic()

    @staticmethod
    def _rotulo_de(origen) -> str:
        return f"Cámara {origen + 1}" if isinstance(origen, int) else Path(str(origen)).name

    def _abrir_fuente(self, origen) -> None:
        previa = self.fuente
        if previa is not None:
            previa.cerrar(esperar=False)
        self.fuente = FuenteVideo(origen, tras=previa)
        self._visto = -1
        self.boton_pausa.config(text="Congelar")
        self.info.set("Vídeo en directo  ·  " + self._rotulo_de(origen))
        self.aviso.set("Lo que ves es lo que se usará. Espacio toma una instantánea"
                       + ("; «Usar en directo» deja la cámara como imagen del cuadro." if self.al_directo else "."))
        self._pintar(None, "Abriendo la cámara…" if isinstance(origen, int) else "Abriendo el vídeo…")

    def elegir_fuente(self) -> None:
        if not self.en_video:
            return
        texto = self.origen.get()
        if texto.startswith("Cámara"):
            camara = int(texto.split()[1]) - 1
            self.galeria.recordar("camara", camara)
            self._abrir_fuente(camara)
            return
        from tkinter import filedialog
        recuerdo = self.galeria.recuerdo("carpeta_videos")
        ruta = filedialog.askopenfilename(parent=self.top, title="Abrir un vídeo",
                                          initialdir=recuerdo if recuerdo and Path(recuerdo).is_dir() else None,
                                          filetypes=[("Vídeos", VIDEOS), ("Todos los archivos", "*.*")])
        if self.cerrada or not self.en_video:
            return
        if not ruta:                                             # cancelado: se queda con lo que había
            self.origen.set(self._rotulo_de(self.fuente.origen))
            return
        self.galeria.recordar("carpeta_videos", str(Path(ruta).parent))
        self.origen.set(Path(ruta).name)
        self._abrir_fuente(ruta)

    def _tic(self) -> None:
        if self.cerrada or not self.en_video:
            return
        fuente = self.fuente
        if fuente.error:
            self._pintar(None, fuente.error + "\nElige otra fuente o vuelve a las imágenes.")
        else:
            numero, fotograma = fuente.fotograma()
            if fotograma is not None and numero != self._visto:
                self._visto = numero
                self._pintar(adaptar(fotograma, self.objetivo, "auto", ancho=self.pw)[0])
        self.top.after(66, self._tic)

    def pausa(self) -> None:
        if not self.en_video:
            return
        self.fuente.pausar(not self.fuente.en_pausa)
        self.boton_pausa.config(text="Seguir" if self.fuente.en_pausa else "Congelar")

    def instantanea(self) -> None:
        if not self.en_video:
            return
        _, fotograma = self.fuente.fotograma()
        if fotograma is None:
            self.aviso.set(self.fuente.error or "Todavía no hay imagen del vídeo.")
            return
        try:
            nombre = self.galeria.instantanea(fotograma.copy())
        except (ErrorImagen, OSError) as e:
            self.aviso.set(f"No se pudo guardar la instantánea: {e}")
            return
        self.salir_video(seleccionar=nombre)
        self.usar()

    def directo(self) -> None:
        """Entrega el vídeo a la sesión: el cuadro pasa a ser la cámara (o el archivo) en directo."""
        if not self.en_video or self.al_directo is None:
            return
        fuente = self.fuente
        if fuente.error or fuente.fotograma()[1] is None:
            self.aviso.set(fuente.error or "Todavía no hay imagen del vídeo.")
            return
        fuente.pausar(False)
        rotulo = self._rotulo_de(fuente.origen)
        try:
            self.al_directo(fuente, rotulo)
        except Exception as e:
            self.aviso.set(f"No se pudo usar en directo: {e}")
            return
        self.fuente = None                                       # ya es de la sesión: aquí no se cierra
        if self.cerrada:
            return
        self._modo_galeria()
        self.recargar()
        self.aviso.set(f"{rotulo} en directo. Cada pregunta usa la imagen de ese momento.")

    def salir_video(self, seleccionar=False) -> None:
        if self.fuente is not None:
            self.fuente.cerrar(esperar=False)
            self.fuente = None
        self._modo_galeria()
        self.aviso.set("")
        self.recargar(seleccionar)

    # ------------------------------------------------------------ teclas y cierre
    def _intro(self) -> None:
        self.instantanea() if self.en_video else self.usar()

    def _espacio(self) -> None:
        if self.en_video:
            self.instantanea()

    def _limpiar(self) -> None:
        if self.cerrada:
            return
        self.cerrada = True
        if self.fuente is not None:
            self.fuente.cerrar(esperar=False)
            self.fuente = None
        if self.al_cerrar:
            self.al_cerrar()

    def cerrar(self) -> None:
        self._limpiar()
        try:
            self.top.destroy()
        except self.tk.TclError:
            pass

    def traer_al_frente(self) -> None:
        self.top.deiconify()
        self.top.lift()
        self.top.focus_set()
