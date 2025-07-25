import tkinter as tk
from tkinter import ttk, filedialog
import csv
from collections import defaultdict
import os

# ---- Helper functions ----
def load_achievements(csv_path):
    games = defaultdict(lambda: {'achievements': [], 'unlocked': 0})

    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            game = row['Game Name']
            achieved = int(row['Achieved (1=Yes)'])
            achievement = {
                'api_name': row['Achievement API Name'],
                'display_name': row['Achievement Display Name'],
                'description': row['Description'],
                'achieved': achieved,
                'unlock_time': row['Unlock Time (UTC)']
            }
            games[game]['achievements'].append(achievement)
            if achieved:
                games[game]['unlocked'] += 1

    for game, data in games.items():
        total = len(data['achievements'])
        unlocked = data['unlocked']
        data['progress'] = round((unlocked / total) * 100, 2) if total else 0

    return dict(games)

# ---- UI Class ----
class SteamAchievementTracker(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Steam Achievement Tracker")
        self.geometry("800x600")
        self.games = {}
        self.active_game = None

        self.create_widgets()

    def create_widgets(self):
        # Top frame for file loading
        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=10, pady=5)
        tk.Button(top, text="Load CSV", command=self.load_csv).pack(side=tk.LEFT)

        # Game selector
        self.game_listbox = tk.Listbox(self)
        self.game_listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0), pady=5)
        self.game_listbox.bind("<<ListboxSelect>>", self.on_game_select)

        # Main view area
        right_frame = tk.Frame(self)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.progress_label = tk.Label(right_frame, text="Progress: N/A")
        self.progress_label.pack(anchor='w')

        self.ach_list = tk.Listbox(right_frame)
        self.ach_list.pack(fill=tk.BOTH, expand=True)

    def load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if not path:
            return

        self.games = load_achievements(path)
        self.game_listbox.delete(0, tk.END)

        for game in sorted(self.games):
            self.game_listbox.insert(tk.END, game)

    def on_game_select(self, event):
        selection = self.game_listbox.curselection()
        if not selection:
            return

        game_name = self.game_listbox.get(selection[0])
        game_data = self.games[game_name]

        self.progress_label.config(text=f"Progress: {game_data['progress']}% ({game_data['unlocked']}/{len(game_data['achievements'])})")
        self.ach_list.delete(0, tk.END)

        for ach in game_data['achievements']:
            status = "✅" if ach['achieved'] else "❌"
            line = f"{status} {ach['display_name']}"
            if ach['description']:
                line += f" - {ach['description']}"
            self.ach_list.insert(tk.END, line)


if __name__ == '__main__':
    app = SteamAchievementTracker()
    app.mainloop()

