# Sintetiza texto con una voz instalada en Windows y devuelve la marca de cada palabra.
#
# Una frase:   voz_windows.ps1 -Texto frase_utf8.txt -Salida audio.wav [-Voz "..."] [-Ritmo 0]
# Servidor:    voz_windows.ps1 -Servidor [-Voz "..."] [-Ritmo 0]
#              Escribe LISTO y despues atiende lineas "frase_utf8.txt|audio.wav" por la entrada
#              estandar, respondiendo a cada una con una linea JSON. Asi la voz ya esta cargada
#              y cada frase sale al instante.
#
# El audio se escribe a 24 kHz, 16 bits, mono. El JSON lleva, por palabra, su posicion en el
# texto (caracteres) y la marca de audio del motor de voz (el programa la pasa a segundos reales).
param(
    [string]$Texto = "",
    [string]$Salida = "",
    [string]$Voz = "",
    [int]$Ritmo = 0,
    [switch]$Servidor
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($Voz -ne "") {
    $s.SelectVoice($Voz)
} else {
    $es = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like "es-*" } | Select-Object -First 1
    if ($null -eq $es) { throw "No hay ninguna voz en castellano instalada en Windows." }
    $s.SelectVoice($es.VoiceInfo.Name)
}
$s.Rate = $Ritmo
$s.Volume = 100
$nombre = $s.Voice.Name
$marcas = New-Object System.Collections.ArrayList
$manejador = [System.EventHandler[System.Speech.Synthesis.SpeakProgressEventArgs]] {
    param($origen, $a)
    [void]$marcas.Add(@{ c = $a.CharacterPosition; t = [math]::Round($a.AudioPosition.TotalSeconds, 3) })
}
$s.add_SpeakProgress($manejador)
$formato = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
    24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)

function Decir([string]$rutaTexto, [string]$rutaSalida) {
    $marcas.Clear()
    $frase = [System.IO.File]::ReadAllText($rutaTexto, [System.Text.Encoding]::UTF8)
    $s.SetOutputToWaveFile($rutaSalida, $formato)
    $s.Speak($frase)
    $s.SetOutputToNull()
    return (ConvertTo-Json -InputObject @{ voz = $nombre; palabras = @($marcas) } -Compress -Depth 4)
}

if ($Servidor) {
    [Console]::Out.WriteLine("LISTO")
    [Console]::Out.Flush()
    while ($true) {
        $linea = [Console]::In.ReadLine()
        if ($null -eq $linea -or $linea -eq "") { break }
        $partes = $linea.Split("|")
        try {
            $respuesta = Decir $partes[0] $partes[1]
        } catch {
            $respuesta = '{"error":"fallo al sintetizar"}'
        }
        [Console]::Out.WriteLine($respuesta)
        [Console]::Out.Flush()
    }
} else {
    Decir $Texto $Salida
}
[Environment]::Exit(0)
