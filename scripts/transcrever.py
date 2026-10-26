"""
transcrever.py
--------------
Transcreve um video ou audio salvo no computador (reuniao gravada, aula, entrevista)
via Groq (Whisper large-v3), com timestamp por paragrafo.

Modo arquivo unico:
    python transcrever.py --video "caminho/video.mp4" --out "pasta/destino"

Modo pasta (varios arquivos direto numa pasta, um por item):
    python transcrever.py --src "pasta/com/videos" --out "pasta/destino"

Opcional --prompt "vocabulario especifico" ajuda o Whisper a acertar termos tecnicos ou
nomes proprios que ele erraria sem contexto (ex. siglas do seu setor).

Requer a variavel de ambiente GROQ_API_KEY e ffmpeg/ffprobe no PATH.
"""

import os
import re
import sys
import time
import json
import math
import argparse
import tempfile
import subprocess
from pathlib import Path

try:
    from groq import Groq
    import groq
except ImportError:
    print("Erro: pacote 'groq' nao instalado. Rode: pip install groq")
    sys.exit(1)

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

LIMITE_MB = 24
BITRATE_AUDIO = "48k"
MODELO = "whisper-large-v3"
ESPERA_MAX_S = 75 * 60      # acima disso o limite e diario: para e avisa
TENTATIVAS = 6
EXTENSOES = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".wav", ".m4a")


def log(msg):
    print(msg, flush=True)


def formatar_ts(s):
    s = int(s)
    return f"{s // 3600:02}:{(s % 3600) // 60:02}:{s % 60:02}"


def duracao_video(p):
    r = subprocess.run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(p)],
                        capture_output=True, encoding="utf-8", errors="replace")
    return float(json.loads(r.stdout)["format"]["duration"])


def extrair_audio(video, destino, inicio, duracao):
    cmd = ["ffmpeg", "-y", "-ss", str(inicio), "-t", str(duracao), "-i", str(video),
           "-vn", "-ar", "16000", "-ac", "1", "-ab", BITRATE_AUDIO, "-f", "mp3", str(destino)]
    r = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
    return r.returncode == 0


def segundos_de_espera(erro):
    m = re.search(r"try again in\s+(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)s)?", str(erro))
    if m and any(m.groups()):
        h, mi, s = (float(x) if x else 0 for x in m.groups())
        return h * 3600 + mi * 60 + s
    try:
        return float(erro.response.headers.get("retry-after"))
    except Exception:
        return 60.0


class LimiteDiario(Exception):
    pass


def transcrever_chunk(client, audio, offset, prompt):
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            with open(audio, "rb") as f:
                resp = client.audio.transcriptions.create(
                    file=f, model=MODELO, language="pt", prompt=prompt or "",
                    response_format="verbose_json", timestamp_granularities=["segment"])
            segs = []
            for seg in resp.segments:
                g = (lambda k: seg.get(k)) if isinstance(seg, dict) else (lambda k: getattr(seg, k))
                segs.append({"start": g("start") + offset, "end": g("end") + offset, "text": g("text").strip()})
            return segs
        except groq.RateLimitError as e:
            espera = segundos_de_espera(e) + 5
            if espera > ESPERA_MAX_S:
                raise LimiteDiario(f"limite diario da Groq (espera de {espera/60:.0f} min)")
            log(f"    limite de uso da Groq, aguardando {espera/60:.1f} min...")
            time.sleep(espera)
        except (groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError) as e:
            espera = 20 * tentativa
            log(f"    erro de rede/servidor ({type(e).__name__}), tentativa {tentativa}/{TENTATIVAS}, aguardando {espera}s")
            time.sleep(espera)
    raise RuntimeError("falhou apos varias tentativas")


def transcrever_video(client, video, prompt):
    duracao = duracao_video(video)
    seg_por_chunk = LIMITE_MB * 1024 * 1024 * 8 / (int(BITRATE_AUDIO[:-1]) * 1000)
    n = max(1, math.ceil(duracao / seg_por_chunk))
    segmentos = []
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(n):
            ini = i * seg_por_chunk
            dur = min(seg_por_chunk, duracao - ini)
            mp3 = os.path.join(tmp, f"c{i}.mp3")
            if not extrair_audio(video, mp3, ini, dur):
                raise RuntimeError(f"ffmpeg falhou no trecho {i+1}/{n}")
            segmentos += transcrever_chunk(client, mp3, ini, prompt)
    return duracao, segmentos


def paragrafos(segmentos):
    saida, ini, textos, palavras = [], None, [], 0
    for s in segmentos:
        if ini is None:
            ini = s["start"]
        textos.append(s["text"])
        palavras += len(s["text"].split())
        if palavras > 120:
            saida.append((ini, " ".join(textos)))
            ini, textos, palavras = None, [], 0
    if textos:
        saida.append((ini, " ".join(textos)))
    linhas = []
    for ini, texto in saida:
        texto = re.sub(r"\s+", " ", texto).strip()
        if texto:
            linhas.append(f"[{formatar_ts(ini)}] {texto}")
    return "\n\n".join(linhas)


def transcrever_um(client, video, out_dir, prompt):
    out_dir.mkdir(parents=True, exist_ok=True)
    out_txt = out_dir / "transcricao.txt"
    if out_txt.exists() and out_txt.stat().st_size > 0:
        log(f"{video.name}: ja transcrita, pulando")
        return True
    log(f"{video.name} ...")
    t0 = time.time()
    try:
        duracao, segs = transcrever_video(client, video, prompt)
    except LimiteDiario as e:
        log(f"PARADO: {e}. Rode de novo depois, ele retoma daqui.")
        return False
    except Exception as e:
        log(f"    ERRO: {e}")
        return True
    if not segs:
        log("    ERRO: nenhum segmento")
        return True
    out_txt.write_text(paragrafos(segs), encoding="utf-8")
    log(f"    OK, {duracao/60:.1f} min de video em {time.time()-t0:.0f}s")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", help="arquivo unico de video/audio")
    ap.add_argument("--src", help="pasta com varios arquivos de video/audio")
    ap.add_argument("--out", required=True, help="pasta de destino")
    ap.add_argument("--prompt", default=None, help="vocabulario especifico pra ajudar o Whisper")
    args = ap.parse_args()

    if not args.video and not args.src:
        print("Erro: informe --video (arquivo unico) ou --src (pasta).")
        sys.exit(1)

    if not os.environ.get("GROQ_API_KEY"):
        log("Erro: GROQ_API_KEY nao definida. Configure a variavel de ambiente antes de rodar.")
        sys.exit(1)
    client = Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=0)

    out = Path(args.out)

    if args.video:
        video = Path(args.video)
        transcrever_um(client, video, out, args.prompt)
    else:
        src = Path(args.src)
        arquivos = sorted([p for p in src.iterdir() if p.suffix.lower() in EXTENSOES])
        total = len(arquivos)
        for i, video in enumerate(arquivos, 1):
            log(f"[{i}/{total}]")
            continua = transcrever_um(client, video, out / video.stem, args.prompt)
            if not continua:
                sys.exit(2)

    log("Concluido.")


if __name__ == "__main__":
    main()
