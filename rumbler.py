# rumblerer - download video or live stream, or entire channels from rumble

# pip install selenium urllib tqdm beautifulsoup requests 

#parser.add_argument("-u", "--url", help="Specify a Rumble video URL to download", default=None)
#parser.add_argument("-f", "--file", help="Specify a file containing a list of Rumble video URLs to download", default=None)
#parser.add_argument("-c", "--channel", help="Specify a user or channel and download a list of all videos", default=None)
#parser.add_argument("-o", "--output", help="Specify an output file name (ignored for channels)", default=None)
#parser.add_argument("-v", "--visible", action="store_true", help="Make the browser visible (for debugging)")

import os
import re
import random
import requests
from bs4 import BeautifulSoup
import shutil
import time
import argparse
import tempfile
import subprocess
import sys
import string
from tqdm import tqdm
from urllib.parse import urljoin, urlparse, unquote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# development testing only. Set to False for production
DevTesting = False

# global variables, don't change these
continue_downloading = True
completed = False
is_browser_visible = False


def sanitize_filename(filename):
    valid_chars = f"-_.() {string.ascii_letters}{string.digits}"
    sanitized = ''.join(c for c in filename if c in valid_chars)
    return sanitized[:240]

def extract_channel_name_from_url(url):
    url = url.rstrip('/')
    return url.split('/')[-1]

def extract_title_from_url(url):
    parsed_url = urlparse(url)
    path_parts = parsed_url.path.split('/')
    if len(path_parts) >= 2:
        title = unquote(path_parts[1]).replace('.html', '').split('-', 1)[-1]
        title = title.replace('.', '-')
        sanitized_title = sanitize_filename(title)
        return sanitized_title
    else:
        return f"unknown-{random.randint(1000, 9999)}"


# download a bunch of videos from a file containing a list of URLs
def download_videos_from_file(file):
    # Check if the file exists
    if not os.path.exists(file):
        print(f"Error: file '{file}' does not exist.")
        exit(0)

    print(f"Downloading videos from file list: {file}")
    # Read in the list of URLs from the file
    with open(file) as f:
        urls = f.readlines()
    urls = [x.strip() for x in urls]

    # Make a directory for the output files and change to it
    output_folder = os.path.join(os.getcwd(), file.split('.')[0])
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    os.chdir(output_folder)

    # Download videos with progress bar
    for url in tqdm(urls, desc="Downloading videos", unit="video"):
        print(f"Downloading video: {url}")
        # Execute this script with the URL as an argument
        os.system(f"python3 {os.path.abspath(__file__)} -u {url}")


# fetch a Rumble channel page, extract the video links and save them to a file
# this list can be edited and used to download the videos later using the -f option
from tqdm import tqdm

def extract_video_links_from_channel(channel_url):
    video_links = []
    page_number = 1
    is_last_page = False

    with tqdm(desc="Extracting video links", unit="page") as pbar:
        while not is_last_page:
            current_url = f"{channel_url}?page={page_number}"
            response = requests.get(current_url)

            if response.status_code != 200:
                is_last_page = True
                continue

            soup = BeautifulSoup(response.text, 'html.parser')

            video_items = soup.find_all('a', class_='video-item--a')
            if not video_items:
                is_last_page = True
                continue

            for video_item in video_items:
                video_path = video_item['href']
                video_links.append(video_path)

            page_number += 1
            pbar.update(1)

    filename = extract_channel_name_from_url(channel_url) + '_videos.txt'

    # Write the list to a file
    with open(filename, 'w') as f:
        for video_link in video_links:
            f.write("https://rumble.com%s\n" % video_link)

    print(f"Video links saved to {filename}")
    exit(0)



## Live Stream Downloading  -- might need some work     
def download_m3u8_file(m3u8_url):
    m3u8_content = requests.get(m3u8_url).text
    with open(os.path.join(temp_dir, 'playlist.m3u8'), 'w') as f:
        f.write(m3u8_content)
    return m3u8_content

def get_ts_files_urls(m3u8_content, base_url):
    ts_files = re.findall(r'(media.+\.ts)', m3u8_content)
    ts_urls = [urljoin(base_url, ts_file) for ts_file in ts_files]
    return ts_urls

