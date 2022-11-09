import os
import logging
import subprocess
import requests

import ffmpy

from pathlib import Path

from moviepy.editor import *

import music_tag
from telegram import ReplyKeyboardMarkup
from telegram.ext import CallbackContext

from models.admin import Admin
from models.user import User
from localization import keys

logger = logging.getLogger()

def translate_key_to(key: str, destination_lang: str) -> str:
    """Find the specified key in the `keys` dictionary and returns the corresponding
    value for the given language

    **Keyword arguments:**
     - file_path (str) -- The file path of the file to delete

    **Returns:**
     - The value of the requested key in the dictionary
    """
    if key not in keys:
        raise KeyError("Specified key doesn't exist")

    return keys[key][destination_lang]


def delete_file(file_path: str) -> None:
    """Deletes a file from the filesystem. Simply ignores the files that don't exist.

    **Keyword arguments:**
     - file_path (str) -- The file path of the file to delete
    """
    if os.path.exists(file_path):
        os.remove(file_path)


def generate_music_info(tag_editor_context: dict) -> str:
    """Generate the details of the music based on the values in `tag_editor_context`
    dictionary

    **Keyword arguments:**
     - tag_editor_context (dict) -- The context object of the user

    **Returns:**
     `str`
    """
    ctx = tag_editor_context

    return (
        f"*🗣 Artist:* {ctx['artist'] if ctx['artist'] else '-'}\n"
        f"*🎵 Title:* {ctx['title'] if ctx['title'] else '-'}\n"
        f"*🎼 Album:* {ctx['album'] if ctx['album'] else '-'}\n"
        f"*🎹 Genre:* {ctx['genre'] if ctx['genre'] else '-'}\n"
        f"*📅 Year:* {ctx['year'] if ctx['year'] else '-'}\n"
        f"*💿 Disk Number:* {ctx['disknumber'] if ctx['disknumber'] else '-'}\n"
        f"*▶️ Track Number:* {ctx['tracknumber'] if ctx['tracknumber'] else '-'}\n"
        "{}\n"
    )


def increment_usage_counter_for_user(user_id: int) -> int:
    """Increment the `number_of_files_sent` column of user with the specified `user_id`.

    **Keyword arguments:**
     - user_id (int) -- The user id of the user

    **Returns:**
     The new value for `user.number_of_files_sent`
    """
    user = User.where('user_id', '=', user_id).first()

    if user:
        user.number_of_files_sent = user.number_of_files_sent + 1
        user.push()

        return user.number_of_files_sent

    raise LookupError(f'User with id {user_id} not found.')

def reset_user_data_context(context: CallbackContext) -> None:
    user_data = context.user_data
    language = user_data['language'] if ('language' in user_data) else 'en'

    if 'voice_path' in user_data:
        delete_file(user_data['voice_path'])
    if 'voice_art_path' in user_data:
        delete_file(user_data['voice_art_path'])
    if 'new_voice_art_path' in user_data:
        delete_file(user_data['new_voice_art_path'])
    if 'music_path' in user_data:
        delete_file(user_data['music_path'])
    if 'art_path' in user_data:
        delete_file(user_data['art_path'])
    if 'new_art_path' in user_data:
        delete_file(user_data['new_art_path'])
    if 'video_path' in user_data:
        delete_file(user_data['video_path'])
    if 'video_art_path' in user_data:
        delete_file(user_data['video_art_path'])
    if 'new_video_art_path' in user_data:
        delete_file(user_data['new_video_art_path'])
    if 'gif' in user_data:
        delete_file(user_data['gif'])

    new_user_data = {
        'convert_video_to_gif': False,
        'convert_video_to_circle': False,
        'convert_audio_to_voice': False,
        'edit_tag_music': False,
        'download_from_link': False,
        'voice_path': '',
        'voice_art_path': '',
        'new_voice_art_path': '',
        'video_path': '',
        'video_art_path': '',
        'new_video_art_path': '',
        'gif': '',
        'video_message_id': '',
        'video_duration': '',
        'tag_editor': {},
        'music_path': '',
        'music_duration': 0,
        'art_path': '',
        'new_art_path': '',
        'current_active_module': '',
        'music_message_id': 0,
        'language': language,
    }
    context.user_data.update(new_user_data)

