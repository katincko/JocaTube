import customtkinter
from tkinter import filedialog
from pytubefix import YouTube , Playlist
from pytubefix.cli import on_progress
import urllib.request
from PIL import Image , ImageDraw , ImageOps
import os , threading , subprocess , re
from io import BytesIO
import imageio_ffmpeg as ffmpeg


#TODO:
#fazer download de playlists com o bagaço de objetos. obj_video pra cada um na playlist e pa.
#corrigir bugs: se nao selecionar diretorio nao faz nada
#dizer oque ocorreu no erro.

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

root.after(201, lambda: root.iconbitmap(icon_path))


# Frame da janela
frame = customtkinter.CTkFrame(master=root)
frame.pack(pady=20, padx=60, fill="both", expand=True)




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
        button_sol.place(
            x=200,
            y=65
        )
    else:
        customtkinter.set_appearance_mode("dark")
        tema = "dark"
        button_sol.place_forget()  # Remove the previous button
        button_lua = customtkinter.CTkButton(
            master=frame, text="", command=mudar_tema, width=10, image=img4)
        button_lua.pack(pady=12, padx=10)
        button_lua.place(
            x=200,
            y=65
        )

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

# função de download

def downloadbttn():
    def start_download():
        #TODO: CASO O NOME DO ARQUIVO SEJA IGUAL A OUTRO, ELE ADCIONA (1) NO FINAL DO NOME DO ARQUIVO E ASSIM POR DIANTE.
        # baixar video
        try:

            #for video in playlist.videos:
                #start_download()

            if my_option.get() != "MP3":
                # especificando o video and audio streams
                video_stream = yt.streams.filter(res=my_option.get()).first()
                audio_stream = yt.streams.filter(only_audio=True).first()


                #Download the streams to temporary files
                video_file = os.path.join(diretorio_download, "video_temp.mp4")
                audio_file = os.path.join(diretorio_download, "audio_temp.mp3")
                video_stream.download(output_path=diretorio_download, filename="video_temp.mp4")
                audio_stream.download(output_path=diretorio_download, filename="audio_temp.mp3")

                label3.configure(text="Renderizando Video...", text_color="yellow")
                label3.place(x=333, y=110)

                # Combine the video and audio streams using FFMPEG
                
                output_file = os.path.join(diretorio_download, f"{sanitize_filename(yt.title)}.mp4")
                command = [
                    ffmpeg.get_ffmpeg_exe(),  # Obtém o caminho do ffmpeg embutido
                    '-i', video_file,  # Arquivo de vídeo
                    '-i', audio_file,  # Arquivo de áudio
                    '-c:v', 'copy',  # Copiar o vídeo sem re-encode
                    '-c:a', 'aac',  # Usar o codec de áudio AAC
                    '-strict', 'experimental',  # Para permitir o uso de codecs experimentais se necessário
                    '-loglevel', 'quiet', # Suprime a saída do terminal
                    output_file  # Arquivo de saída
                ]
                subprocess.run(command, check=True)
                # Delete the temporary files
                os.remove(video_file)
                os.remove(audio_file)

                
            
            elif my_option.get() == "MP3":
                mp3_stream = yt.streams.filter(only_audio=True).first()
                mp3_stream.download(output_path=diretorio_download, filename=f"{sanitize_filename(yt.title)}.mp3")



            label3.configure(text="DOWNLOAD CONCLUÍDO!", text_color="green")
            label3.place(x=333, y=110)

        except:
            label3.configure(
                text="Ocorreu um erro, tente novamente", text_color="red")



    # Choose o diretorio q o video will be downloaded
    diretorio_download = filedialog.askdirectory()
    if diretorio_download == "":
        label3.configure(text="Diretório inválido.", text_color="red")

    else:
        # thread
        thread = threading.Thread(target=start_download)
        thread.start()



def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)
# funções de download abaixo.

# Widgets globais
label_titulo = None
label_thumbnail = None
my_option = None
barra_progresso = None

