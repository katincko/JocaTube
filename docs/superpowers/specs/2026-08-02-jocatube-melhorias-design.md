# JocaTube — Melhorias (Playlist, WAV/MP3 real, correção de bugs)

**Data:** 2026-08-02
**Arquivo alvo:** `JocaTube.py`
**Restrição global:** manter a estética atual (tema dark/light, cores dark-blue, fonte roboto). UI nova só é permitida para playlist, seguindo o mesmo estilo.

---

## Contexto

`JocaTube.py` é um downloader de YouTube em `customtkinter` (arquivo único, procedural,
widgets globais posicionados por `.place()` absoluto). Usa `pytubefix` para baixar e
`imageio_ffmpeg` para o binário do ffmpeg embutido.

O usuário usa o app para baixar músicas/sons para samples no FL Studio. Por isso,
áudio lossless (WAV) é prioridade.

## Objetivos

1. Adicionar formatos de áudio **WAV** e **MP3 real** (via ffmpeg).
2. Adicionar **download de playlist** com UI dedicada.
3. Corrigir bugs existentes sem alterar o visual.
4. Melhorias de UX aprovadas: itens 1–6, 8, 9 da lista (ver abaixo).

Fora de escopo: normalizar áudio / cortar silêncio.

---

## 1. Áudio real: WAV + MP3

**Problema atual:** a opção "MP3" faz `audio_stream.download(filename="...mp3")` — apenas
renomeia o container `.mp4`/`webm` para `.mp3`. Não é um MP3 válido.

**Solução:** converter com o ffmpeg embutido (`imageio_ffmpeg.get_ffmpeg_exe()`).

- Menu de formato passa a conter: `WAV`, `MP3`, seguidos das resoluções de vídeo disponíveis.
- **WAV:** baixa melhor stream de áudio → `ffmpeg -i temp -acodec pcm_s16le -ar 44100 saida.wav` → remove temp.
- **MP3:** baixa melhor stream de áudio → `ffmpeg -i temp -codec:a libmp3lame -b:a <bitrate> saida.mp3` → remove temp.
  - Bitrate escolhível: 128 / 256 / 320 kbps (extra #6). Default 320.
  - Metadata + capa (extra #4): `-metadata title=<titulo>` e capa embutida a partir da thumbnail
    quando a codificação for MP3 (usa `-i thumb.jpg -map 0:a -map 1:0 -id3v2_version 3`).

**Fluxo comum de conversão** (função `converter_audio(temp_path, destino, formato, bitrate, titulo, thumb_path)`):
download temp → chama ffmpeg → em sucesso remove temp; em erro propaga mensagem legível.

## 2. Playlist com UI dedicada

**Detecção:** ao clicar BUSCAR, tenta identificar se a URL é playlist
(`"list=" in url` e/ou `Playlist(url)` retorna vídeos). Se for playlist, mostra o
**painel de playlist** em vez do card de vídeo único.

**Painel de playlist** (mesmo tema/cores/fonte):
- Título da playlist + contagem "N vídeos".
- Menu de formato/resolução (mesmo componente do modo single).
- Botão "Baixar Playlist".
- Barra de progresso geral + label de status: **"Baixando X de N: <título>"**.

**Comportamento de download:**
- Itera `playlist.videos`, baixando cada um no formato escolhido reaproveitando a
  lógica de download single (refatorada para função `baixar_video(yt, formato, diretorio, ...)`).
- Erros por vídeo não abortam o lote: coleta falhas e segue.
- Ao final: **"Concluído: X baixados, Y falharam"**.
- Roda em thread separada; atualizações de UI via `root.after(...)` para segurança.

## 3. Correção de bugs

| Bug | Correção |
|-----|----------|
| `except:` mudo engole o erro | Capturar exceções específicas e exibir mensagem real (indisponível, sem conexão, etc.) |
| Sobrescreve arquivo de nome igual | `caminho_unico()` adiciona ` (1)`, ` (2)`… antes de salvar |
| Resoluções indisponíveis viram opção selecionável e quebram no download | Filtrar do menu — só mostra o que existe |
| Link vazio dispara BUSCAR à toa | Validar `entry.get().strip()` não-vazio |
| Diretório vazio (cancelar dialog) | Já tratado; manter e reforçar |
| Barra de progresso não reseta entre vídeo e áudio | Resetar `barra_progresso.set(0)` no início de cada stream |
| Clique duplo durante download | Desabilitar botões enquanto baixa, reabilitar ao terminar |

## 4. Melhorias de UX aprovadas

1. **Lembrar última pasta** — salvar em `~/.jocatube_config.json`; usar como `initialdir` no diálogo.
2. **Botão "Abrir pasta"** ao concluir — abre o explorer na pasta de destino (`os.startfile`).
3. **Enter dispara BUSCAR** — bind `<Return>` no `entry`.
4. **Metadata + capa no MP3** — ver seção 1.
5. **Botão Cancelar** — flag de cancelamento (`threading.Event`) checada entre streams/itens da playlist.
6. **Bitrate MP3 (128/256/320)** — menu adicional visível só quando formato = MP3.
8. **Checar ffmpeg no start** — validar `get_ffmpeg_exe()` existe; avisar claramente se faltar.
9. **Pinar versões no requirements.txt** — fixar versões testadas.

Não incluído: (7) normalizar áudio / cortar silêncio.

---

## Arquitetura / refatoração

Mantém arquivo único e estilo procedural (não reescrever tudo). Extrai funções puras
reutilizáveis para reduzir duplicação e permitir playlist:

- `sanitize_filename(nome)` — já existe; manter.
- `caminho_unico(pasta, nome, ext)` — novo; resolve colisão de nome.
- `converter_audio(temp, destino, formato, bitrate, titulo, thumb)` — novo; encapsula ffmpeg.
- `baixar_video(yt, formato, diretorio, on_progress, cancel_event)` — novo; lógica única de
  download usada tanto pelo modo single quanto pela playlist.
- `carregar_config()` / `salvar_config()` — novo; persistência da última pasta.

UI: os widgets do painel de playlist são criados sob demanda e escondidos com
`place_forget()` quando em modo single, e vice-versa — sem quebrar o layout existente.

## Tratamento de erros

- Toda operação de rede/ffmpeg encapsulada com captura específica → `label3` recebe
  mensagem legível em vermelho.
- ffmpeg com `check=True`; em `CalledProcessError`, reporta falha de conversão.
- Playlist: falhas por item são acumuladas, não abortam o lote.

## Testes / verificação

Projeto é GUI sem suíte de testes. Verificação:
- Funções puras (`caminho_unico`, `sanitize_filename`, detecção de playlist, montagem do
  comando ffmpeg) testadas isoladamente via script rápido.
- Verificação manual: baixar 1 vídeo em WAV, 1 em MP3 (conferir header real), 1 playlist curta.