def download_ts_files(ts_urls, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    for i, ts_url in enumerate(tqdm(ts_urls, desc="Downloading video segments", unit="segment")):
        output_file = os.path.join(output_folder, f"{i}.ts")

        # Check if the file exists
        if os.path.exists(output_file):
            response = requests.head(ts_url)
            total_size = int(response.headers.get('content-length', 0))

            # Check if the existing file size matches the expected size
            if os.path.getsize(output_file) == total_size:
                print(f"Segment {i} already downloaded, skipping...")
                continue

        response = requests.get(ts_url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        with open(output_file, 'wb') as f:
            with tqdm(total=total_size, desc=f"Segment {i}", unit="B", unit_scale=True) as pbar:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

# Merge the downloaded TS files into a single MP4 file
def merge_ts_files(output_folder, output_file):
    input_files = sorted([f for f in os.listdir(output_folder) if f.endswith('.ts')], key=lambda f: int(os.path.splitext(f)[0]))

    mergefile_path = os.path.join(output_folder, 'mergefiles.txt')
    with open(mergefile_path, 'w') as mergefile:
        for ts_file in input_files:
            mergefile.write(f"file '{os.path.join(output_folder, ts_file)}'\n")

    cmd = f"ffmpeg -f concat -safe 0 -i {mergefile_path} -c copy {output_file}"
    print("Executing: "+cmd)

    result = subprocess.call(cmd, shell=True)
    # os.remove(mergefile_path)

    if result == 0:
        return True
    else:
        return False


## VOD Downloading
def download_mp4(url, output_file, max_attempts=2):
    attempt = 1
    while attempt <= max_attempts:
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))

        if os.path.exists(output_file):
            first_byte = os.path.getsize(output_file)
        else:
            first_byte = 0

        if first_byte >= total_size:
            print(f"File '{output_file}' already downloaded.")
            return True

        headers = {"Range": f"bytes={first_byte}-{total_size}"}
        response = requests.get(url, headers=headers, stream=True)

        with open(output_file, 'ab') as f:
            with tqdm(total=total_size, desc=f"Download:", initial=first_byte, unit="B", unit_scale=True) as pbar:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
                        pbar.update(len(chunk))

        if os.path.getsize(output_file) == total_size:
            #print(f"Downloaded {output_file} successfully.")
            return True

        attempt += 1
        print(f"Attempt {attempt} to resume download...")

    print(f"Failed to download {output_file} after {max_attempts} attempts.")
    return False


## Browser automation to detect either m3u8 or mp4 URL
def get_media_url(url, timeout=40):
    chrome_options = Options()
    if not is_browser_visible:
        chrome_options.add_argument("--headless")

    driver = webdriver.Chrome(options=chrome_options)
    print("Opening browser...")
    driver.get(url)

    print("Clicking on video player...")
    wait = WebDriverWait(driver, 10, poll_frequency=8)
    clickable = wait.until(EC.element_to_be_clickable((By.ID, "videoPlayer")))
    ActionChains(driver).click(clickable).perform()

    m3u8_url = None
    mp4_url = None

    with tqdm(total=timeout, desc="Waiting for media", unit="s") as pbar:
        for _ in range(timeout):
            network_entries = driver.execute_script("return window.performance.getEntries()")
            hls_requests = [entry for entry in network_entries if entry["name"].endswith(".m3u8")]
            mp4_requests = [entry for entry in network_entries if ".mp4" in entry["name"]]

            if hls_requests:
                m3u8_url = hls_requests[0]["name"]
                print(f"\nFound m3u8 file: {m3u8_url}")
                driver.quit()
                return m3u8_url, "m3u8"
            elif mp4_requests:
                mp4_url = mp4_requests[0]["name"]
                print(f"\nFound mp4 file: {mp4_url}")
                driver.quit()
                return mp4_url, "mp4"
            else:
                pbar.update(1)
                time.sleep(1)

    driver.quit()
    return None, None


