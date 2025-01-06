# iptv-xstream-download.py

This script is used to download all relevant files from an xtream provider and save them for future archiving or further processing. It retrieves all live TV, series and Movies details, as well as their categories.  It also downloads a full EPG file  

All of the downloads wil lbe saved under a user provided directory (specify with --savedir).  A subdirectory will be created for the server being saved, and under this directory a new subdirectory named after the current date/time will have save all of the data retried.  

By defaul (unless --saveraw specified), the username, password and server name will be masked to ensure these not misused if details shared online.

An option is provided (--prune NUMBER) that will delete the older NUMBER of saved directories for the server.

## Usage

```bash
python3 iptv-xtream-download.py [-h] --server SERVER --user USER --pw PW --savedir SAVEDIR [--agent AGENT] [--debug] [--retries RETRIES] [--saveraw]
                               [--format] [--prune PRUNE]

Program to identify channels from iptv providers

optional arguments:
  -h, --help         show this help message and exit
  --server SERVER    The URL of the Xtream server.
  --user USER        The username for authentication.
  --pw PW            The password for authentication.
  --savedir SAVEDIR  The directory to save the retrieved files.
  --agent AGENT      User-Agent for accessing the server.
  --debug            Enable debug mode.
  --retries RETRIES  Number of retries (default: 3).
  --saveraw          Keep username/password in user_info.json.
  --format           Save data in reformatted form.
  --prune PRUNE      Keep only the most recent <prune> versions.
```

## Examples

1. Download from test.iptv.xyz server and save all files to the SavedFiles directory
```bash
python iptv-xtream-download.py --server test.iptv.xyz --user user1 --pw secret --savedir SavedFiles
```

2. Download from server.cdngold.me server, save all files to the SavedFiles directory and just keep the 5 most recent deownloads
```bash
python iptv-xtream-download.py --server server.cdngold.me --user user1 --pw secret --savedir SavedFiles --prune 5
```