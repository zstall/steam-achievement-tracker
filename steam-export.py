import requests
import csv

# Replace with your Steam API key and SteamID64
STEAM_API_KEY = '549094D7625ABA943DA0EC5CA4BA5D88'
STEAM_ID = '76561198084603204'

# API endpoint to get owned games
url = 'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/'

params = {
    'key': STEAM_API_KEY,
    'steamid': STEAM_ID,
    'include_appinfo': True,
    'include_played_free_games': True
}

response = requests.get(url, params=params)
data = response.json()

# Check if games are returned
if 'response' not in data or 'games' not in data['response']:
    print("No games found or error retrieving data.")
    exit()

games = data['response']['games']

# Write to CSV
csv_filename = 'steam_library.csv'
with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['App ID', 'Name', 'Playtime (Hours)'])

    for game in games:
        appid = game['appid']
        name = game['name']
        playtime_hours = round(game['playtime_forever'] / 60, 2)
        writer.writerow([appid, name, playtime_hours])

print(f"Exported {len(games)} games to {csv_filename}")