def create_user_directory(user_id: int) -> str:
    """Create a directory for a user with a given id.

    **Keyword arguments:**
     - user_id (int) -- The user id of the user

    **Returns:**
     The path of the created directory
    """
    user_download_dir = f"downloads/{user_id}"

    try:
        Path(user_download_dir).mkdir(parents=True, exist_ok=True)
    except (OSError, FileNotFoundError, BaseException) as error:
        raise Exception(f"Can't create directory for user_id: {user_id}") from error

    return user_download_dir

def convert_seconds_to_human_readable_form(seconds: int) -> str:
    """Convert seconds to human readable time format, e.g. 02:30

    **Keyword arguments:**
     - seconds (int) -- Seconds to convert

    **Returns:**
     Formatted string
    """
    if seconds <= 0:
        return "00:00"

    minutes = int(seconds / 60)
    remainder = seconds % 60

    minutes_formatted = str(minutes) if minutes >= 10 else "0" + str(minutes)
    seconds_formatted = str(remainder) if remainder >= 10 else "0" + str(remainder)

    return f"{minutes_formatted}:{seconds_formatted}"

def download_file(user_id: int, file_to_download, file_type: str, context: CallbackContext) -> str:
    """Download a file using convenience methods of "python-telegram-bot"

    **Keyword arguments:**
     - user_id (int) -- The user's id
     - file_to_download (*) -- The file object to download
     - file_type (str) -- The type of the file, either 'photo' or 'audio'
     - context (CallbackContext) -- The context object of the user

    **Returns:**
     The path of the downloaded file
    """
    user_download_dir = f"downloads/{user_id}"
    file_id = ''
    file_extension = ''

    if file_type == 'audio':
        file_id = context.bot.get_file(file_to_download.file_id)
        file_name = file_to_download.file_name
        file_extension = file_name.split(".")[-1]
    elif file_type == 'photo':
        file_id = context.bot.get_file(file_to_download.file_id)
        file_extension = 'jpg'
    elif file_type == 'video':
        file_id = context.bot.get_file(file_to_download.file_id)
        file_name = file_to_download.file_name
        file_extension = file_name.split(".")[-1]
    elif file_type == 'voice':
        file_id = context.bot.get_file(file_to_download.file_id)
        mime_type = file_to_download.mime_type
        file_extension = mime_type.split("/")[-1]

        # voice_path = voice_path.split("/")[-1]

        # mime_type = voice_path.split(".")[-1]
        # voice = voice_path.split(".")[0]

        # # logger.error(voice_path)
        # new_voice = ffmpegcommand(file_id.file_id, file_extension)
        # os.system(new_voice)

        # logger.error(new_voice)
        # logger.error(file_id.file_id)

    file_download_path = f"{user_download_dir}/{file_id.file_id}.{file_extension}"

    try:
        file_id.download(f"{user_download_dir}/{file_id.file_id}.{file_extension}")
    except ValueError as error:
        raise Exception(f"Couldn't download the file with file_id: {file_id}") from error

    return file_download_path

def generate_back_button_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `back_button_keyboard`


    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [translate_key_to('BTN_BACK', language)],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )

def generate_start_over_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `start_over_keyboard`


    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [translate_key_to('BTN_NEW_FILE', language)],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )


def generate_module_selector_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `module_selector_keyboard`

    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [
                    translate_key_to('BTN_TAG_EDITOR', language),
                    translate_key_to('BTN_MUSIC_TO_VOICE_CONVERTER', language)
                ],
                [
                    translate_key_to('BTN_MUSIC_CUTTER', language),
                    translate_key_to('BTN_BITRATE_CHANGER', language)
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )

def generate_module_selector_video_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `module_selector_video_keyboard`


    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [
                    translate_key_to('BTN_CONVERT_VIDEO_TO_CIRCLE', language),
                    translate_key_to('BTN_CONVERT_VIDEO_TO_GIF', language),
                ],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )

def generate_module_selector_voice_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `module_selector_video_keyboard`


    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [
                    translate_key_to('BTN_CONVERT_VOICE_TO_AUDIO', language),
                ],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
    )

