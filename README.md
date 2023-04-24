# rumblerer
Download rumble live streams, videos, or entire channels:

Will nees some additional modules:

```pip install selenium urllib tqdm beautifulsoup requests```

$ python rumbler.py {options}

"--url", help="Specify a Rumble video URL to download"
"--file", help="Specify a file containing a list of Rumble video URLs to download"
"--channel", help="Specify a user or channel and download a list of all videos"
"--output", help="Specify an output file name (ignored for channels)"
"--visible", help="Make the browser visible (for debugging)"
