"""Exportación reproducible de los cuatro ejemplos, sin activar hardware."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from .control.semantico import MotorGestos, ejemplos


def exportar(cfg, destino, referencia=None, casos=None):
    motor = MotorGestos(cfg)
    motivo = None
    if referencia:
        from .control.referencias import Motivo, adaptar
        motivo = Motivo.cargar(referencia)
    bloques = []
    for nombre, g, encoders in (ejemplos(motor) if casos is None else casos):
        if motivo:
            g = adaptar(motivo, g)
        if casos is None:
            from .control.escenico import pose_reposo,ensanchar_abanico,compilar_actuacion
            encoders={n:pose_reposo(motor) for n in motor.marcos}
            if nombre in ('paisaje','cielo'):g=ensanchar_abanico(motor,g)
            plan=compilar_actuacion(motor,g,encoders,bilateral=nombre in ('paisaje','cielo'))
        else:
            plan = motor.compilar(g, encoders)
        # La vista previa puede bajar a 25 FPS; JSON conserva todas las consignas.
        frames = []
        for t in plan.tiempos[::max(1, round(cfg.frecuencia_hz/25))]:
            qs = plan.muestra(float(t))
            frames.append({"t": float(t), "cadenas": {
                n: motor.marcos[n].a_mundo(motor.modelo.puntos(q[:5])).tolist()
                for n, q in qs.items()}})
        bloques.append({"nombre": nombre, "intencion": asdict(plan.intencion),
                        "origen_estado": "fixture_nominal_NO_encoder_real",
                        "referencia_ritmo": {"id": motivo.id, "fuente": motivo.fuente,
                                             "sha256": motivo.sha256} if motivo else None,
                        "encoders_iniciales": {n:q.tolist() for n,q in encoders.items()},
                        "tiempos_s": plan.tiempos.tolist(),
                        "q_grados_pinza_pct": {n:q.tolist() for n,q in plan.q.items()},
                        "inicio_trazo_s": plan.inicio_trazo, "fin_trazo_s": plan.fin_trazo,
                        "inicio_retorno_s":plan.inicio_retorno,"reposo_al_final":plan.reposo_al_final,
                        "error_puntos_mm": plan.error_posicion_mm,
                        "error_ejes_grados": plan.error_eje_grados, "frames": frames})
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    data = {"version": 1, "hardware_activado": False, "bloques": bloques,
            "calibracion": {n:{"base_mm":m.pos.tolist(), "rotacion":m.rot.tolist()}
                            for n,m in motor.marcos.items()}}
    (destino / "cuatro_gestos.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    (destino / "cuatro_gestos.html").write_text(HTML.replace("__DATA__", payload), encoding="utf-8")
    return {"json": str((destino / 'cuatro_gestos.json').resolve()),
            "vista_previa": str((destino / 'cuatro_gestos.html').resolve()),
            "hardware_activado": False,
            "ejemplos": [{"nombre":b["nombre"], "duracion_s":b["tiempos_s"][-1],
                           "error_puntos_mm":b["error_puntos_mm"],
                           "error_ejes_grados":b["error_ejes_grados"]} for b in bloques]}


HTML = '''<!doctype html><html lang="es"><meta charset="utf-8">
<title>SO-101 · Cuatro gestos</title>
<style>body{background:#111827;color:#eef2ff;font:17px system-ui;margin:24px auto;max-width:1100px}
button,select,input{font:inherit;margin:8px}canvas{width:100%;background:#172234;border-radius:14px}
small{color:#b5c7de}input{width:55%}</style>
<h1>SO-101 · Motor de gestos</h1>
<p>Geometría nominal de dos brazos. Vista previa cinemática; sin conexión a motores.</p>
<select id="example"></select><button id="play">Pausar</button><button id="view">Cambiar vista</button>
<canvas width="1100" height="560" id="canvas"></canvas>
<input id="time" type="range" min="0" max="1" step=".001"><span id="status"></span>
<p id="meaning"></p><small>Naranja: izquierdo · Verde: derecho · Azul: trayectoria solicitada.
El segundo brazo mantiene apoyo estable. Las posiciones iniciales son datos de demostración, no lecturas del robot.</small>
<script>const data=__DATA__,select=document.getElementById('example'),canvas=document.getElementById('canvas'),
ctx=canvas.getContext('2d'),slider=document.getElementById('time'),status=document.getElementById('status');
const meanings={paisaje:'Extensión: abanico horizontal sobre una superficie.',cielo:'Extensión elevada: abanico dirigido hacia el cielo.',punto:'Señalamiento: eje estable hacia un punto del plano nominal.',camino:'Recorrido recto: el cabezal permanece paralelo al camino.'};
data.bloques.forEach((b,i)=>select.add(new Option(b.nombre,i)));
let running=true,t=0,last=performance.now(),view=0;
document.getElementById('play').onclick=()=>{running=!running;document.getElementById('play').textContent=running?'Pausar':'Reproducir'};
document.getElementById('view').onclick=()=>{view=(view+1)%3};
slider.oninput=()=>{t=Number(slider.value)*data.bloques[select.value].tiempos_s.at(-1)};
select.onchange=()=>{t=0};
function project(p){let [x,y,z]=p;if(view===0)return [550+x*.95+y*.32,470-z*1.05-y*.23];if(view===1)return[550+x,470-z];return[550+x,480-y*.9]}
function line(points,color,width=3){ctx.strokeStyle=color;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>{let [x,y]=project(p);i?ctx.lineTo(x,y):ctx.moveTo(x,y)});ctx.stroke()}
function frame(now){let b=data.bloques[select.value];if(running)t+=(now-last)/1000;last=now;if(t>b.tiempos_s.at(-1)+.8)t=0;
ctx.clearRect(0,0,1100,560);line([[-430,0,0],[430,0,0]],'#526178',1);
let f=b.frames.reduce((a,c)=>Math.abs(c.t-t)<Math.abs(a.t-t)?c:a,b.frames[0]);
line(b.intencion.puntos_mm,'#73aaff',3);
Object.entries(f.cadenas).forEach(([n,chain])=>{const c=n==='izq'?'#ffb15c':'#62e7b0';line(chain,c,9);chain.forEach(p=>{let [x,y]=project(p);ctx.fillStyle='#e8efff';ctx.beginPath();ctx.arc(x,y,4,0,7);ctx.fill()})});
slider.value=Math.min(t/b.tiempos_s.at(-1),1);status.textContent=t.toFixed(2)+' s · '+(t<b.inicio_trazo_s?'preparación':t<b.fin_trazo_s?'trazo':b.inicio_retorno_s!=null&&t>=b.inicio_retorno_s?'vuelta a reposo':'sostenido');
document.getElementById('meaning').textContent=(meanings[b.nombre]||b.nombre)+(b.referencia_ritmo?' Ritmo importado: '+b.referencia_ritmo.id+'. Geometría adaptada al objetivo.':'');requestAnimationFrame(frame)}requestAnimationFrame(frame);
</script></html>'''


