import requests
e = requests.get(f"http://ddragon.leagueoflegends.com/cdn/10.16.1/data/en_US/runesReforged.json")
errorcode = e.status_code
with open(f"runesReforged.json", "wb") as file:
    file.write(e.content)
"""
for i in range(1000):
    r = requests.get(f"https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/champion-icons/{i}.png")
    if r.status_code == errorcode:
        continue
    with open(f"{i}.png", "wb") as file:
        file.write(r.content)

import requests
import urllib

# Set the URL of the directory you want to download
url = "https://raw.communitydragon.org/latest/game/"

# Send an HTTP request to the server
response = requests.get(url, stream=True)

# Get the content of the response and split it into lines
lines = response.content.decode().splitlines()

# Loop through each line and download the files
for line in lines:
    filename = line.split('"')[1] # Get the filename from the line
    file_url = url + filename # Create the full URL of the file
    urllib.request.urlretrieve(file_url, filename) # Download the file
    """