def generate_tag_editor_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `tag_editor_keyboard`


    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [
                    translate_key_to('BTN_ARTIST', language),
                    translate_key_to('BTN_TITLE', language),
                    translate_key_to('BTN_ALBUM', language)
                ],
                [
                    translate_key_to('BTN_GENRE', language),
                    translate_key_to('BTN_YEAR', language),
                    translate_key_to('BTN_ALBUM_ART', language)
                ],
                [
                    translate_key_to('BTN_DISK_NUMBER', language),
                    translate_key_to('BTN_TRACK_NUMBER', language)
                ],
                [
                    translate_key_to('BTN_BACK', language)
                ]
            ],
            resize_keyboard=True,
        )
    )

def generate_tag_editor_video_keyboard(language: str) -> ReplyKeyboardMarkup:
    """Create an return an instance of `tag_editor_keyboard`


    **Keyword arguments:**
     - language (str) -- The desired language to generate labels

    **Returns:**
     ReplyKeyboardMarkup instance
    """
    return (
        ReplyKeyboardMarkup(
            [
                [
                    translate_key_to('BTN_CONVERT_VIDEO_TO_CIRCLE', language),
                    translate_key_to('BTN_CONVERT_VIDEO_TO_GIF', language),
                ],
            ],
            resize_keyboard=True,
        )
    )

def save_tags_to_file(file: str, tags: dict, new_art_path: str) -> str:
    """Create an return an instance of `tag_editor_keyboard`


    **Keyword arguments:**
     - file (str) -- The path of the file
     - tags (str) -- The dictionary containing the tags and their values
     - new_art_path (str) -- The new album art to set

    **Returns:**
     The path of the file
    """
    music = music_tag.load_file(file)

    try:
        if new_art_path:
            with open(new_art_path, 'rb') as art:
                music['artwork'] = art.read()
    except OSError as error:
        raise Exception("Couldn't set hashtags") from error

    music['artist'] = tags['artist'] if tags['artist'] else ''
    music['title'] = tags['title'] if tags['title'] else ''
    music['album'] = tags['album'] if tags['album'] else ''
    music['genre'] = tags['genre'] if tags['genre'] else ''
    music['year'] = int(tags['year']) if tags['year'] else 0
    music['disknumber'] = int(tags['disknumber']) if tags['disknumber'] else 0
    music['tracknumber'] = int(tags['tracknumber']) if tags['tracknumber'] else 0

    music.save()

    return file

def ffmpegcommand(voice, mime_type):
    # 1) wav to mp3
    # ffmpeg -i audio.wav -acodec libmp3lame audio.mp3

    # 2) ogg to mp3
    # ffmpeg -i audio.ogg -acodec libmp3lame audio.mp3

    # 3) ac3 to mp3
    # ffmpeg -i audio.ac3 -acodec libmp3lame audio.mp3

    # 4) aac to mp3
    # ffmpeg -i audio.aac -acodec libmp3lame audio.mp3

    new_mime_type = "mp3"
    # cmd = f'ffmpeg -i "{voice}.{mime_type}" -acodec libmp3lame "{voice}.{new_mime_type}"'
        # cmd = f'ffmpeg -i "{inputt}" -c copy "{output}"'
    cmd = f'ffmpeg -i "{voice}.{mime_type}" "{voice}.{new_mime_type}"'

    # ffmpeg -i input.mp3 -acodec libopus output.ogg -y
    # import os
    # import requests
    # import subprocess

    # token = YYYYYYY
    # chat_id = XXXXXXXX

    # upload_audio_url = "https://api.telegram.org/bot%s/sendAudio?chat_id=%s" % (token, chat_id)
    # audio_path_wav = '/Users/me/some-file.wav'

    # # Convert the file from wav to ogg
    # filename = os.path.splitext(audio_path_wav)[0]
    # audio_path_ogg = filename + '.ogg'
    # subprocess.run(["ffmpeg", '-i', audio_path_wav, '-acodec', 'libopus', audio_path_ogg, '-y'])

    # with open(audio_path_ogg, 'rb') as f:
    #     data = f.read()

    # # An arbitrary .ogg filename has to be present so that the spectogram is shown
    # file = {'audio': ('Message.ogg', data)}
    # result = requests.post(upload_audio_url, files=file)
    # https://stackoverflow.com/questions/44615991/how-convert-ogg-file-to-telegram-voice-format
    # print("Command to be Executed is")
    # print(cmd)
    return cmd

