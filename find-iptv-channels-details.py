import argparse
import csv
import json
import logging
import os
import signal
import subprocess
import sys
from datetime import datetime

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def debug_log(message):
    """
    Log a debug message if debugging is enabled.
    """
    if DEBUG_MODE:
        print(f"[DEBUG] {message}")


class CacheManager:
    """
    Manage caching of data to and from JSON files.
    """

    CACHE_FILE_PATTERN = "cache-{server}-{data_type}.json"

    @staticmethod
    def load_cache(server: str, data_type: str) -> dict | None:
        """
        Load data from the cache file if it exists and is up-to-date.
        """
        logging.info(f"Loading cache for {data_type} on server {server}")
        cache_file = CacheManager.CACHE_FILE_PATTERN.format(
            server=server, data_type=data_type
        )
        if os.path.exists(cache_file):
            file_date = datetime.fromtimestamp(os.path.getmtime(cache_file)).date()
            if file_date == datetime.today().date():
                try:
                    with open(cache_file, "r") as file:
                        return json.load(file)
                except (OSError, IOError, json.JSONDecodeError) as e:
                    logging.error(f"Error reading cache file {cache_file}: {e}")
        return None

    @staticmethod
    def save_cache(server: str, data_type: str, data: dict) -> None:
        """
        Save data to the cache file.
        """
        logging.info(f"Saving cache for {data_type} on server {server}")
        cache_file = CacheManager.CACHE_FILE_PATTERN.format(
            server=server, data_type=data_type
        )
        try:
            with open(cache_file, "w") as file:
                json.dump(data, file)
        except (OSError, IOError) as e:
            logging.error(f"Error saving cache file {cache_file}: {e}")


class IPTVDownloader:
    """
    Handle downloading data from the Xtream IPTV server.
    """

    @staticmethod
    def download_data(
        server: str,
        user: str,
        password: str,
        endpoint: str,
        additional_params: dict = None,
    ) -> dict:
        """
        Download data from the Xtream IPTV server.
        """
        logging.info(f"Downloading data from {server}, endpoint: {endpoint}")
        url = f"http://{server}/player_api.php"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
        }
        params = {"username": user, "password": password, "action": endpoint}
        if additional_params:
            params.update(additional_params)
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            logging.debug(f"Response from server ({endpoint}): {response.text[:500]}")
            return response.json()
        except requests.RequestException as e:
            logging.error(f"Failed to fetch {endpoint} data: {e}")
            sys.exit(1)


def check_epg(server, user, password, stream_id):
    """Check EPG data for a specific channel."""
    debug_log(f"Checking EPG for stream ID {stream_id}")
    epg_data = IPTVDownloader.download_data(
        server, user, password, "get_simple_data_table", {"stream_id": stream_id}
    )

    if isinstance(epg_data, dict) and epg_data.get("epg_listings"):
        return len(epg_data["epg_listings"])  # Return the count of EPG entries

    elif isinstance(epg_data, list):
        debug_log(f"Unexpected list response for EPG data: {epg_data}")
        return len(epg_data)  # Return the length of the list

    else:
        debug_log(f"Unexpected EPG response type: {type(epg_data)}")
        return 0  # No EPG data available


def filter_data(live_categories, live_streams, group, channel):
    """Filter the live streams based on group and channel arguments."""
    filtered_streams = []
    group = group.lower() if group else None
    channel = channel.lower() if channel else None

    for stream in live_streams:
        # Filter by group if specified
        if group:
            matching_categories = [
                cat for cat in live_categories if group in cat["category_name"].lower()
            ]
            if not any(
                cat["category_id"] == stream["category_id"]
                for cat in matching_categories
            ):
                continue
        # Filter by channel if specified
        if channel and channel not in stream["name"].lower():
            continue
        # Add the stream to the filtered list
        filtered_streams.append(stream)

    return filtered_streams