def buscar():
    global button_download, my_option, yt, label_titulo, label_thumbnail , barra_progresso

    def on_progress(stream, chunk, bytes_remaining):
        # Atualiza a barra de progresso e porcentagem
        totalsize = stream.filesize
        bytes_downloaded = totalsize - bytes_remaining
        percentage_completion = bytes_downloaded / totalsize * 100
        per = str(int(percentage_completion)) + "%"
        pPercentage.configure(text=per)
        barra_progresso.set(float(percentage_completion) / 100)
        pPercentage.configure(text=per)
        if pPercentage.cget("text") == "100%":
            pPercentage.place(x=261)

    try:
        # Verifica se a URL é válida
        yt = YouTube(entry.get(), on_progress_callback=on_progress)

        # Atualiza o título do vídeo
        video_title = yt.title
        MAX_TITLE_LENGTH = 35
        if len(video_title) > MAX_TITLE_LENGTH:
            video_title = video_title[:MAX_TITLE_LENGTH] + "..."

        if label_titulo is None:
            label_titulo = customtkinter.CTkLabel(
                master=frame, text=video_title, font=("roboto bold", 16)
            )
            label_titulo.place(x=275, y=200)
        else:
            label_titulo.configure(text=video_title)

        # Atualiza a thumbnail do vídeo
        url_image = yt.thumbnail_url
        response = urllib.request.urlopen(url_image)
        image_data = response.read()

        #Arredonda imagem
        thumbnail = round_image(Image.open(BytesIO(image_data)), radius=20).convert("RGBA")
        rounded_thumbnail = round_image(thumbnail, radius=50)

        img = customtkinter.CTkImage(
            light_image=rounded_thumbnail,
            dark_image=rounded_thumbnail,
            size=(220, 180),
        )



        if label_thumbnail is None:
            label_thumbnail = customtkinter.CTkLabel(master=frame, text="", image=img)
            label_thumbnail.place(x=40, y=130)
        else:
            label_thumbnail.configure(image=img)

        #Atualiza label3
        label3.configure(text="")
        label3.place(x=333, y=110)
        pPercentage.configure(text="0%")


        # Atualiza as opções de resolução
        resolucoes = {
            "MP3": yt.streams.filter(only_audio=True).first(),
            "1080p": yt.streams.filter(res="1080p").first(),
            "720p": yt.streams.filter(res="720p").first(),
            "480p": yt.streams.filter(res="480p").first(),
            "360p": yt.streams.filter(res="360p").first(),
            "240p": yt.streams.filter(res="240p").first(),
            "144p": yt.streams.filter(res="144p").first(),
        }

        opcoes = [
            resolucao if stream is not None else f"{resolucao} não disponível."
            for resolucao, stream in resolucoes.items()
        ]

        if my_option is None:
            my_option = customtkinter.CTkOptionMenu(master=frame, values=opcoes)
            my_option.place(x=662, y=198)
        else:
            my_option.configure(values=opcoes)
            my_option.set(opcoes[0])  # Define a primeira opção como padrão

        # Faz o botão de download aparecer
        button_download.place(x=662, y=238)

        # Adicione a barra de progresso ao layout
        barra_progresso = customtkinter.CTkProgressBar(master=frame, width=350)
        barra_progresso.place(x=300, y=240)
        barra_progresso.set(0)  # Inicializa a barra de progresso em 0

    except Exception as e:
        label3.configure(text="URL/LINK INVÁLIDO.", text_color="red")
        label3.place(x=333, y=110)
        print(f"Erro: {e}")

# Label, downloader de videos
label = customtkinter.CTkLabel(
    master=frame, text="Downloader de videos", font=("roboto bold", 24))
label.pack(pady=12, padx=10)
label.place(x = 333 , y= 20)

# box de colocar link
entry = customtkinter.CTkEntry(
    master=frame, placeholder_text="Link do Video:", width=400)
entry.pack(pady=12, padx=10)
entry.place(x = 250 , y = 65)

# função de avisar que o download foi feito
label3 = customtkinter.CTkLabel(
    master=frame, text="", font=("roboto bold", 24))
label3.pack(pady=12, padx=10)
label3.place(x = 333 , y = 110)

# Buscar
button = customtkinter.CTkButton(master=frame, text="BUSCAR", command=buscar)
button.pack(pady=12, padx=10)
button.place(
    x=662,
    y=65
)



# Porcentagem de download
pPercentage = customtkinter.CTkLabel(
    master=frame, text="", font=("roboto bold", 15))
pPercentage.pack(pady=12, padx=10)
pPercentage.place(
    x=268,
    y=230
)


# Imagem do botão de download
imgdownload = "https://i.ibb.co/bsq5qKj/imagem-2024-11-02-230637827.png"

response_download = urllib.request.urlopen(imgdownload)
image_data_download = response_download.read()

img2 = customtkinter.CTkImage(light_image=Image.open(BytesIO(
    image_data_download)), dark_image=Image.open(BytesIO(image_data_download)), size=(25, 25))


# botão pra chamar a função de download
button_download = customtkinter.CTkButton(
    master=frame, text="Download!", command=downloadbttn, image=img2)
button_download.place_forget()


# LUA
img_theme2 = "https://i.ibb.co/WGvwND5/imagem-2024-11-02-232939527.png"

response_theme2 = urllib.request.urlopen(img_theme2)
image_data_theme2 = response_theme2.read()

img4 = customtkinter.CTkImage(light_image=Image.open(BytesIO(
    image_data_theme2)), dark_image=Image.open(BytesIO(image_data_theme2)), size=(25, 25))


# SOL
img_theme = "https://i.ibb.co/4pgG4rK/imagem-2024-11-02-232759452.png"

response_theme = urllib.request.urlopen(img_theme)
image_data_theme = response_theme.read()

img3 = customtkinter.CTkImage(light_image=Image.open(BytesIO(
    image_data_theme)), dark_image=Image.open(BytesIO(image_data_theme)), size=(25, 25))

# botão pra mudar tema
# Declare and initialize the button_lua variable before using it
button_lua = customtkinter.CTkButton(
    master=frame, text="", command=mudar_tema, width=10, image=img4)
button_lua.pack(pady=12, padx=10)
button_lua.place(
    x=200,
    y=65
)


# fazer loop
root.mainloop()
