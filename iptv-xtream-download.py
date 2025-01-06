import os
import sys
import argparse
import requests
import time
import json
from pathlib import Path
from xml.dom.minidom import parseString
from datetime import datetime

DEBUG_MODE = False  # Default: Debugging is off

def debug_log(message):
    """
    Logs a debug message if debugging is enabled.
    """
    if DEBUG_MODE:
        print(f"[DEBUG] {message}")

def save_data_to_file(url, save_path, headers, retries, sleep_time, debug, format_data):
    """
    Downloads data from the given URL and saves it to a file.
    """
    attempt = 0
    while attempt <= retries:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            debug_log(f"Response from server ({url}): {response.text[:500]}")  # Print first 500 characters

            if format_data:
                try:
                    data = response.json()
                    with open(save_path, "w") as f:
                        json.dump(data, f, indent=4)
                    if debug:
                        print(f"Formatted JSON data successfully saved to {save_path}")
                except ValueError:
                    with open(save_path, "wb") as f:
                        f.write(response.content)
                    if debug:
                        print(f"Non-JSON data saved as is to {save_path}")
            else:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                if debug:
                    print(f"Data saved as is to {save_path}")

            return True
        except requests.RequestException as e:
            if debug:
                print(f"Attempt {attempt + 1} failed for URL: {url}, Error: {e}")
            attempt += 1
            if attempt > retries:
                print(f"Failed to retrieve data from {url} after {retries} retries.")
            else:
                time.sleep(sleep_time)
    return False

def save_epg_data(url, save_path, headers, retries, sleep_time, debug, format_data):
    """
    Fetches EPG data from the given URL, formats it (if required), and saves it as an XML file.
    """
    attempt = 0
    while attempt <= retries:
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            debug_log(f"Response from server ({url}): {response.text[:500]}")  # Print first 500 characters

            if debug:
                print(f"Retrieving EPG data from {url}...")

            if not response.content.strip():
                print(f"No EPG data returned from {url}.")
                return False

            if format_data:
                try:
                    dom = parseString(response.content)
                    pretty_xml_as_string = dom.toprettyxml(indent="  ")

                    with open(save_path.with_suffix(".xml"), "w", encoding="utf-8") as f:
                        f.write(pretty_xml_as_string)

                    if debug:
                        print(f"Formatted EPG data successfully saved to {save_path}.xml")
                except Exception as e:
                    if debug:
                        print(f"Error formatting XML data: {e}")
                    return False
            else:
                with open(save_path.with_suffix(".xml"), "wb") as f:
                    f.write(response.content)
                if debug:
                    print(f"Raw EPG data saved to {save_path}.xml")

            return True
        except requests.RequestException as e:
            if debug:
                print(f"Attempt {attempt + 1} failed for EPG URL: {url}, Error: {e}")
            attempt += 1
            if attempt > retries:
                print(f"Failed to retrieve EPG data from {url} after {retries} retries.")
            else:
                time.sleep(sleep_time)
    return False

def ensure_http_prefix(server):
    """
    Ensures the server URL starts with http:// or https://.
    """
    if not server.startswith(("http://", "https://")):
        return f"http://{server}"
    return server

def anonymize_user_info(file_path, debug):
    """
    Reads the user_info.json file and anonymizes sensitive fields.
    """
    try:
        with open(file_path, "r") as f:
            data = json.load(f)
        if "user_info" in data:
            data["user_info"]["username"] = "XXXXX"
            data["user_info"]["password"] = "YYYYY"
        if "server_info" in data:
            url = data["server_info"]["url"]
            if "." in url:
                parts = url.split(".")
                parts[0] = "UUUUU"
                data["server_info"]["url"] = ".".join(parts)
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        if debug:
            print(f"User info successfully anonymized in {file_path}")
    except Exception as e:
        print(f"Failed to anonymize user info: {e}")

