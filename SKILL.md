---
name: transcrever-local
description: Transcreve um vídeo ou áudio salvo no computador (reunião gravada, aula, entrevista) em texto com timestamp por parágrafo, usando Whisper via API da Groq. Pede pra instalar o que faltar (ffmpeg, pacote groq, chave de API) na primeira vez. Use quando o usuário mandar um arquivo de vídeo ou áudio local pedindo pra transcrever, "transcreve essa reunião", "transcreve essa gravação", "transforma esse vídeo em texto", ou mencionar um caminho de arquivo de vídeo/áudio no computador pedindo transcrição.
---

# Transcrever Local

Transcreve um vídeo ou áudio que já está salvo no computador (não é link de internet, pra
isso existe a skill `transcribe`) em texto, com timestamp por parágrafo, via Whisper
(API da Groq, gratuita até um certo volume de uso).

## Fase 0 — Setup (só na primeira vez, ou se faltar algo)

Checar, nessa ordem, e perguntar antes de instalar qualquer coisa:

1. **ffmpeg instalado e no PATH** (`ffmpeg -version` no terminal). Se não tiver, explicar
   como instalar conforme o sistema operacional do usuário (Windows: `winget install
   ffmpeg`, ou baixar manualmente; Mac: `brew install ffmpeg`; Linux: gerenciador de
   pacote da distro) e perguntar se pode rodar o comando de instalação agora
2. **Pacote Python `groq` instalado** (`python -c "import groq"`). Se faltar, perguntar se
   pode rodar `pip install groq` (ou `python -m pip install groq`, em máquina com `pip`
   bloqueado por política, como algumas corporativas)
3. **Variável de ambiente `GROQ_API_KEY` configurada.** Se não existir:
   - Explicar que é grátis: criar conta em console.groq.com, gerar uma chave de API lá
   - Perguntar se o usuário já tem uma chave, ou se precisa criar agora
   - Depois de ter a chave, configurar como variável de ambiente permanente (Windows:
     variável de ambiente do usuário, via painel de controle ou
     `setx GROQ_API_KEY "chave"`; Mac/Linux: exportar no perfil do shell, `~/.zshrc` ou
     `~/.bashrc`). **Nunca** colar a chave direto no código ou em arquivo versionado no
     Git
4. Mostrar o que já está instalado/configurado e só pedir o que realmente falta, sem
   repetir passo já feito

## Fase 1 — Rodar a transcrição

Script em `scripts/transcrever.py`. Dois modos:

```
# arquivo único
python scripts/transcrever.py --video "caminho/da/reuniao.mp4" --out "pasta/destino"

# pasta com vários arquivos (cada um vira uma transcrição separada)
python scripts/transcrever.py --src "pasta/com/videos" --out "pasta/destino"
```

- Perguntar ao usuário qual arquivo (ou pasta) ele quer transcrever, se não tiver vindo
  junto do pedido
- Se o vídeo tratar de um vocabulário específico (termos técnicos, siglas, nomes próprios
  que o Whisper erraria sem contexto), perguntar se o usuário quer passar um `--prompt`
  com esse vocabulário. Sem isso, o Whisper tende a inventar grafia pra sigla que não
  conhece
- O script retoma sozinho de onde parou se for interrompido (pula arquivo já transcrito) e
  para automaticamente se bater no limite diário da Groq, avisando pra rodar de novo depois
- Vídeo grande demora: avisar o usuário que pode levar alguns minutos, não é travamento

## Fase 2 — Entregar

- Confirmar que a transcrição foi salva (`transcricao.txt`, com timestamp `[HH:MM:SS]` a
  cada parágrafo) e mostrar o caminho
- Se o usuário quiser, oferecer resumir ou extrair um passo a passo da transcrição em
  seguida, mas isso é outro pedido, não fazer sem perguntar

## Regras

1. Nunca instalar nada (ffmpeg, pacote Python, variável de ambiente) sem perguntar antes
2. Nunca colocar a chave da API direto no código, só em variável de ambiente
3. Se o GROQ_API_KEY não estiver configurado, parar e orientar o usuário, nunca inventar
   ou usar uma chave de exemplo
4. Timestamp sempre no formato `[HH:MM:SS]`, igual o script já gera
