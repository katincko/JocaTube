import customtkinter
from tkinter import filedialog
from pytubefix import YouTube, Playlist
import urllib.request
from PIL import Image, ImageDraw
import os, threading, subprocess, re, json, itertools
from io import BytesIO
import imageio_ffmpeg as ffmpeg


# Tema usado no app
customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("dark-blue")
tema = "dark"

# definições da janela.

root = customtkinter.CTk()

root.geometry("1024x768")
root.title("JocaTube!")


# Get the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))

# Construct the path to the icon file
icon_path = os.path.join(script_dir, 'Icone.ico')


def _set_icon():
    # Não quebra o app caso o .ico não exista.
    try:
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except Exception:
        pass


root.after(201, _set_icon)


# Frame da janela
frame = customtkinter.CTkFrame(master=root)
frame.pack(pady=20, padx=60, fill="both", expand=True)


# ---------------------------------------------------------------------------
# Configuração persistente (lembra a última pasta usada)
# ---------------------------------------------------------------------------
CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".jocatube_config.json")


def carregar_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def salvar_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass


config = carregar_config()


# ---------------------------------------------------------------------------
# Estado global
# ---------------------------------------------------------------------------
modo = "single"          # "single" ou "playlist"
yt = None                # YouTube atual (modo single)
playlist = None          # Playlist atual (modo playlist)
downloading = False
last_download_dir = ""
diretorio_download = ""
cancel_event = threading.Event()
_tmp = itertools.count()  # gera nomes de arquivo temporário únicos


class Cancelado(Exception):
    """Levantada quando o usuário cancela o download."""
    pass


# ---------------------------------------------------------------------------
# Helpers puros / utilidades
# ---------------------------------------------------------------------------
def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename).strip()


def caminho_unico(pasta, nome, ext):
    """Evita sobrescrever: adiciona (1), (2)... se o arquivo já existir."""
    destino = os.path.join(pasta, f"{nome}{ext}")
    if not os.path.exists(destino):
        return destino
    i = 1
    while True:
        destino = os.path.join(pasta, f"{nome} ({i}){ext}")
        if not os.path.exists(destino):
            return destino
        i += 1


def eh_playlist(url):
    u = url.lower()
    if "playlist?" in u:
        return True
    if "list=" in u and "watch" not in u and "youtu.be/" not in u and "/shorts/" not in u:
        return True
    return False


def get_ffmpeg():
    return ffmpeg.get_ffmpeg_exe()


def traduzir_erro(e):
    if isinstance(e, Cancelado):
        return "Cancelado."
    txt = str(e).lower()
    if any(k in txt for k in ("urlopen", "getaddrinfo", "connection", "network", "timed out")):
        return "Sem conexão com a internet."
    if any(k in txt for k in ("unavailable", "private", "age", "members-only", "restrict")):
        return "Vídeo indisponível ou restrito."
    if "non-zero" in txt or "ffmpeg" in txt:
        return "Falha na conversão (ffmpeg)."
    return "Ocorreu um erro, tente novamente."


def carregar_img_url(url, size):
    """Carrega imagem de URL sem quebrar o app se estiver offline."""
    try:
        data = urllib.request.urlopen(url, timeout=10).read()
        return customtkinter.CTkImage(
            light_image=Image.open(BytesIO(data)),
            dark_image=Image.open(BytesIO(data)),
            size=size,
        )
    except Exception:
        return None


