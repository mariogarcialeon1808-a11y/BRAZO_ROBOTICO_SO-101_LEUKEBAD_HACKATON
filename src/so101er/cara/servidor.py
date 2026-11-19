"""Servidor local de la cara: estáticos, la imagen de la obra y eventos SSE. Solo librería estándar."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import queue
import sys
import threading
import time

WEB = Path(__file__).parent / 'web'
TIPOS = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
         '.css': 'text/css; charset=utf-8'}
PING_S = 15.


class Bus:
    """Reparte eventos a los navegadores conectados y recuerda lo que necesita uno nuevo."""

    def __init__(self):
        self.lock = threading.Lock()
        self.clientes = []
        self.estado = {'estado': 'IDLE'}
        self.turno = None          # evento `turno` en curso, para quien se conecte tarde
        self.reloj = None
        self.mirada = None
        self.cerrado = False

    def publicar(self, evento, datos):
        with self.lock:
            if evento == 'estado':
                self.estado = datos
            elif evento == 'turno':
                self.turno, self.reloj = datos, None
            elif evento == 'reloj':
                self.reloj = datos
            elif evento == 'fin':
                self.turno = self.reloj = None
            elif evento == 'mirada':
                self.mirada = datos
            for q in self.clientes:
                q.put((evento, datos))

    def suscribir(self):
        q = queue.Queue()
        with self.lock:
            q.put(('estado', self.estado))
            if self.turno is not None:
                q.put(('turno', self.turno))
                if self.reloj is not None:
                    q.put(('reloj', self.reloj))
            if self.mirada is not None:
                q.put(('mirada', self.mirada))
            self.clientes.append(q)
        return q

    def baja(self, q):
        with self.lock:
            if q in self.clientes:
                self.clientes.remove(q)


class _Servidor(ThreadingHTTPServer):
    daemon_threads = True
    # En Windows SO_REUSEADDR deja que dos procesos compartan el puerto sin error.
    allow_reuse_address = sys.platform != 'win32'

    def handle_error(self, request, client_address):
        pass                  # un navegador que se cierra o recarga no es un error del programa


def _manejador(bus, obra):
    class Manejador(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def _enviar(self, codigo, cuerpo, tipo):
            self.send_response(codigo)
            self.send_header('Content-Type', tipo)
            self.send_header('Content-Length', str(len(cuerpo)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            ruta = self.path.split('?', 1)[0]
            try:
                if ruta == '/eventos':
                    return self._eventos()
                if ruta == '/salud':
                    return self._enviar(200, json.dumps({'ok': True, 'clientes': len(bus.clientes)}).encode(),
                                        'application/json')
                if ruta == '/obra.jpg':
                    datos = obra()
                    if datos:
                        return self._enviar(200, datos, 'image/jpeg')
                    return self._enviar(404, b'sin imagen', 'text/plain')
                archivo = (WEB / ('index.html' if ruta == '/' else ruta.lstrip('/'))).resolve()
                if WEB.resolve() in archivo.parents and archivo.is_file() and archivo.suffix in TIPOS:
                    return self._enviar(200, archivo.read_bytes(), TIPOS[archivo.suffix])
                self._enviar(404, b'no encontrado', 'text/plain')
            except (ConnectionError, OSError):
                pass

        def _eventos(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            self.close_connection = True
            q = bus.suscribir()
            try:
                self.wfile.write(b'retry: 1000\n\n')
                self.wfile.flush()
                ultimo = time.monotonic()
                while not bus.cerrado:
                    try:
                        evento, datos = q.get(timeout=.5)
                    except queue.Empty:
                        if time.monotonic() - ultimo > PING_S:
                            self.wfile.write(b': ping\n\n')
                            self.wfile.flush()
                            ultimo = time.monotonic()
                        continue
                    texto = json.dumps(datos, ensure_ascii=False, separators=(',', ':'))
                    self.wfile.write(f'event: {evento}\ndata: {texto}\n\n'.encode())
                    self.wfile.flush()
                    ultimo = time.monotonic()
            except (ConnectionError, OSError):
                pass
            finally:
                bus.baja(q)

    return Manejador


class Servidor:
    """`127.0.0.1:puerto`. Si el puerto está ocupado, el constructor lanza OSError (lo recoge `crear`)."""

    def __init__(self, bus, obra, puerto=8765, host='127.0.0.1'):
        self.bus = bus
        self.httpd = _Servidor((host, puerto), _manejador(bus, obra))
        self.puerto = self.httpd.server_address[1]
        self.hilo = threading.Thread(target=self.httpd.serve_forever, kwargs={'poll_interval': .1},
                                     name='cara-http', daemon=True)
        self.hilo.start()

    def cerrar(self):
        self.bus.cerrado = True
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except OSError:
            pass
