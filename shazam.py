import os
import re
import sys
import asyncio
import tempfile
from datetime import datetime
import logging
import argparse
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse

from pydub import AudioSegment
from shazamio import Shazam
from yt_dlp import YoutubeDL

# Duration of each segment in milliseconds (1 minute)
SEGMENT_LENGTH = 60 * 1000

# Directory for downloaded files
DOWNLOADS_DIR = 'downloads'

ALLOWED_DOMAINS = {
    'youtube.com', 'www.youtube.com', 'm.youtube.com',
    'youtu.be',
    'soundcloud.com', 'www.soundcloud.com', 'm.soundcloud.com',
}


def validate_url(url: str) -> str:
    """Validate URL scheme and domain against allowlist."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError(f"Invalid URL scheme: {parsed.scheme}")
    if parsed.hostname not in ALLOWED_DOMAINS:
        raise ValueError(f"Unsupported domain: {parsed.hostname}. Allowed: YouTube, SoundCloud.")
    return url


def sanitize_url_for_log(url: str) -> str:
    """Strip query parameters from URL before logging."""
    parsed = urlparse(url)
    return urlunparse(parsed._replace(query='', fragment=''))

# Logger setup 
logger = logging.getLogger('shazam_tool')

def setup_logging(debug_mode=False):
    """
    Configure logging based on debug mode.
    When debug mode is enabled, detailed logs are written to both console and file.
    """
    log_level = logging.DEBUG if debug_mode else logging.INFO
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Reset handlers if they exist
    logger.handlers = []
    logger.setLevel(log_level)
    
    # Ensure logs directory exists
    ensure_directory_exists('logs')
    
    # File handler - always logs at DEBUG level to app.log
    file_handler = logging.FileHandler('logs/app.log')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    logger.addHandler(file_handler)
    
    # Console handler - level depends on debug_mode
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    # Use simpler format for console if not in debug mode
    if not debug_mode:
        console_format = '%(message)s'
    else:
        console_format = log_format
        
    console_handler.setFormatter(logging.Formatter(console_format))
    logger.addHandler(console_handler)
    
    if debug_mode:
        logger.debug("Debug mode enabled - detailed logging activated")


def ensure_directory_exists(dir_path: str) -> None:
    """
    Checks if directory exists, creates it if it doesn't.
    """
    os.makedirs(dir_path, exist_ok=True)
    logger.debug(f"Ensured directory exists: {dir_path}")


def remove_files(directory: str, extension: str = ".mp3") -> None:
    """Removes files with the given extension in the directory. Skips symlinks."""
    ensure_directory_exists(directory)
    real_dir = os.path.realpath(directory)
    file_count = 0
    for file_name in os.listdir(real_dir):
        file_path = os.path.join(real_dir, file_name)
        if not file_name.endswith(extension):
            logger.debug(f"Skipping non-{extension} file: {file_name}")
            continue
        if os.path.islink(file_path):
            logger.warning(f"Skipping symlink: {file_path}")
            continue
        if not os.path.isfile(file_path):
            continue
        try:
            os.remove(file_path)
            file_count += 1
        except OSError as e:
            logger.error(f"Error deleting file {file_path}: {e}")
    logger.debug(f"Removed {file_count} files from {directory}")


def write_to_file(data: str, filename: str) -> None:
    """
    Appends text string to specified file if data != 'Not found'.
    """
    if data != "Not found":
        try:
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"{data}\n")
        except OSError as e:
            print(f"Error writing to file {filename}: {e}")


def download_soundcloud(url: str, output_path: str = DOWNLOADS_DIR) -> str | None:
    """
    Download audio from a SoundCloud URL using yt-dlp.
    Returns the track title on success, None on failure.
    """
    ensure_directory_exists(output_path)
    logger.debug(f"Attempting to download from SoundCloud: {sanitize_url_for_log(url)}")
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',
            'restrictfilenames': True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')

        # Verify downloads landed in expected directory
        real_output = os.path.realpath(output_path)
        for f in os.listdir(output_path):
            real_file = os.path.realpath(os.path.join(output_path, f))
            if not real_file.startswith(real_output + os.sep):
                logger.error(f"Security: file {f} resolved outside download directory, removing")
                os.remove(os.path.join(output_path, f))

        logger.info(f"Successfully downloaded from SoundCloud: {title}!")
        return title
    except Exception as e:
        logger.error(f"Failed to download from SoundCloud {sanitize_url_for_log(url)}: {e}")
        return None


def download_youtube(url: str, output_path: str = DOWNLOADS_DIR) -> str | None:
    """
    Download the audio track from a YouTube video and convert to mp3 using yt-dlp.
    Returns the video title on success, None on failure.
    """
    ensure_directory_exists(output_path)
    logger.debug(f"Attempting to download from YouTube: {sanitize_url_for_log(url)}")
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': f'{output_path}/%(title)s.%(ext)s',
            'restrictfilenames': True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'Unknown Title')
            logger.info(f"Successfully downloaded: {title}!")

        # Verify downloads landed in expected directory
        real_output = os.path.realpath(output_path)
        for f in os.listdir(output_path):
            real_file = os.path.realpath(os.path.join(output_path, f))
            if not real_file.startswith(real_output + os.sep):
                logger.error(f"Security: file {f} resolved outside download directory, removing")
                os.remove(os.path.join(output_path, f))

        return title

    except Exception as e:
        logger.error(f"Error downloading from YouTube {sanitize_url_for_log(url)}: {e}")
        return None


def download_from_url(url: str) -> str | None:
    """Determines if URL is YouTube or SoundCloud and calls appropriate download function.
    Returns the video/track title on success, None on failure."""
    logger.info("Starting download...")
    validate_url(url)
    safe_url = sanitize_url_for_log(url)
    logger.debug(f"Processing URL: {safe_url}")
    parsed = urlparse(url)
    hostname = parsed.hostname
    if 'soundcloud.com' in hostname:
        logger.info("SoundCloud URL detected")
        return download_soundcloud(url)
    elif 'youtube.com' in hostname or hostname == 'youtu.be':
        logger.info("YouTube URL detected")
        return download_youtube(url)
    else:
        logger.error("Unsupported URL format. Please provide a YouTube or SoundCloud link.")
        return None


def segment_audio(audio_file: str, output_directory: str = "tmp", num_threads: int = 4) -> None:
    """
    Segments MP3 file into chunks of SEGMENT_LENGTH duration (in milliseconds)
    using parallel processing.
    """
    ensure_directory_exists(output_directory)
    logger.debug(f"Segmenting audio file: {audio_file} with {num_threads} threads")
    try:
        audio = AudioSegment.from_file(audio_file, format="mp3")
        segments = [audio[i:i + SEGMENT_LENGTH] for i in range(0, len(audio), SEGMENT_LENGTH)]
        total_segments = len(segments)
        logger.debug(f"Created {total_segments} segments of {SEGMENT_LENGTH}ms each")

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = []
            for idx, seg in enumerate(segments, start=1):
                segment_file_path = os.path.join(output_directory, f"{idx}.mp3")
                futures.append(
                    executor.submit(seg.export, segment_file_path, format="mp3")
                )

            for future in futures:
                future.result()

    except Exception as e:
        logger.error(f"Failed to segment audio file {audio_file}: {e}")


async def get_name(shazam: Shazam, file_path: str, max_retries: int = 3) -> str:
    """
    Uses Shazam to recognize the song with retry logic and error handling.
    Returns either 'Artist - Track Title' or 'Not found' if it fails.
    """
    logger.debug(f"Attempting to recognize: {file_path} (max retries: {max_retries})")
    for attempt in range(max_retries):
        try:
            logger.debug(f"Recognition attempt {attempt+1}/{max_retries}")
            data = await shazam.recognize(file_path)
            if 'track' not in data:
                logger.debug(f"No track data found in attempt {attempt+1}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                logger.debug("Recognition failed after all attempts")
                return "Not found"

            title = data['track']['title']
            subtitle = data['track']['subtitle']
            result = f"{subtitle} - {title}"
            logger.debug(f"Recognition successful: {result}")
            return result

        except Exception as e:
            logger.debug(f"Error in recognition attempt {attempt+1}: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            logger.debug("Recognition failed after all attempts due to exception")
            return "Not found"


async def _recognize_segments(tmp_dir: str, tmp_files: list, total_segments: int,
                               output_filename: str, unique_tracks: list, seen_tracks: set) -> None:
    shazam = Shazam()
    for idx, file_name in enumerate(tmp_files, start=1):
        segment_path = os.path.join(tmp_dir, file_name)
        try:
            track_name = await get_name(shazam, segment_path)
            progress_str = f"[{idx}/{total_segments}]: {track_name}"
            logger.info(progress_str)
            if track_name != "Not found" and track_name not in seen_tracks:
                seen_tracks.add(track_name)
                unique_tracks.append(track_name)
                write_to_file(track_name, output_filename)
                logger.debug(f"Added new unique track: {track_name}")
        except Exception as e:
            logger.error(f"Error processing segment {file_name}: {e}")
            continue
        # Small delay between requests to avoid rate limiting
        if idx < total_segments:
            await asyncio.sleep(0.5)


def process_audio_file(audio_file: str, output_filename: str, file_index: int, total_files: int) -> None:
    if total_files > 2:
        logger.info(f"\n[{file_index}/{total_files}] Processing file: {audio_file}")
    else:
        logger.info(f"\nProcessing file: {audio_file}")

    logger.debug(f"Starting processing for {audio_file}")
    unique_tracks = []
    seen_tracks = set()
    try:
        with open(output_filename, "a", encoding="utf-8") as f:
            f.write(f"===== {os.path.basename(audio_file)} ======\n")
        logger.debug(f"Created file header for {audio_file}")
    except OSError as e:
        logger.error(f"Error writing header for {audio_file}: {e}")
        return

    with tempfile.TemporaryDirectory(prefix="shazam_") as tmp_dir:
        logger.info("1/4 Segmenting audio file...")
        segment_audio(audio_file, tmp_dir)

        logger.info("2/4 Recognizing segments...")
        tmp_files = sorted(os.listdir(tmp_dir), key=lambda x: int(os.path.splitext(x)[0]))
        total_segments = len(tmp_files)
        logger.debug(f"Found {total_segments} segments to process")

        asyncio.run(_recognize_segments(tmp_dir, tmp_files, total_segments,
                                         output_filename, unique_tracks, seen_tracks))

    # Add an empty line after processing each file
    try:
        with open(output_filename, "a", encoding="utf-8") as f:
            f.write("\n")
    except OSError as e:
        logger.error(f"Error writing empty line for {audio_file}: {e}")

    if unique_tracks:
        logger.info(f"\n--- Tracklist ({len(unique_tracks)} tracks) ---")
        for i, track in enumerate(unique_tracks, 1):
            logger.info(f"  {i}. {track}")
        logger.info("---")

    logger.info(f"Successfully processed file: {audio_file}")
    logger.debug(f"Found {len(unique_tracks)} unique tracks in {audio_file}")


def process_downloads() -> None:
    """
    Process all MP3 files in DOWNLOADS_DIR: recognize each and save results to a new file.
    """
    output_dir = "recognised-lists"
    ensure_directory_exists(output_dir)
    ensure_directory_exists(DOWNLOADS_DIR)

    mp3_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith('.mp3')]
    if not mp3_files:
        logger.warning(f"No MP3 files found in '{DOWNLOADS_DIR}' directory.")
        return

    timestamp = datetime.now().strftime("%d%m%y-%H%M%S")
    output_filename = os.path.join(output_dir, f"songs-{timestamp}.txt")
    logger.debug(f"Created output file: {output_filename}")

    try:
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(f"===== Scan results for {DOWNLOADS_DIR} directory ======\n\n")
    except OSError as e:
        logger.error(f"Error creating output file {output_filename}: {e}")
        return

    total_files = len(mp3_files)
    logger.info(f"Found {total_files} MP3 file(s) to process...")
    logger.info("Starting processing...")

    for idx, file_name in enumerate(mp3_files, start=1):
        full_path = os.path.join(DOWNLOADS_DIR, file_name)
        logger.debug(f"Processing file {idx}/{total_files}: {full_path}")
        process_audio_file(full_path, output_filename, idx, total_files)

    logger.info(f"\nAll files successfully processed!")
    logger.info(f"Results saved to {output_filename}")


def print_usage() -> None:
    """
    Displays script usage instructions.
    """
    print("""