def myffmpegcommand(voice_path, user_data):
    voice = voice_path.split(".")[0]
    new_mime_type = ".mp3"
    new_voice = voice + new_mime_type
    # subprocess.run(["ffmpeg", '-i', voice_path, '-acodec', 'libopus', new_voice, '-y'])
    # subprocess.run(["ffmpeg -i {voice_path} -map 0:a -acodec libmp3lame {new_voice}"])
    
    subprocess.run(["ffmpeg", "-n", "-i", voice_path, "-acodec", "libmp3lame", "-ab", "128k", new_voice])
    user_data['new_voice_art_path'] = new_voice
    # delete_file(user_data['voice_path'])
    # logging.info(user_data['new_voice_art_path'])
    # return
    # codec = "libmp3lame"
    # mp3_filename = filename + ".mp3"

    # command = [self.FFMPEG_BIN,
    #             "-n",
    #             "-i", path,
    #             "-acodec", codec,
    #             "-ab", "128k",
    #             mp3_filename
    #             ]

    # old_voice = voice_path.split("/")[-1]
    # voice_path = voice_path.split("/")[0]
    # logger.error(voice_path)

    # mime_type = voice_path.split(".")[-1]
    # voice = voice_path.split(".")[0]



    # with open(new_voice, 'rb') as f:
    #     data = f.read()

    # logging.error(new_voice)

    # An arbitrary .ogg filename has to be present so that the spectogram is shown
    # file = {'audio': ('Message.ogg', data)}
    # result = requests.post(upload_audio_url, files=file)
    # return result

def video_to_gif(video_path, user_data):
    video = video_path.split(".")[0]
    new_mime_type = ".gif"
    gif = video + new_mime_type

    # logging.error(new_video)
    # subprocess.run(["ffmpeg", "-i", video_path, "-pix_fmt", "rgb24", gif])
    # subprocess.run(["ffmpeg", "-i", video_path, "-movflags", "faststart", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", gif])
    subprocess.run(["ffmpeg", "-ss", "00:00:00.000", "-i", video_path, "-pix_fmt", "rgb24", "-r", "10", "-s", "320x240", "-t", "00:00:10.000", gif])
    user_data['gif'] = gif


    # subprocess(["ffmpeg -f gif -i " {video_path outfile.mp4}])
    # subprocess.run(["ffmpeg", "-i", video_path, "-c:v", "libvpx", "-crf", "12", "-b:v", "500K", gif])
    # subprocess.run(["ffmpeg", "-f", "gif", "-i", video_path, gif])
    # subprocess.run(["ffmpeg", "-i", video_path, "-movflags", "faststart", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", gif])
    # subprocess.run(["ffmpeg", "-ss", "00:01:30", "-t", "5", "-i", video_path, "-filter_complex", "[0:v] fps=10,scale=720:-1 [new];[new][1:v] paletteuse", gif])
    # subprocess.run(["ffmpeg", "-stream_loop 5", "-i", video_path, "-y;ffmpeg", "-i" loop.gif -pix_fmt yuv420p -vf "scale=trunc(iw/2)*2:trunc(ih/2)*2" loop.mp4 -y"])
    # try:
    #     with open(video_path, 'rb') as video_file:
    #         clip = (VideoFileClip(video_file)
    #         .subclip((1,22.65),(1,23.2))
    #         .resize(0.3))
    #         clip.write_gif(new_video)

    # except (BaseException) as error:
    #     logger.exception("Telegram error: %s", error)

    # subprocess.run(["ffmpeg -ss 30 -t 3 -i", video_path, "-vf", "fps=10,scale=320:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse", "-loop 0", new_video])
    # subprocess.run(["ffmpeg -i", video_path, "-vf scale=320:-1 -r 10 -f image2pipe -vcodec ppm - | convert -delay 10 -loop 0 - gif:- | convert -layers Optimize - ", new_video])

    # subprocess.run([video_path, new_video])