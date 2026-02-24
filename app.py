import random
import time
import eventlet
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

eventlet.monkey_patch()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# DATABASE CON PASSWORD
data = {
    "users": {}, 
    "admin_stats": {"totale_incassato": 0, "totale_pagato": 0, "bilancio": 0},
    "current_race": {"status": "waiting", "horses": [], "bets": [], "timer": 0}
}

NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    num = random.randint(8, 12)
    horses = []
    nomi = random.sample([f"{a} {b}" for a in NOMI_A for b in NOMI_B], num)
    for i in range(num):
        prob = random.uniform(0.05, 0.20)
        quota_v = round(1 / (prob * 1.15), 2)
        horses.append({
            "id": i + 1, "nome": nomi[i], "quota_v": max(1.20, quota_v),
            "colore": f"#{random.randint(100,255):02x}{random.randint(100,255):02x}{random.randint(100,255):02x}"
        })
    return horses

data["current_race"]["horses"] = genera_nuova_corsa()

@app.route('/')
def index(): return render_template('index.html')

@app.route('/admin')
def admin(): return render_template('admin.html')

@socketio.on('request_update')
def send_update(): emit('update_data', data)

@socketio.on('admin_update_wallet')
def handle_wallet(req):
    user = req['user']
    password = req.get('password', '1234') # Default se non messa
    amount = req['amount']
    if user not in data["users"]:
        data["users"][user] = {"wallet": 0, "password": password}
    data["users"][user]["wallet"] += amount
    socketio.emit('update_data', data)

@socketio.on('tentativo_login')
def login_check(req):
    user = req.get('user')
    pwd = req.get('password')
    if user in data["users"] and data["users"][user]["password"] == pwd:
        emit('login_success', {"user": user, "wallet": data["users"][user]["wallet"]})
    else:
        emit('login_error', "Credenziali errate o utente inesistente")

@socketio.on('place_bet')
def handle_bet(bet_data):
    race = data["current_race"]
    user = bet_data['user']
    if user in data["users"] and data["users"][user]["wallet"] >= bet_data['amount'] and race["status"] == "waiting":
        data["users"][user]["wallet"] -= bet_data['amount']
        data["admin_stats"]["totale_incassato"] += bet_data['amount']
        data["admin_stats"]["bilancio"] += bet_data['amount']
        quota = next(h["quota_v"] for h in race["horses"] if h["id"] == bet_data['horse_id'])
        race["bets"].append({"user": user, "horse_id": bet_data['horse_id'], "amount": bet_data['amount'], "quota": quota})
        if len(race["bets"]) == 1:
            race["status"] = "countdown"
            socketio.start_background_task(run_countdown)
        socketio.emit('update_data', data)

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
    posizioni = {h["id"]: 0 for h in race["horses"]}
    for _ in range(150):
        for h in race["horses"]: posizioni[h["id"]] += random.uniform(0.02, 0.1)
        socketio.emit('race_update', posizioni)
        time.sleep(0.1)
    race["status"] = "waiting"
    race["horses"] = genera_nuova_corsa()
    race["bets"] = []
    socketio.emit('update_data', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