Shazam Tool

Usage: python shazam.py [command] [options]

Commands:
    scan                       Scan downloads directory and recognize all MP3
    download <url>             Download and process audio from YouTube or SoundCloud
    recognize <file_or_url>    Recognize specific audio file or download and recognize from URL

Options:
    --debug                    Enable debug mode with detailed logging

Examples:
    python shazam.py scan
    python shazam.py scan --debug
    python shazam.py download https://www.youtube.com/watch?v=...
    python shazam.py download https://soundcloud.com/... --debug
    python shazam.py recognize path/to/audio.mp3
    python shazam.py recognize https://soundcloud.com/...
    """)


def main() -> None:
    parser = argparse.ArgumentParser(description='Shazam Tool')
    parser.add_argument('command', nargs='?', help='scan, download, or recognize')
    parser.add_argument('url_or_file', nargs='?', help='URL or file path')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    if not args.command:
        print_usage()
        sys.exit(1)

    setup_logging(args.debug)

    command = args.command
    url_or_file = args.url_or_file

    output_dir = "recognised-lists"
    ensure_directory_exists(output_dir)

    timestamp = datetime.now().strftime("%d%m%y-%H%M%S")
    output_filename = os.path.join(output_dir, f"songs-{timestamp}.txt")

    if command == 'download':
        if not url_or_file:
            logger.error("Missing URL. Usage: python shazam.py download <url> [--debug]")
            sys.exit(1)

        title = download_from_url(url_or_file)
        if title:
            safe_title = re.sub(r'[^\w\s\-\(\)]', '', title).strip()
            safe_title = re.sub(r'\s+', '_', safe_title)
            output_filename = os.path.join(output_dir, f"{safe_title}.txt")

        try:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write("===== Download Results ======\n\n")
        except OSError as e:
            logger.error(f"Error creating output file {output_filename}: {e}")
            sys.exit(1)

        # Process downloaded files
        ensure_directory_exists(DOWNLOADS_DIR)
        mp3_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith('.mp3')]
        if not mp3_files:
            logger.warning(f"No MP3 files found in '{DOWNLOADS_DIR}' directory.")
            return

        total_files = len(mp3_files)
        logger.info(f"Found {total_files} MP3 file(s) to process...")

        for idx, file_name in enumerate(mp3_files, start=1):
            full_path = os.path.join(DOWNLOADS_DIR, file_name)
            process_audio_file(full_path, output_filename, idx, total_files)

        logger.info(f"\nAll files successfully processed!")
        logger.info(f"Results saved to {output_filename}")

    elif command in ['scan', 'scan-downloads']:
        logger.info(f"Scanning '{DOWNLOADS_DIR}' directory for MP3 files...")
        process_downloads()
        return

    elif command == 'recognize':
        if not url_or_file:
            logger.error("Missing file path. Usage: python shazam.py recognize <file_path> [--debug]")
            sys.exit(1)

        audio_file = url_or_file

        # Check if the input is a URL
        if audio_file.startswith('http://') or audio_file.startswith('https://'):
            logger.info(f"URL detected: {sanitize_url_for_log(audio_file)}")
            try:
                validate_url(audio_file)
            except ValueError as e:
                logger.error(f"Invalid URL: {e}")
                sys.exit(1)
            title = download_from_url(audio_file)
            if title:
                safe_title = re.sub(r'[^\w\s\-\(\)]', '', title).strip()
                safe_title = re.sub(r'\s+', '_', safe_title)
                output_filename = os.path.join(output_dir, f"{safe_title}.txt")

            mp3_files = [f for f in os.listdir(DOWNLOADS_DIR) if f.endswith('.mp3')]
            if not mp3_files:
                logger.error(f"No MP3 files found in '{DOWNLOADS_DIR}' directory after download.")
                sys.exit(1)
            latest_file = max([os.path.join(DOWNLOADS_DIR, f) for f in mp3_files],
                              key=os.path.getmtime)

            try:
                with open(output_filename, "w", encoding="utf-8") as f:
                    f.write("===== Recognition Results ======\n\n")
            except OSError as e:
                logger.error(f"Error creating output file {output_filename}: {e}")
                sys.exit(1)

            process_audio_file(latest_file, output_filename, 1, 1)
            logger.info(f"\nResults saved to {output_filename}")
            return

        # Handle local file
        if not os.path.exists(audio_file):
            logger.error(f"Error: File '{audio_file}' not found.")
            sys.exit(1)

        try:
            with open(output_filename, "w", encoding="utf-8") as f:
                f.write("===== Recognition Results ======\n\n")
        except OSError as e:
            logger.error(f"Error creating output file {output_filename}: {e}")
            sys.exit(1)

        process_audio_file(audio_file, output_filename, 1, 1)
        logger.info(f"\nResults saved to {output_filename}")
        return

    else:
        logger.error(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()