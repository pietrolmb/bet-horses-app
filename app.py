import random
import time
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# --- DATABASE TEMPORANEO (In un progetto reale useremmo SQL) ---
users = {"admin": {"wallet": 0, "is_admin": True}} # L'admin parte da qui
current_race = {"status": "waiting", "horses": [], "bets": [], "timer": 0}
race_history = []

# Nomi stile Sisal
NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    num = random.randint(8, 12)
    horses = []
    nomi = random.sample([f"{a} {b}" for a in NOMI_A for b in NOMI_B], num)
    
    for i in range(num):
        # La quota base riflette la probabilità + margine banco
        prob = random.uniform(0.05, 0.25)
        quota_vincente = round(1 / (prob * 1.12), 2) # 12% di vantaggio teorico banco
        horses.append({
            "id": i + 1,
            "nome": nomi[i],
            "quota_v": max(1.20, quota_vincente),
            "quota_p": max(1.10, round(quota_vincente/3, 2)),
            "puntato_totale": 0
        })
    return horses

# Inizializziamo la prima corsa
current_race["horses"] = genera_nuova_corsa()

@app.route('/')
def index():
    return "Sito in costruzione - Il motore Python è attivo!"

# --- LOGICA SOCKET PER REAL-TIME ---
@socketio.on('place_bet')
def handle_bet(data):
    # Qui inseriremo la logica: se qualcuno scommette, parte il timer di 30s
    global current_race
    if current_race["status"] == "waiting":
        current_race["status"] = "countdown"
        current_race["timer"] = 30
        socketio.emit('start_timer', {'time': 30})

if __name__ == '__main__':
    socketio.run(app)
