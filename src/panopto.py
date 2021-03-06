import argparse
import os
import re
from pathlib import Path
from time import sleep

from selenium import webdriver
from selenium.webdriver.common.by import By
from typing import Dict, Tuple

import downloader
import util


def login(tum_username: str, tum_password: str) -> webdriver:
    driver_options = webdriver.ChromeOptions()
    driver_options.add_argument("--headless")
    if os.getenv('NO-SANDBOX') == '1':
        driver_options.add_argument("--no-sandbox")
    driver = webdriver.Chrome(options=driver_options)

    driver.get("https://www.moodle.tum.de/login/index.php")
    driver.find_element(By.LINK_TEXT, "TUM LOGIN").click()

    driver.find_element(By.ID, "username").send_keys(tum_username)
    driver.find_element(By.ID, "password").send_keys(tum_password)
    driver.find_element(By.ID, "btnLogin").click()
    sleep(3)
    if "Username or password was incorrect" in driver.page_source:
        driver.close()
        raise argparse.ArgumentTypeError("Username or password incorrect")

    driver.get("https://tum.cloud.panopto.eu/")
    driver.find_element(By.LINK_TEXT, "Anmelden").click()
    sleep(1)
    return driver


def get_video_links_in_folder(driver: webdriver, folder_id: str) -> [(str, str)]:
    folder_link = f"https://tum.cloud.panopto.eu/Panopto/Pages/Sessions/List.aspx#folderID=%22" \
                  f"{folder_id}" \
                  f"%22&maxResults=250"
    driver.get(folder_link)
    sleep(3)
    if "Failed to load folder" in driver.title:
        print("Folder-ID incorrect: " + folder_id)
        raise Exception

    links_on_page = driver.find_elements_by_xpath(".//a")
    video_urls: [str] = []
    for link in links_on_page:
        link_url = link.get_attribute("href")
        if link_url and "https://tum.cloud.panopto.eu/Panopto/Pages/Viewer.aspx" in link_url:
            video_urls.append(link_url)

    video_playlists: [(str, str)] = []
    for video_url in video_urls:
        video_id = video_url[-36:]
        video_playlists.append(get_m3u8_playlist(driver, video_id))

    video_playlists = util.dedup(video_playlists)
    video_playlists.reverse()

    return video_playlists


def get_m3u8_playlist(driver: webdriver, video_id: str) -> (str, str):
    video_url = "https://tum.cloud.panopto.eu/Panopto/Pages/Embed.aspx?id=" + video_id
    sleep(1)    # else server blocks crawler
    driver.get(video_url)

    prefix = "\"VideoUrl\":\""
    postfix = "/master.m3u8"
    matches = re.search(prefix + '(.+?)' + postfix, driver.page_source) or re.search(prefix + '(.+?)' + ".mp4", driver.page_source)
    if not matches:
        print("Error on URL " + video_url + " - " + driver.title)
        return
    playlist_extracted_url = matches.group(1)
    playlist_url = playlist_extracted_url.replace('\\', '') + postfix
    filename = driver.title.strip()
    return filename, playlist_url


def get_folders(panopto_folders: Dict[str, str], tum_username: str, tum_password: str, queue: [str, Tuple[str, str]]):
    driver = login(tum_username, tum_password)
    for subject_name, folder_id in panopto_folders.items():
        m3u8_playlists = get_video_links_in_folder(driver, folder_id)
        m3u8_playlists = util.rename_duplicates(m3u8_playlists)
        print(f'Found {len(m3u8_playlists)} videos for "{subject_name}"')
        queue.append((subject_name, m3u8_playlists))
    driver.close()
