import requests
import csv
import time
import os

STEAM_API_KEY = os.environ.get('STEAM_API_KEY')
STEAM_ID = '76561198084603204'

# Get list of owned games
games_url = 'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/'
games_params = {
    'key': STEAM_API_KEY,
    'steamid': STEAM_ID,
    'include_appinfo': True,
    'include_played_free_games': True
}

games_response = requests.get(games_url, params=games_params)
games_data = games_response.json().get('response', {}).get('games', [])

# Output CSV
csv_filename = 'steam_achievements.csv'
with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow(['Game Name', 'Achievement Name', 'Achieved (1=Yes)', 'Unlock Time'])

    for game in games_data:
        appid = game['appid']
        game_name = game.get('name', f'App {appid}')

        achievements_url = 'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/'
        achievements_params = {
            'key': STEAM_API_KEY,
            'steamid': STEAM_ID,
            'appid': appid
        }

        try:
            ach_response = requests.get(achievements_url, params=achievements_params)
            ach_data = ach_response.json()

            achievements = ach_data.get('playerstats', {}).get('achievements', [])
            for ach in achievements:
                writer.writerow([
                    game_name,
                    ach['apiname'],
                    ach['achieved'],
                    ach['unlocktime']
                ])

            print(f"Exported achievements for: {game_name}")

        except Exception as e:
            print(f"Skipped {game_name}: {e}")

        # Optional: Pause to avoid rate limiting
        time.sleep(0.5)

print(f"All achievements saved to {csv_filename}")