def prune_old_versions(server_dir, prune_count, debug):
    """
    Keeps the most recent `prune_count` directories and deletes older ones.
    """
    subdirs = [d for d in server_dir.iterdir() if d.is_dir()]
    subdirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)  # Sort by modification time (most recent first)

    if len(subdirs) > prune_count:
        print(f"Found {len(subdirs)} subdirectories under {server_dir}. Pruning to : {prune_count}")
        to_delete = subdirs[prune_count:]
        for old_dir in to_delete:
            if debug:
                print(f"Deleting old directory: {old_dir}")
            for root, dirs, files in os.walk(old_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(old_dir)
    else:
        print(f"Nothing pruned as only {len(subdirs)} versions available")

def main():
    global DEBUG_MODE

    parser = argparse.ArgumentParser(description="Program to identify channels from iptv providers")
    parser.add_argument("--server", required=True, help="The URL of the Xtream server.")
    parser.add_argument("--user", required=True, help="The username for authentication.")
    parser.add_argument("--pw", required=True, help="The password for authentication.")
    parser.add_argument("--savedir", required=True, help="The directory to save the retrieved files.")
    parser.add_argument("--agent", default="Mozilla/5.0", help="User-Agent for accessing the server.")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode.")  # Debug flag
    parser.add_argument("--retries", type=int, default=3, help="Number of retries (default: 3).")
    parser.add_argument("--saveraw", action="store_true", help="Keep username/password in user_info.json.")
    parser.add_argument("--format", action="store_false", help="Save data in reformatted form.")
    parser.add_argument("--prune", type=int, help="Keep only the most recent <prune> versions.")

    args = parser.parse_args()

    # Print the date and time when the program is run
    run_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n\niptv-xtream-download - Running for server {args.server} on {run_time}\n")

    # Enable debug mode if the --debug flag is present
    DEBUG_MODE = args.debug
    debug_log("Debug mode enabled")

    server_url = ensure_http_prefix(args.server)
    save_dir = Path(args.savedir)
    if not save_dir.exists():
        print(f"Error: '{save_dir}' does not exist. Please create it.")
        sys.exit(1)

    server_name = args.server.split("://")[-1].replace("/", "_")
    server_dir = save_dir / server_name
    server_dir.mkdir(parents=True, exist_ok=True)

    if args.prune and args.prune > 0:
        prune_old_versions(server_dir, args.prune, args.debug)

    timestamp_dir = server_dir / datetime.now().strftime("%y-%m-%d--%H-%M")
    timestamp_dir.mkdir(parents=True)

    headers = {"User-Agent": args.agent}
    endpoints = {
        "user_info": f"{server_url}/player_api.php?username={args.user}&password={args.pw}",
        "live_categories": f"{server_url}/player_api.php?username={args.user}&password={args.pw}&action=get_live_categories",
        "live_streams": f"{server_url}/player_api.php?username={args.user}&password={args.pw}&action=get_live_streams",
        "vod_categories": f"{server_url}/player_api.php?username={args.user}&password={args.pw}&action=get_vod_categories",
        "vod_streams": f"{server_url}/player_api.php?username={args.user}&password={args.pw}&action=get_vod_streams",
        "series_categories": f"{server_url}/player_api.php?username={args.user}&password={args.pw}&action=get_series_categories",
        "series_streams": f"{server_url}/player_api.php?username={args.user}&password={args.pw}&action=get_series",
    }

    epg_url = f"{server_url}/xmltv.php?username={args.user}&password={args.pw}"
    epg_save_path = timestamp_dir / "epg_data"

    for key, url in endpoints.items():
        file_path = timestamp_dir / f"{key}.json"
        print(f"Retrieving {key}")
        save_data_to_file(url, file_path, headers, args.retries, 30, args.debug, args.format)
        if key == "user_info" and not args.saveraw:
            anonymize_user_info(file_path, args.debug)

    print(f"Retrieving EPG data")
    save_epg_data(epg_url, epg_save_path, headers, args.retries, 30, args.debug, args.format)

    print(f"\nData saved in '{timestamp_dir}'\n\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProgram interrupted. Exiting.")
        sys.exit(0)