# take in a file with a list of urls and download them all
def download_from_file_list(file_list):
      #check if the file exists
    if not os.path.exists(file_list):
        print(f"Error: file '{file_list}' does not exist.")
        exit(0)

    print(f"Downloading videos from file list: {file_list}")
    #read in the list of urls from the file
    with open(file_list) as f:
        urls = f.readlines()
    urls = [x.strip() for x in urls]

    # make a directory for the output files and change to it
    output_folder = os.path.join(os.getcwd(), file_list.split('.')[0] )
    script_path = os.path.abspath(__file__)
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    os.chdir(output_folder)

    total_videos = len(urls)
    for index, url in enumerate(urls):
        print(f"Downloading video {index + 1} of {total_videos}: {url}")
        result = subprocess.run([sys.executable, script_path, "-u", url], check=False)
        if result.returncode != 0:
            print(f"Error: Failed to download video from {url}")
            exit(1)

    exit(0)


# Define command line arguments
parser = argparse.ArgumentParser(description="Rumbler - Download Rumble videos")
parser.add_argument("-u", "--url", help="Specify a Rumble video URL to download", default=None)
parser.add_argument("-f", "--file", help="Specify a file containing a list of Rumble video URLs to download", default=None)
parser.add_argument("-c", "--channel", help="Specify a user or channel and download a list of all videos", default=None)
parser.add_argument("-o", "--output", help="Specify an output file name (ignored for channels)", default=None)
parser.add_argument("-v", "--visible", action="store_true", help="Make the browser visible (for debugging)")
args = parser.parse_args()

# if both url and channel are specified, exit with an error
if args.url is not None and args.channel is not None:
    print("Error: you must specify either a video URL or a channel URL, not both.")
    exit(0)

# if channel is specified, download all videos and exit.
if args.channel is not None:
    print(f"Downloading list of videos from channel: {args.channel}")
    extract_video_links_from_channel(args.channel)
    exit(0)
 
if args.file is not None:
    download_from_file_list(args.file)
    exit(0)

# if no url is specified, exit with an error... unless we are in DevTesting mode
if args.url is None:   
   if DevTesting == True:        
        # testing url
        url = "https://rumble.com/val8vm-how-to-use-rumble.html"        
        is_browser_visible = True
   else:
        print("Error: you must supply a Rumble video URL.  eg. python rumbler.py -u https://rumble.com/val8vm-how-to-use-rumble.html")
        exit(0)
else:
    url = args.url

title = extract_title_from_url(url)

# if no output file name is provided, use the title
if args.output is None:
    output_file = f"{title}.mp4"
else:
    output_file = args.output

# open a browser, click on the video player and get the m3u8 (live) or a mp4 file
media_url, media_type = get_media_url(url)

if media_url is None:
    print("\nUnable to find the video URL for either m3u8 or mp4.")
    print("\nThe video may be private, of an unsupported type, or the process might not working anymore.")
    exit(1)

## Media type of mp4 detected
if media_type == "mp4":
    # Easy, download the mp4 to the current directory, and show the progress
    print("\nDownloading mp4 file: " + media_url)
    try:     
        success = download_mp4(media_url, output_file)
    except:
        print("Failed to download the video.")
        success = False
    
    if not success:        
        exit(1)
    
    print(f"Video saved as: {output_file}")
    exit(0)

## Live-stream downloading has a few steps
elif media_type == "m3u8":

    # 1. Download the m3u8 file
    # 2. Get the list of ts files from the m3u8 file
    # 3. Download the ts files
    # 4. Merge the ts files into a mp4 file

    temp_dir = tempfile.mkdtemp(prefix=f"rumble-{title}-")
    print("\nDownloading live-stream m3u8 file: " + media_url)

    try:
        m3u8_content = download_m3u8_file(m3u8_url)
        base_url = media_url.rsplit('/', 1)[0] + '/'
        ts_urls = get_ts_files_urls(m3u8_content, base_url)

        output_folder = os.path.join(temp_dir, 'ts_files')
        print("Downloading video segments...")
        download_ts_files(ts_urls, output_folder)
        print("Merging video segments...")
        
        # use ffmpeg to merge the ts files into a mp4 file     
        completed = merge_ts_files(output_folder, output_file)

    finally:
            if not completed:
                print("Process Interrupted, progress saved in " + temp_dir)
                exit(1)

            else: 
                print("Cleaning up temporary files...")
                shutil.rmtree(temp_dir)
                print(f"Video saved as: {output_file}")                     
                exit(0)