def round_image(image, radius):
    # Cria uma máscara circular para a imagem
    mask = Image.new("L", image.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle(
        (0, 0, image.size[0], image.size[1]), radius=radius, fill=255
    )
    # Aplica a máscara à imagem original
    rounded_image = image.copy()
    rounded_image.putalpha(mask)
    return rounded_image


def baixar_thumb_temp(yt_obj, pasta):
    """Baixa a thumbnail como .jpg temporário (usada como capa do MP3)."""
    try:
        data = urllib.request.urlopen(yt_obj.thumbnail_url, timeout=10).read()
        p = os.path.join(pasta, f"cover_temp_{next(_tmp)}.jpg")
        Image.open(BytesIO(data)).convert("RGB").save(p, "JPEG")
        return p
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Conversão de áudio (WAV / MP3 reais via ffmpeg embutido)
# ---------------------------------------------------------------------------
def converter_audio(temp, destino, formato, bitrate, titulo, thumb):
    exe = get_ffmpeg()
    if formato == "WAV":
        cmd = [
            exe, '-y', '-i', temp, '-vn',
            '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2',
            '-loglevel', 'quiet', destino,
        ]
    else:  # MP3 real
        if thumb and os.path.exists(thumb):
            cmd = [
                exe, '-y', '-i', temp, '-i', thumb,
                '-map', '0:a', '-map', '1:0',
                '-codec:a', 'libmp3lame', '-b:a', bitrate,
                '-id3v2_version', '3',
                '-metadata', f'title={titulo}',
                '-metadata:s:v', 'title=Album cover',
                '-metadata:s:v', 'comment=Cover (front)',
                '-loglevel', 'quiet', destino,
            ]
        else:
            cmd = [
                exe, '-y', '-i', temp, '-vn',
                '-codec:a', 'libmp3lame', '-b:a', bitrate,
                '-metadata', f'title={titulo}',
                '-loglevel', 'quiet', destino,
            ]
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# Lógica única de download (reutilizada por single e playlist)
# ---------------------------------------------------------------------------
def baixar_video(yt_obj, formato, diretorio, bitrate="320k", cancel=None):
    def check():
        if cancel is not None and cancel.is_set():
            raise Cancelado()

    nome = sanitize_filename(yt_obj.title) or "download"
    check()

    if formato in ("WAV", "MP3"):
        try:
            audio_stream = yt_obj.streams.filter(only_audio=True).order_by('abr').last()
        except Exception:
            audio_stream = None
        if audio_stream is None:
            audio_stream = yt_obj.streams.filter(only_audio=True).first()
        if audio_stream is None:
            raise RuntimeError("Sem stream de áudio disponível.")

        temp_name = f"audio_temp_{next(_tmp)}.mp4"
        audio_stream.download(output_path=diretorio, filename=temp_name)
        temp = os.path.join(diretorio, temp_name)
        check()

        ext = ".wav" if formato == "WAV" else ".mp3"
        destino = caminho_unico(diretorio, nome, ext)
        thumb = baixar_thumb_temp(yt_obj, diretorio) if formato == "MP3" else None
        try:
            converter_audio(temp, destino, formato, bitrate, yt_obj.title, thumb)
        finally:
            if os.path.exists(temp):
                os.remove(temp)
            if thumb and os.path.exists(thumb):
                os.remove(thumb)
        return destino

    else:  # resolução de vídeo
        video_stream = yt_obj.streams.filter(res=formato).first()
        if video_stream is None:
            video_stream = yt_obj.streams.get_highest_resolution()
        audio_stream = yt_obj.streams.filter(only_audio=True).first()
        if video_stream is None or audio_stream is None:
            raise RuntimeError("Streams de vídeo/áudio indisponíveis.")

        vn = f"video_temp_{next(_tmp)}.mp4"
        an = f"audio_temp_{next(_tmp)}.mp4"
        video_stream.download(output_path=diretorio, filename=vn)
        audio_stream.download(output_path=diretorio, filename=an)
        check()

        vfile = os.path.join(diretorio, vn)
        afile = os.path.join(diretorio, an)
        destino = caminho_unico(diretorio, nome, ".mp4")
        cmd = [
            get_ffmpeg(), '-y', '-i', vfile, '-i', afile,
            '-c:v', 'copy', '-c:a', 'aac', '-strict', 'experimental',
            '-loglevel', 'quiet', destino,
        ]
        try:
            subprocess.run(cmd, check=True)
        finally:
            if os.path.exists(vfile):
                os.remove(vfile)
            if os.path.exists(afile):
                os.remove(afile)
        return destino


# ---------------------------------------------------------------------------
# Helpers de UI (thread-safe)
# ---------------------------------------------------------------------------
def ui(fn):
    """Agenda uma atualização de UI na thread principal."""
    root.after(0, fn)


def set_status(text, color="gray"):
    label3.configure(text=text, text_color=color)
    label3.place(x=333, y=110)


def on_format_change(choice):
    # Mostra o menu de bitrate só quando o formato é MP3.
    if choice == "MP3":
        bitrate_menu.place(x=510, y=198)
    else:
        bitrate_menu.place_forget()


def set_downloading(flag):
    global downloading
    downloading = flag
    state = "disabled" if flag else "normal"
    button.configure(state=state)
    button_download.configure(state=state)
    if flag:
        cancel_button.place(x=510, y=238)
    else:
        cancel_button.place_forget()


def cancelar_download():
    cancel_event.set()
    set_status("Cancelando...", "orange")


def abrir_pasta():
    try:
        if last_download_dir and os.path.isdir(last_download_dir):
            os.startfile(last_download_dir)
    except Exception:
        pass


def download_concluido(pasta, texto="DOWNLOAD CONCLUÍDO!", cor="green"):
    global last_download_dir
    last_download_dir = pasta
    set_status(texto, cor)
    abrir_pasta_button.place(x=662, y=278)


def mostrar_thumbnail(url_image):
    global label_thumbnail
    response = urllib.request.urlopen(url_image, timeout=10)
    image_data = response.read()
    thumbnail = round_image(Image.open(BytesIO(image_data)), radius=20).convert("RGBA")
    rounded_thumbnail = round_image(thumbnail, radius=50)
    img = customtkinter.CTkImage(
        light_image=rounded_thumbnail, dark_image=rounded_thumbnail, size=(220, 180)
    )
    if label_thumbnail is None:
        label_thumbnail = customtkinter.CTkLabel(master=frame, text="", image=img)
        label_thumbnail.place(x=40, y=130)
    else:
        label_thumbnail.configure(image=img)


def on_progress(stream, chunk, bytes_remaining):
    # Atualiza a barra de progresso e porcentagem (modo single).
    try:
        totalsize = stream.filesize
        bytes_downloaded = totalsize - bytes_remaining
        percentage_completion = bytes_downloaded / totalsize * 100
        per = f"{int(percentage_completion)}%"

        def _upd():
            pPercentage.configure(text=per)
            if barra_progresso is not None:
                barra_progresso.set(percentage_completion / 100)

        root.after(0, _upd)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Threads de download
# ---------------------------------------------------------------------------
def run_single_download():
    try:
        formato = my_option.get()
        if "não disponível" in formato:
            ui(lambda: set_status("Resolução indisponível.", "red"))
            return
        bitrate = bitrate_menu.get() if formato == "MP3" else "320k"
        ui(lambda: set_status("Baixando...", "yellow"))
        destino = baixar_video(yt, formato, diretorio_download, bitrate, cancel_event)
        pasta = diretorio_download
        ui(lambda: download_concluido(pasta))
    except Exception as e:
        msg = traduzir_erro(e)
        ui(lambda: set_status(msg, "red"))
        print(f"Erro: {e}")
    finally:
        ui(lambda: set_downloading(False))


def run_playlist_download():
    try:
        formato = my_option.get()
        bitrate = bitrate_menu.get() if formato == "MP3" else "320k"
        videos = list(playlist.videos)
        total = len(videos)
        ok = 0
        falhas = 0
        for i, v in enumerate(videos, 1):
            if cancel_event.is_set():
                break
            try:
                tit = v.title
            except Exception:
                tit = f"vídeo {i}"

            def _upd(i=i, total=total, tit=tit):
                set_status(f"Baixando {i} de {total}: {tit[:28]}", "yellow")
                if barra_progresso is not None:
                    barra_progresso.set((i - 1) / total)

            ui(_upd)
            try:
                baixar_video(v, formato, diretorio_download, bitrate, cancel_event)
                ok += 1
            except Cancelado:
                break
            except Exception as e:
                falhas += 1
                print(f"Falha no vídeo {i}: {e}")

        ui(lambda: barra_progresso.set(1) if barra_progresso is not None else None)
        pasta = diretorio_download
        if cancel_event.is_set():
            ui(lambda: download_concluido(pasta, f"Cancelado. {ok} baixados.", "orange"))
        else:
            ui(lambda: download_concluido(pasta, f"Concluído: {ok} ok, {falhas} falharam.", "green"))
    except Exception as e:
        ui(lambda: set_status(traduzir_erro(e), "red"))
        print(f"Erro: {e}")
    finally:
        ui(lambda: set_downloading(False))


# função de download
def downloadbttn():
    global diretorio_download
    # Escolhe o diretório, lembrando o último usado.
    diretorio_download = filedialog.askdirectory(initialdir=config.get("last_dir", ""))
    if not diretorio_download:
        set_status("Diretório inválido.", "red")
        return

    config["last_dir"] = diretorio_download
    salvar_config(config)

    cancel_event.clear()
    abrir_pasta_button.place_forget()
    set_downloading(True)
    if barra_progresso is not None:
        barra_progresso.set(0)

    if modo == "playlist":
        threading.Thread(target=run_playlist_download, daemon=True).start()
    else:
        threading.Thread(target=run_single_download, daemon=True).start()


# ---------------------------------------------------------------------------
# Busca (detecta vídeo único ou playlist)
# ---------------------------------------------------------------------------
# Widgets globais
label_titulo = None
label_thumbnail = None
my_option = None
barra_progresso = None


def buscar():
    global button_download, my_option, yt, playlist, modo, label_titulo, barra_progresso

    url = entry.get().strip()
    if not url:
        set_status("Cole um link primeiro.", "red")
        return

    try:
        if eh_playlist(url):
            # ---------------- MODO PLAYLIST ----------------
            playlist = Playlist(url)
            qtd = len(playlist.video_urls)
            if qtd == 0:
                set_status("Playlist vazia ou inválida.", "red")
                return
            modo = "playlist"

            nome = playlist.title or "Playlist"
            if len(nome) > 30:
                nome = nome[:30] + "..."
            if label_titulo is None:
                label_titulo = customtkinter.CTkLabel(
                    master=frame, text=f"Playlist: {nome}", font=("roboto bold", 16))
                label_titulo.place(x=275, y=200)
            else:
                label_titulo.configure(text=f"Playlist: {nome}")

            label_playlist_info.configure(text=f"{qtd} vídeos")
            label_playlist_info.place(x=275, y=228)

            try:
                mostrar_thumbnail(playlist.videos[0].thumbnail_url)
            except Exception:
                pass

            opcoes = ["WAV", "MP3", "1080p", "720p", "480p", "360p"]

        else:
            # ---------------- MODO VÍDEO ÚNICO ----------------
            modo = "single"
            yt = YouTube(url, on_progress_callback=on_progress)
            label_playlist_info.place_forget()

            video_title = yt.title
            MAX_TITLE_LENGTH = 35
            if len(video_title) > MAX_TITLE_LENGTH:
                video_title = video_title[:MAX_TITLE_LENGTH] + "..."

            if label_titulo is None:
                label_titulo = customtkinter.CTkLabel(
                    master=frame, text=video_title, font=("roboto bold", 16))
                label_titulo.place(x=275, y=200)
            else:
                label_titulo.configure(text=video_title)

            mostrar_thumbnail(yt.thumbnail_url)

            # Monta as opções, filtrando resoluções indisponíveis.
            opcoes = []
            if yt.streams.filter(only_audio=True).first() is not None:
                opcoes += ["WAV", "MP3"]
            for r in ["1080p", "720p", "480p", "360p", "240p", "144p"]:
                if yt.streams.filter(res=r).first() is not None:
                    opcoes.append(r)
            if not opcoes:
                set_status("Nenhum formato disponível.", "red")
                return

        # ---------------- COMUM AOS DOIS MODOS ----------------
        set_status("", "gray")
        pPercentage.configure(text="0%")
        abrir_pasta_button.place_forget()

        if my_option is None:
            my_option = customtkinter.CTkOptionMenu(
                master=frame, values=opcoes, command=on_format_change)
            my_option.place(x=662, y=198)
        else:
            my_option.configure(values=opcoes)
        my_option.set(opcoes[0])
        on_format_change(opcoes[0])

        button_download.place(x=662, y=238)

        if barra_progresso is None:
            barra_progresso = customtkinter.CTkProgressBar(master=frame, width=350)
            barra_progresso.place(x=300, y=240)
        barra_progresso.set(0)

    except Exception as e:
        set_status("URL/LINK INVÁLIDO.", "red")
        print(f"Erro: {e}")


def mudar_tema():
    global tema
    global button_sol
    global button_lua

    if tema == "dark":
        customtkinter.set_appearance_mode("light")
        tema = "light"
        button_lua.place_forget()  # Remove the previous button
        button_sol = customtkinter.CTkButton(
            master=frame, text="", command=mudar_tema, width=10, image=img3)
        button_sol.pack(pady=12, padx=10)
        button_sol.place(x=200, y=65)
    else:
        customtkinter.set_appearance_mode("dark")
        tema = "dark"
        button_sol.place_forget()  # Remove the previous button
        button_lua = customtkinter.CTkButton(
            master=frame, text="", command=mudar_tema, width=10, image=img4)
        button_lua.pack(pady=12, padx=10)
        button_lua.place(x=200, y=65)


# ---------------------------------------------------------------------------
# Widgets da interface
# ---------------------------------------------------------------------------
# Label, downloader de videos
label = customtkinter.CTkLabel(
    master=frame, text="Downloader de videos", font=("roboto bold", 24))
label.pack(pady=12, padx=10)
label.place(x=333, y=20)

# box de colocar link
entry = customtkinter.CTkEntry(
    master=frame, placeholder_text="Link do Video:", width=400)
entry.pack(pady=12, padx=10)
entry.place(x=250, y=65)
entry.bind("<Return>", lambda e: buscar())  # Enter dispara a busca

# função de avisar que o download foi feito
label3 = customtkinter.CTkLabel(
    master=frame, text="", font=("roboto bold", 24))
label3.pack(pady=12, padx=10)
label3.place(x=333, y=110)

# Info da playlist (quantidade de vídeos) — escondido por padrão
label_playlist_info = customtkinter.CTkLabel(
    master=frame, text="", font=("roboto bold", 13))

# Buscar
button = customtkinter.CTkButton(master=frame, text="BUSCAR", command=buscar)
button.pack(pady=12, padx=10)
button.place(x=662, y=65)

# Porcentagem de download
pPercentage = customtkinter.CTkLabel(
    master=frame, text="", font=("roboto bold", 15))
pPercentage.pack(pady=12, padx=10)
pPercentage.place(x=268, y=230)

# Menu de bitrate (aparece só no MP3)
bitrate_menu = customtkinter.CTkOptionMenu(
    master=frame, values=["320k", "256k", "128k"], width=90)
bitrate_menu.set("320k")

# Imagem do botão de download
imgdownload = "https://i.ibb.co/bsq5qKj/imagem-2024-11-02-230637827.png"
img2 = carregar_img_url(imgdownload, (25, 25))

# botão pra chamar a função de download
button_download = customtkinter.CTkButton(
    master=frame, text="Download!", command=downloadbttn, image=img2)
button_download.place_forget()

# botão de cancelar (aparece durante o download)
cancel_button = customtkinter.CTkButton(
    master=frame, text="Cancelar", command=cancelar_download, width=90,
    fg_color="#a83232", hover_color="#7d2626")
cancel_button.place_forget()

# botão de abrir pasta (aparece ao concluir)
abrir_pasta_button = customtkinter.CTkButton(
    master=frame, text="Abrir Pasta", command=abrir_pasta, width=120)
abrir_pasta_button.place_forget()

# LUA
img_theme2 = "https://i.ibb.co/WGvwND5/imagem-2024-11-02-232939527.png"
img4 = carregar_img_url(img_theme2, (25, 25))

# SOL
img_theme = "https://i.ibb.co/4pgG4rK/imagem-2024-11-02-232759452.png"
img3 = carregar_img_url(img_theme, (25, 25))

# botão pra mudar tema
button_lua = customtkinter.CTkButton(
    master=frame, text="", command=mudar_tema, width=10, image=img4)
button_lua.pack(pady=12, padx=10)
button_lua.place(x=200, y=65)


# ---------------------------------------------------------------------------
# Verificação do ffmpeg no start
# ---------------------------------------------------------------------------
def _checar_ffmpeg():
    try:
        exe = get_ffmpeg()
        if not exe or not os.path.exists(exe):
            raise FileNotFoundError
    except Exception:
        set_status("ffmpeg não encontrado — reinstale as dependências.", "red")


root.after(300, _checar_ffmpeg)


# fazer loop
root.mainloop()
