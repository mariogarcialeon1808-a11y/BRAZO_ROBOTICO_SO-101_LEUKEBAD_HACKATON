"""Descarga opcional de los pesos públicos que usa el ASR local."""
import argparse
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destino',type=Path,
                        default=Path(__file__).resolve().parents[1]/'datos/modelos/whisper_base')
    args=parser.parse_args()
    from huggingface_hub import snapshot_download
    snapshot_download('Systran/faster-whisper-base',local_dir=str(args.destino),
                      allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*'])
    if not (args.destino/'model.bin').is_file():raise RuntimeError('faltan los pesos descargados')
    print('Whisper base instalado en '+str(args.destino))


if __name__=='__main__':main()
