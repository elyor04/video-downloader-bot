import shutil
import os
from yt_dlp import YoutubeDL


def fetch_formats(url, download_type):
    formats = {"video": [], "audio": []}

    try:
        with YoutubeDL({"cookiefile": "data/cookies.txt"}) as ydl:
            info = ydl.extract_info(url, download=False)
            formats["media_id"] = info.get("id", None)

            for f in info.get("formats", []):
                if f["audio_ext"] != "none":
                    formats["audio"].append(f["ext"])
                elif f["video_ext"] != "none":
                    formats["video"].append((f["height"], f["ext"]))

            formats["audio"] = sorted(set(formats["audio"]), reverse=True)
            formats["video"] = [
                f"{f[0]}p {f[1]}" for f in sorted(set(formats["video"]), reverse=True)
            ]

            if not formats[download_type]:
                formats["message"] = "No format found."

    except Exception as e:
        formats["message"] = f"Error occurred: {e}"

    return formats


def download_media(
    url,
    download_type,
    desired_format,
    available_formats,
    output_path,
    file_name,
    convert_to,
):
    ffmpeg_location = shutil.which("ffmpeg")
    if not ffmpeg_location:
        return "FFmpeg is not installed. Please install FFmpeg to proceed."

    ydl_opts = {
        "format": get_format(download_type, desired_format, available_formats),
        "outtmpl": os.path.join(output_path, f"{file_name}.%(ext)s"),
        "ffmpeg_location": ffmpeg_location,
        "cookiefile": "data/cookies.txt",
    }

    if convert_to != "original":
        ydl_opts["postprocessors"] = [get_postprocessor(download_type, convert_to)]

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return None

    except Exception as e:
        return f"Error occurred: {e}"


def get_format(download_type, desired_format, available_formats):
    if download_type == "audio":
        return f"bestaudio[ext={desired_format}]"

    q, f = desired_format.split()
    if not available_formats["audio"]:
        return f"best[height={q[:-1]}][ext={f}]"

    if f in available_formats["audio"]:
        audio = f
    elif "m4a" in available_formats["audio"]:
        audio = "m4a"
    else:
        audio = None

    if not audio:
        return f"bestvideo[height={q[:-1]}][ext={f}]+bestaudio"
    return f"bestvideo[height={q[:-1]}][ext={f}]+bestaudio[ext={audio}]/best"


def get_postprocessor(download_type, convert_to):
    if download_type == "audio":
        return {
            "key": "FFmpegExtractAudio",
            "preferredcodec": convert_to,
        }
    return {
        "key": "FFmpegVideoConvertor",
        "preferedformat": convert_to,
    }
