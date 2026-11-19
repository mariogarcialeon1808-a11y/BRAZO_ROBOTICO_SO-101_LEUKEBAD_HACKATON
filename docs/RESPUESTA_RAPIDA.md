# Respuesta rápida: el turno frase a frase

Desde que se envía una pregunta hasta que suena la primera palabra pasaban 9–10 s, y 16–19 s
la primera vez que se usaba un idioma. Ahora son 2–3,5 s en los dos casos.

## De dónde salía la espera

Medido el 15-11-2026 con la IA real y la voz de ElevenLabs:

| Paso | Antes |
|---|---|
| La IA escribe la respuesta entera | 2,3–3,2 s |
| Voz de toda la respuesta y cálculo de todos los gestos (a la vez) | 2,7–3,6 s |
| Silencio inicial para que el primer gesto llegue a su palabra | 1–3,6 s |
| Varios | 1 s |
| Primer uso de una voz de ElevenLabs en la sesión | 10–13 s más |

Nada sonaba hasta tener la respuesta entera, toda la voz y todos los gestos.

## Qué se hace ahora

1. **La IA entrega cada frase en cuanto la termina de escribir** (`Vision.por_bloques`). La primera
   llega a los 1,2–2,4 s. Cada frase se comprueba igual que antes: si no está en el idioma del
   turno no se dice, y se pide el resto corregido.
2. **La voz llega por trozos** de medio segundo (`Voz.sintetizar(…, al_trozo)`) y suena con el
   primero, unas 4 décimas después de pedirla. El altavoz queda abierto y se le va añadiendo audio
   (`Reproductor(abierto=True)`); si se queda sin audio emite silencio y su reloj sigue corriendo.
3. **No hay silencio inicial.** El gesto de cada frase se coloca en cuanto la voz ha dado el
   instante de su palabra, sin esperar al resto de la frase.
4. **Las voces se usan una vez al abrir la sesión**, con una sílaba y en segundo plano
   (`Voz.preparar`), para que esa primera vez tan lenta no caiga en una pregunta. Gasta unos 15
   créditos de ElevenLabs por sesión.
5. **Más formatos de región aceptados.** La IA a veces escribe una región como
   `[ymin, xmin, [ymax, xmax]]`; antes eso costaba pedir la respuesta otra vez (2 s). Además, en
   este modo, una frase con el gesto mal escrito se narra sin gesto en vez de repetir la petición.

Todo sigue sobre un único reloj, el del altavoz, igual que antes.

## Los gestos

A 110°/s un gesto dura de 5 a 10 s (solo llegar al ápice son unos 2 s) y una frase, 6 o 7. Por eso:

- El gesto de una frase puede **empezar antes de que suene su frase**, sobre el final de la
  anterior, como hacía el turno entero. Los acentos que aún no han empezado le ceden el sitio.
- En la **primera frase** eso no es posible: el gesto empieza en cuanto está calculado y llega a su
  palabra con hasta 2,5 s de retraso. Si el retraso fuera mayor, se omite y se dice.
- Un gesto solo empieza cuando ha terminado el anterior. Si no cabe, se omite, igual que antes.
- **La voz ya no se estira.** El turno entero frenaba la narración para encajar los gestos; ahora
  la voz va siempre a su ritmo.
- En los ratos libres de cada frase se añaden acentos, y el brazo que no hace el gesto lo acompaña.

Antes de ejecutar cada plan se sigue comprobando con los encoders que el brazo está donde el plan
empieza (5° de margen), y con los brazos reales cada plan se valida contra sus rangos.

Al terminar el turno el registro dice cuánto tardó: «Primera palabra a los 2.6 s; 1 gesto(s) algo
después de su palabra (hasta 1.2 s).»

## Los gestos se calculan en otro proceso

Compilar un gesto ocupa un núcleo entre 0,3 y 1,5 s, y ahora ocurre mientras los brazos se mueven
con la frase anterior. Hecho dentro del programa le quitaba el turno a los demás hilos: en
simulación la física avanzó 1,1 s en 2,7 s y el control se detuvo con «error de seguimiento >25
grados». Por eso se calculan en un proceso aparte (`control/calculo_aparte.py`), que arranca al
abrir la sesión (0,8–1,5 s, en segundo plano). Solo viajan consignas y constantes: el motor de
gestos, la intención, la postura de partida prevista y el audio generado de la frase. Ninguna
medida de sensores. Si ese proceso no arranca o se cae, el cálculo se hace en el programa cediendo
el paso a los demás hilos diez veces más a menudo.

Con esto, el hilo más perjudicado esperó como mucho 22–36 ms durante un turno (55 ms en el turno
entero); el aviso de «pico de latencia» salta a 200 ms.

## Volver al turno de antes

En la pestaña 4, la casilla **Frase a frase** está marcada. Sin marcar, el siguiente turno es el
de siempre: todo preparado y luego suena, con los gestos exactamente en su palabra y la voz
adaptada a ellos. Para dejarlo así de forma fija, `por_frases = false` en `[conversacion]` de
`config/so101er.toml` (y en su copia `src/so101er/predeterminado.toml`).

## Comprobado (15-11-2026, sin brazos)

Con brazos de encoders simulados sobre la calibración guardada, la IA real, voz simulada con los
tiempos medidos de ElevenLabs y un altavoz sin sonido:

| Petición | Primera palabra | Gestos |
|---|---|---|
| «explica lo que ves» | 2,7 s | 3 de 4; uno 0,8 s después de su palabra |
| «explain what you see» (cambio de idioma) | 2,9 s | 3 de 4; hasta 1,9 s después |
| «¿y el sol?» | 3,5 s | 3 de 3; hasta 2,1 s después |
| «explique-moi ce que tu vois» (primer turno, con despliegue) | 2,4 s | 3 de 4; hasta 2,1 s después |
| El mismo banco con el turno entero | 15,2 s | 3 de 4, en su palabra |

Un turno completo en simulación (motor de gestos, control y física reales) forma parte de las
pruebas: `tests/test_turno_por_frases.py`.

## Sin comprobar

- **Con los brazos reales.** Todo lo anterior es sin hardware.
- **Con la voz real de ElevenLabs dentro del turno.** La entrega por trozos se midió aparte
  (primer trozo a 0,33–0,6 s); el turno completo se ha medido con voz simulada para no gastar crédito.
- **Cómo se ve** un gesto que llega 2 s después de su palabra en la primera frase. Si no convence,
  la casilla permite comparar con el turno de antes.
