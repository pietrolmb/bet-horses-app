import random
import time
import eventlet
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

eventlet.monkey_patch()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# DATABASE IN MEMORIA
data = {
    "users": {
        "admin": {"wallet": 1000, "is_admin": True}
    },
    "current_race": {
        "status": "waiting",
        "horses": [],
        "bets": [],
        "timer": 0
    }
}

NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    num = random.randint(8, 12)
    horses = []
    nomi_scelti = random.sample([f"{a} {b}" for a in NOMI_A for b in NOMI_B], num)
    for i in range(num):
        prob = random.uniform(0.05, 0.20)
        quota_v = round(1 / (prob * 1.15), 2)
        horses.append({
            "id": i + 1, "nome": nomi_scelti[i],
            "quota_v": max(1.20, quota_v),
            "colore": f"#{random.randint(100,255):02x}{random.randint(100,255):02x}{random.randint(100,255):02x}"
        })
    return horses

data["current_race"]["horses"] = genera_nuova_corsa()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_page():
    return render_template('admin.html')

@socketio.on('place_bet')
def handle_bet(bet_data):
    race = data["current_race"]
    # Se è la prima scommessa, avvia il countdown
    if race["status"] == "waiting":
        race["status"] = "countdown"
        socketio.start_background_task(run_countdown)
    emit('update_data', data, broadcast=True)

def run_countdown():
    race = data["current_race"]
    race["timer"] = 30
    while race["timer"] > 0:
        socketio.emit('timer_update', race["timer"])
        time.sleep(1)
        race["timer"] -= 1
    start_race()

def start_race():
    race = data["current_race"]
    race["status"] = "racing"
    socketio.emit('race_start')
    
    # Simulazione posizioni (angoli per l'ovale)
    posizioni = {h["id"]: 0 for h in race["horses"]}
    for _ in range(100):
        for h in race["horses"]:
            posizioni[h["id"]] += random.uniform(0.05, 0.15)
        socketio.emit('race_update', posizioni)
        time.sleep(0.1)
    
    # Reset gara
    race["status"] = "waiting"
    race["horses"] = genera_nuova_corsa()
    socketio.emit('update_data', data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
