"""Reproducción PCM con reloj derivado del instante DAC de PortAudio."""
import time
import threading
import numpy as np


class Reproductor:
    def __init__(self,audio,previo_s=0.,frecuencia=24000,abierto=False):
        """Con `abierto`, se le puede ir añadiendo audio (`anadir`) mientras suena: si se acaba lo que
        tiene, emite silencio y sigue contando tiempo hasta que llega más o se llama a `cerrar_entrada`."""
        self.frecuencia=frecuencia;self.abierto=abierto;self.pista_lock=threading.Lock()
        self.previo=round(max(0,previo_s)*frecuencia)
        self.track=np.r_[np.zeros(self.previo,np.int16),np.asarray(audio,dtype=np.int16)]
        self.cursor=0;self.referencia=None;self.stream=None
        self.listo=threading.Event();self.terminado=threading.Event()
        self.stream_lock=threading.Lock()
        self.cerrado=False;self.subalimentaciones=0

    def registrar_buffer(self,muestra,dac,actual,ahora):
        """Única transformación entre reloj del dispositivo y perf_counter.

        muestra es el inicio del buffer, incluido el preroll. No se toma el tiempo
        de la llamada play() como si fuera la salida acústica.
        """
        self.referencia=((muestra-self.previo)/self.frecuencia,ahora+dac-actual)
        self.listo.set()

    def posicion(self,ahora=None):
        reference=self.referencia
        if reference is None:raise RuntimeError('el dispositivo aún no ha dado reloj DAC')
        sample_time,dac_time=reference
        return sample_time+(time.perf_counter() if ahora is None else ahora)-dac_time

    def iniciar(self):
        import sounddevice as sd
        if self.cerrado:raise RuntimeError('reproducción cancelada')
        def callback(outdata,frames,t,status):
            outdata.fill(0)
            if self.cerrado:raise sd.CallbackAbort
            self.registrar_buffer(self.cursor,float(t.outputBufferDacTime),float(t.currentTime),time.perf_counter())
            if status.output_underflow:self.subalimentaciones+=1
            with self.pista_lock:
                count=min(frames,len(self.track)-self.cursor)
                if count>0:outdata[:count,0]=self.track[self.cursor:self.cursor+count]
                count=max(count,0)
                if count<frames and self.abierto:
                    # Aún puede llegar más audio: el silencio que suena mientras tanto forma parte de la pista,
                    # para que `posicion` y lo que se añada después sigan en la misma línea de tiempo.
                    self.track=np.r_[self.track,np.zeros(frames-count,np.int16)];count=frames
                self.cursor+=count
                fin=self.cursor>=len(self.track) and not self.abierto
            if fin:raise sd.CallbackStop
        with self.stream_lock:
            if self.cerrado:raise RuntimeError('reproducción cancelada')
            self.stream=sd.OutputStream(samplerate=self.frecuencia,channels=1,dtype='int16',
                                       blocksize=480,latency='low',callback=callback,
                                       finished_callback=self.terminado.set)
            self.stream.start()
        if not self.listo.wait(3):self.cerrar();raise RuntimeError('sin reloj de salida del altavoz')

    def anadir(self,audio,pausa_s=0.):
        """Añade audio al final, tras `pausa_s` de silencio. Devuelve el instante (reloj de `posicion`) en que empieza."""
        audio=np.asarray(audio,dtype=np.int16)
        with self.pista_lock:
            inicio=len(self.track)+round(max(0.,pausa_s)*self.frecuencia)
            self.track=np.r_[self.track,np.zeros(inicio-len(self.track),np.int16),audio]
        return (inicio-self.previo)/self.frecuencia

    def cerrar_entrada(self):
        """No llegará más audio: la reproducción termina al acabar lo que hay."""
        self.abierto=False

    def cerrar(self):
        self.cerrado=True
        with self.stream_lock:
            stream,self.stream=self.stream,None
            if stream is not None:
                stream.abort();stream.close()
