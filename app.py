import random
import time
import eventlet
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# Installazione necessaria per i server real-time
eventlet.monkey_patch()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# --- DATABASE IN MEMORIA ---
# Admin gestisce tutto. Gli utenti avranno un codice univoco.
data = {
    "users": {
        "admin": {"wallet": 0, "is_admin": True},
        "player1": {"wallet": 100, "is_admin": False} # Esempio utente
    },
    "current_race": {
        "status": "waiting",
        "horses": [],
        "bets": [],
        "timer": 0,
        "total_pool": 0
    },
    "settings": {"max_bet": 100, "auto_start": True}
}

NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    num = random.randint(8, 12)
    horses = []
    nomi_completi = [f"{a} {b}" for a in NOMI_A for b in NOMI_B]
    nomi_scelti = random.sample(nomi_completi, num)
    
    for i in range(num):
        # Probabilità di base (il banco ha sempre un margine del 12-15%)
        prob = random.uniform(0.05, 0.20)
        quota_v = round(1 / (prob * 1.15), 2)
        horses.append({
            "id": i + 1,
            "nome": nomi_scelti[i],
            "quota_v": max(1.20, quota_v),
            "quota_p": max(1.10, round(quota_v/3.5, 2)),
            "puntato": 0,
            "colore": f"#{random.randint(100,255):02x}{random.randint(100,255):02x}{random.randint(100,255):02x}"
        })
    return horses

data["current_race"]["horses"] = genera_nuova_corsa()

# --- ROTTE ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_panel():
    return "Pannello Admin (In fase di creazione...)"

# --- LOGICA DI GIOCO (Real-time) ---

@socketio.on('place_bet')
def handle_bet(bet_data):
    # bet_data: {user: 'player1', amount: 10, horse_id: 1, type: 'vincente'}
    global data
    race = data["current_race"]
    user = data["users"].get(bet_data['user'])

    if user and user['wallet'] >= bet_data['amount']:
        # Sottrai soldi
        user['wallet'] -= bet_data['amount']
        
        # Aggiungi scommessa
        race['bets'].append(bet_data)
        race['total_pool'] += bet_data['amount']
        
        # Ricalcolo quote dinamico (Ponderazione rischio)
        for h in race['horses']:
            if h['id'] == bet_data['horse_id']:
                h['puntato'] += bet_data['amount']
                # Se puntano troppo, la quota scende drasticamente
                riduzione = (h['puntato'] / (race['total_pool'] + 1)) * 0.5
                h['quota_v'] = max(1.05, round(h['quota_v'] * (1 - riduzione), 2))

        # Se è la prima scommessa, parte il timer
        if race['status'] == "waiting":
            race['status'] = "countdown"
            socketio.start_background_task(start_countdown)
        
        emit('update_data', data, broadcast=True)

def start_countdown():
    race = data["current_race"]
    race['timer'] = 30
    while race['timer'] > 0:
        time.sleep(1)
        race['timer'] -= 1
        socketio.emit('timer_update', race['timer'])
    
    start_race()

def start_race():
    race = data["current_race"]
    race['status'] = "racing"
    socketio.emit('race_start', {"horses": race['horses']})
    
    # Simulazione corsa (durata circa 40 secondi)
    for step in range(100):
        time.sleep(0.4)
        # Invia posizioni casuali ma pesate
        posizioni = {h['id']: random.uniform(0.5, 2.0) for h in race['horses']}
        socketio.emit('race_update', posizioni)
    
    # Fine gara e reset
    race['status'] = "waiting"
    race['horses'] = genera_nuova_corsa()
    race['total_pool'] = 0
    race['bets'] = []
    socketio.emit('update_data', data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
