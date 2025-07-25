import requests
import csv
import time
from datetime import datetime

# 🔧 Configuration
STEAM_API_KEY = '549094D7625ABA943DA0EC5CA4BA5D88'
STEAM_ID = '76561198084603204'
OUTPUT_FILE = 'steam_library_with_achievements.csv'

# 🔍 Get owned games
print("Fetching owned games...")
games_url = 'https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/'
games_params = {
    'key': STEAM_API_KEY,
    'steamid': STEAM_ID,
    'include_appinfo': True,
    'include_played_free_games': True
}
games_response = requests.get(games_url, params=games_params)
if games_response.status_code != 200:
    print(f"⚠️  Failed to fetch games! Status: {games_response.status_code}")
    print(f"Response text: {games_response.text}")
    exit(1)

try:
    games_data = games_response.json().get('response', {}).get('games', [])
except Exception as e:
    print(f"❌ JSON parse error: {e}")
    print(f"Raw response: {games_response.text}")
    exit(1)

# 📝 Write to CSV
with open(OUTPUT_FILE, mode='w', newline='', encoding='utf-8') as file:
    writer = csv.writer(file)
    writer.writerow([
        'App ID', 'Game Name', 'Playtime (Hours)',
        'Achievement API Name', 'Achievement Display Name', 'Description',
        'Achieved (1=Yes)', 'Unlock Time (UTC)'
    ])

    for game in games_data:
        appid = game['appid']
        name = game.get('name', f'App {appid}')
        playtime_hours = round(game['playtime_forever'] / 60, 2)

        # 🏆 Get achievements
        achievements_url = 'https://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v1/'
        achievements_params = {
            'key': STEAM_API_KEY,
            'steamid': STEAM_ID,
            'appid': appid
        }

        schema_url = 'https://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/'
        schema_params = {
            'key': STEAM_API_KEY,
            'appid': appid
        }

        try:
            ach_response = requests.get(achievements_url, params=achievements_params)
            schema_response = requests.get(schema_url, params=schema_params)

            ach_data = ach_response.json().get('playerstats', {})
            ach_list = ach_data.get('achievements', [])
            schema_data = schema_response.json().get('game', {}).get('availableGameStats', {}).get('achievements', [])

            # Map schema info for descriptions
            schema_map = {a['name']: a for a in schema_data}

            if not ach_list:
                writer.writerow([appid, name, playtime_hours, '', '', '', '', ''])
                print(f"[No Achievements] {name}")
                continue

            for ach in ach_list:
                api_name = ach['apiname']
                achieved = ach['achieved']
                unlocktime = ach['unlocktime']
                unlocktime_str = datetime.utcfromtimestamp(unlocktime).isoformat() if unlocktime > 0 else ''

                schema = schema_map.get(api_name, {})
                display_name = schema.get('displayName', '')
                description = schema.get('description', '')

                writer.writerow([
                    appid, name, playtime_hours,
                    api_name, display_name, description,
                    achieved, unlocktime_str
                ])

            print(f"[Exported] {name} - {len(ach_list)} achievements")

        except Exception as e:
            print(f"[Skipped] {name} due to error: {e}")
            writer.writerow([appid, name, playtime_hours, 'Error retrieving achievements', '', '', '', ''])

        # Optional: delay to avoid rate limiting
        time.sleep(0.5)

print(f"\n✅ Done! Exported data to {OUTPUT_FILE}")