class StreamChecker:
    """
    Handle checking stream details using ffprobe.
    """

    @staticmethod
    def check_ffprobe() -> None:
        """
        Verify if the ffprobe command is available on the system.
        """
        try:
            subprocess.run(
                ["ffprobe", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            logging.info("ffprobe is installed and reachable.")
        except FileNotFoundError:
            logging.error(
                "ffprobe is not installed or not found in the system PATH. Please install ffprobe before running this program."
            )
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            logging.error(f"ffprobe check failed with error: {e}")
            sys.exit(1)

    @staticmethod
    def check_channel(url: str) -> dict:
        """
        Retrieve stream details using ffprobe.
        """
        logging.debug(f"Checking channel: {url}")
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_name,width,height,avg_frame_rate,channels,sample_rate",
                    "-of",
                    "json",
                    url,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            output = json.loads(result.stdout)

            if "streams" in output and len(output["streams"]) > 0:
                # Get first element in json structure output
                video_stream = output["streams"][0]
                audio_stream = (
                    output["streams"][1] if len(output["streams"]) > 1 else None
                )

                codec_name = video_stream.get("codec_name")
                width = video_stream.get("width")
                height = video_stream.get("height")
                avg_frame_rate = video_stream.get("avg_frame_rate")

                if "/" in avg_frame_rate:
                    num, denom = map(int, avg_frame_rate.split("/"))
                    frame_rate = round(num / denom) if denom != 0 else "?"
                else:
                    frame_rate = avg_frame_rate

                if audio_stream:
                    audio_codec = audio_stream.get("codec_name")
                    channels = audio_stream.get("channels")
                    sample_rate = audio_stream.get("sample_rate")
                else:
                    audio_codec = "?"
                    channels = "?"
                    sample_rate = "?"

                return {
                    "status": "working",
                    "video_codec": codec_name,
                    "width": width,
                    "height": height,
                    "frame_rate": frame_rate,
                    "audio_codec": audio_codec,
                    "channels": channels,
                    "sample_rate": sample_rate,
                }
            else:
                logging.warning(f"No streams found in ffprobe output for URL: {url}")
                logging.warning(f"{output}")
                return {"status": "not working"}
        except Exception as e:
            logging.error(f"Error in check_channel: {e}")
            return {"status": "error", "error_message": str(e)}


def save_to_csv(file_name, data, fieldnames):
    """
    Save data to a CSV file, ensuring all fields are enclosed in double quotes.

    :param file_name: The name of the CSV file to save.
    :param data: A list of dictionaries containing the data to write.
    :param fieldnames: A list of field names for the CSV header.
    """
    try:
        with open(file_name, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
            writer.writeheader()
            writer.writerows(data)
        print(f"Output saved to {file_name}")
    except Exception as e:
        print(f"Error saving to CSV: {e}")


def handle_sigint(signal, frame):
    """Handle Ctrl+C gracefully."""
    print("\nProgram interrupted by user. Exiting...")
    sys.exit(0)


class IPTVTool:
    """
    Main class to orchestrate the IPTV tool workflow.
    """

    def __init__(self, args):
        self.server = args.server
        self.user = args.user
        self.password = args.pw
        self.nocache = args.nocache
        self.channel = args.channel
        self.category = args.category
        self.debug = args.debug
        self.epgcheck = args.epgcheck
        self.check = args.check
        self.save = args.save

        if self.debug:
            logging.getLogger().setLevel(logging.DEBUG)
            logging.debug("Debug mode enabled")

    def run(self):
        # Check ffprobe if --check is enabled
        if self.check:
            StreamChecker.check_ffprobe()

        # Check cache or download data
        live_categories = (
            CacheManager.load_cache(self.server, "live_categories")
            if not self.nocache
            else None
        )
        live_streams = (
            CacheManager.load_cache(self.server, "live_streams")
            if not self.nocache
            else None
        )

        if not live_categories or not live_streams:
            live_categories = IPTVDownloader.download_data(
                self.server, self.user, self.password, "get_live_categories"
            )
            live_streams = IPTVDownloader.download_data(
                self.server, self.user, self.password, "get_live_streams"
            )
            CacheManager.save_cache(self.server, "live_categories", live_categories)
            CacheManager.save_cache(self.server, "live_streams", live_streams)

        # Filter data
        filtered_streams = self.filter_data(live_categories, live_streams)

        # Prepare CSV data and headers
        csv_data = []
        fieldnames = [
            "Stream ID",
            "Name",
            "Category",
            "Archive",
            "EPG",
            "Video Codec",
            "Resolution",
            "Frame Rate",
            "Audio Codec",
            "Channels",
            "Sample Rate",
        ]

        # Print and collect results
        self.print_header()
        category_map = {
            cat["category_id"]: cat["category_name"] for cat in live_categories
        }
        for stream in filtered_streams:
            category_name = category_map.get(stream["category_id"], "Unknown")
            epg_count = (
                IPTVDownloader.download_data(
                    self.server,
                    self.user,
                    self.password,
                    "get_simple_data_table",
                    {"stream_id": stream["stream_id"]},
                )
                if self.epgcheck
                else ""
            )
            stream_url = f"http://{self.server}/{self.user}/{self.password}/{stream['stream_id']}"
            stream_info = (
                StreamChecker.check_channel(stream_url)
                if self.check
                else {
                    "video_codec": "",
                    "width": "",
                    "height": "",
                    "frame_rate": "",
                    "audio_codec": "",
                    "channels": "",
                    "sample_rate": "",
                }
            )
            resolution = (
                f"{stream_info.get('width', 'N/A')}x{stream_info.get('height', 'N/A')}"
                if self.check
                else "N/A"
            )

            # Print to console
            self.print_stream(stream, category_name, epg_count, stream_info, resolution)

            # Collect data for CSV
            csv_data.append(
                {
                    "Stream ID": stream["stream_id"],
                    "Name": stream["name"][:60],
                    "Category": category_name[:40],
                    "Archive": stream.get("tv_archive_duration", "N/A"),
                    "EPG": epg_count,
                    "Video Codec": stream_info.get("video_codec", "N/A"),
                    "Resolution": resolution,
                    "Frame Rate": stream_info.get("frame_rate", "N/A"),
                    "Audio Codec": stream_info.get("audio_codec", "N/A"),
                    "Channels": stream_info.get("channels", "N/A"),
                    "Sample Rate": stream_info.get("sample_rate", "N/A"),
                }
            )

        # Write to CSV if --save is provided
        if self.save:
            self.save_to_csv(csv_data, fieldnames)

    def filter_data(self, live_categories, live_streams):
        """Filter the live streams based on group and channel arguments."""
        filtered_streams = []
        group = self.category.lower() if self.category else None
        channel = self.channel.lower() if self.channel else None

        for stream in live_streams:
            # Filter by group if specified
            if group:
                matching_categories = [
                    cat
                    for cat in live_categories
                    if group in cat["category_name"].lower()
                ]
                if not any(
                    cat["category_id"] == stream["category_id"]
                    for cat in matching_categories
                ):
                    continue
            # Filter by channel if specified
            if channel and channel not in stream["name"].lower():
                continue
            # Add the stream to the filtered list
            filtered_streams.append(stream)

        return filtered_streams

    @staticmethod
    def print_header():
        """Print the table header."""
        print(
            f"{'ID':<10}{'Name':<60} {'Category':<40}{'Archive':<8}{'EPG':<5}{'Video Codec':<12}{'Resolution':<15}{'Frame':<10}{'Audio Codec':<12}{'Channels':<10}{'Sample Rate':<12}"
        )
        print("=" * 180)

    @staticmethod
    def print_stream(stream, category_name, epg_count, stream_info, resolution):
        """Print a single stream's details."""
        print(
            f"{stream['stream_id']:<10}{stream['name'][:60]:<60} {category_name[:40]:<40}{stream.get('tv_archive_duration', 'N/A'):<8}{epg_count:<5}{stream_info.get('video_codec', 'N/A'):<12}{resolution:<15}{stream_info.get('frame_rate', 'N/A'):<10}{stream_info.get('audio_codec', 'N/A'):<12}{stream_info.get('channels', 'N/A'):<10}{stream_info.get('sample_rate', 'N/A'):<12}"
        )

    def save_to_csv(self, data, fieldnames):
        """Save data to a CSV file."""
        try:
            with open(self.save, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file, fieldnames=fieldnames, quoting=csv.QUOTE_ALL
                )
                writer.writeheader()
                writer.writerows(data)
            logging.info(f"Output saved to {self.save}")
        except Exception as e:
            logging.error(f"Error saving to CSV: {e}")


def main():
    global DEBUG_MODE

    # Set up the signal handler for Ctrl+C
    signal.signal(signal.SIGINT, handle_sigint)

    parser = argparse.ArgumentParser(description="Xtream IPTV Downloader and Filter")
    parser.add_argument(
        "--server", required=True, help="The Xtream server to connect to."
    )
    parser.add_argument("--user", required=True, help="The username to use.")
    parser.add_argument("--pw", required=True, help="The password to use.")
    parser.add_argument(
        "--nocache", action="store_true", help="Force download and ignore cache."
    )
    parser.add_argument("--channel", help="Filter by channel name.")
    parser.add_argument("--category", help="Filter by category name.")
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode."
    )  # Debug flag
    parser.add_argument(
        "--epgcheck",
        action="store_true",
        help="Check if channels provide EPG data and count entries.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check stream resolution and frame rate using ffprobe.",
    )
    parser.add_argument(
        "--save", help="Save the output to a CSV file. Provide the file name."
    )
    args = parser.parse_args()

    # Print the date and time when the program is run
    masked_server = f"{'.'.join(['xxxxx'] + args.server.split('.')[1:])}"
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(
        f"\n\nfind-iptv-channels-details - Running for server {masked_server} on {run_time}\n"
    )

    # Enable debug mode if the --debug flag is present
    DEBUG_MODE = args.debug
    debug_log(
        "Debug mode enabled"
    )  # Will only print if debug mode is set.  else ignored

    # Run the IPTV tool
    tool = IPTVTool(args)
    tool.run()

    print("\n\n")


if __name__ == "__main__":
    main()
