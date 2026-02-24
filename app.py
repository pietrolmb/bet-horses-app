import random
import math
import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

data = {
    "users": {},
    "online_users": [],
    "admin_stats": {"totale_incassato": 0.0, "totale_pagato": 0.0, "bilancio": 0.0},
    "current_race": {"status": "waiting", "horses": [], "bets": [], "timer": 0},
    "history": [],
    "settings": {"auto_timer": True, "max_bet": 0, "timer_duration": 60}
}

NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    num = random.randint(8, 12)
    horses = []
    nomi = random.sample([f"{a} {b}" for a in NOMI_A for b in NOMI_B], num)
    
    raw_weights = [random.uniform(10, 100) for _ in range(num)]
    tot_weight = sum(raw_weights)
    p_vittoria = [w / tot_weight for w in raw_weights]
    
    inv_weights = [1.0 / p for p in p_vittoria]
    tot_inv = sum(inv_weights)
    p_ultimo = [iw / tot_inv for iw in inv_weights]
    
    house_edge = 1.18 

    for i in range(num):
        q_v = max(1.10, round(1 / (p_vittoria[i] * house_edge), 2))
        q_p = max(1.05, round(q_v / 3.2, 2))
        q_u = max(1.10, round(1 / (p_ultimo[i] * house_edge), 2))

        horses.append({
            "id": i + 1, "nome": nomi[i], 
            "prob_vittoria": p_vittoria[i], 
            "quota_v": q_v, "quota_p": q_p, "quota_u": q_u, 
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
    user = req['user'].strip()
    password = req.get('password', '').strip()
    amount = float(req['amount'])
    
    if user not in data["users"]: 
        data["users"][user] = {"wallet": 0.0, "password": password if password else "1234"}
    else:
        if password != "": data["users"][user]["password"] = password
        
    data["users"][user]["wallet"] = round(data["users"][user]["wallet"] + amount, 2)
    socketio.emit('update_data', data)

@socketio.on('admin_update_settings')
def update_settings(req):
    if 'max_bet' in req: data["settings"]["max_bet"] = float(req['max_bet'])
    if 'auto_timer' in req: data["settings"]["auto_timer"] = req['auto_timer']
    if 'timer_duration' in req: data["settings"]["timer_duration"] = int(req['timer_duration'])
    socketio.emit('update_data', data)

@socketio.on('admin_force_start')
def force_start():
    race = data["current_race"]
    if race["status"] in ["waiting", "countdown"]:
        race["timer"] = 1 
        if race["status"] == "waiting":
            race["status"] = "countdown"
            socketio.start_background_task(run_countdown)
        socketio.emit('update_data', data)

@socketio.on('tentativo_login')
def login_check(req):
    user = req.get('user', '').strip()
    pwd = req.get('password', '').strip()
    if user in data["users"] and data["users"][user]["password"] == pwd:
        if user not in data["online_users"]: data["online_users"].append(user)
        emit('login_success', {"user": user})
        socketio.emit('update_data', data)
    else:
        emit('login_error', "Nome utente o Password errati!")

@socketio.on('place_bet')
def handle_bet(bet_data):
    race = data["current_race"]
    user = bet_data['user']
    importo = float(bet_data['amount'])
    tipo = bet_data['type']
    
    if data["settings"]["max_bet"] > 0 and importo > data["settings"]["max_bet"]:
        emit('login_error', f"Puntata massima consentita: {data['settings']['max_bet']}€")
        return
    
    if user in data["users"] and data["users"][user]["wallet"] >= importo and race["status"] in ["waiting", "countdown"]:
        data["users"][user]["wallet"] = round(data["users"][user]["wallet"] - importo, 2)
        data["admin_stats"]["totale_incassato"] = round(data["admin_stats"]["totale_incassato"] + importo, 2)
        
        cavallo = next(h for h in race["horses"] if h["id"] == bet_data['horse_id'])
        if tipo == "Piazzato": quota = cavallo["quota_p"]
        elif tipo == "Ultimo": quota = cavallo["quota_u"]
        else: quota = cavallo["quota_v"]
        
        race["bets"].append({
            "user": user, "horse_id": bet_data['horse_id'], "horse_nome": cavallo['nome'],
            "amount": importo, "quota": quota, "type": tipo
        })
        
        if data["settings"]["auto_timer"]:
            race["timer"] = data["settings"]["timer_duration"]
            if race["status"] == "waiting":
                race["status"] = "countdown"
                socketio.start_background_task(run_countdown)
        
        socketio.emit('update_data', data)

def run_countdown():
    race = data["current_race"]
    while race["timer"] > 0:
        socketio.emit('timer_update', race["timer"])
        socketio.sleep(1)
        race["timer"] -= 1
    start_race()

def start_race():
    race = data["current_race"]
    race["status"] = "racing"
    socketio.emit('race_start')
    
    posizioni = {h["id"]: 0 for h in race["horses"]}
    
    # LA NUOVA CORSA: Si ferma ESATTAMENTE quando il primo compie 1 giro (2 * Pi Greco)
    traguardo_raggiunto = False
    while not traguardo_raggiunto:
        max_pos = 0
        for h in race["horses"]: 
            passo_base = random.uniform(0.01, 0.06)
            spinta = h["prob_vittoria"] * 0.025 
            posizioni[h["id"]] += (passo_base + spinta)
            if posizioni[h["id"]] > max_pos:
                max_pos = posizioni[h["id"]]
                
        socketio.emit('race_update', posizioni)
        socketio.sleep(0.12)
        
        if max_pos >= 2 * math.pi:
            traguardo_raggiunto = True
            
    classifica = sorted(race["horses"], key=lambda h: posizioni[h["id"]], reverse=True)
    
    id_primo = classifica[0]["id"]
    id_secondo = classifica[1]["id"]
    id_terzo = classifica[2]["id"]
    id_ultimo = classifica[-1]["id"]
    
    vincitori_gara = []
    totale_pagato_gara = 0.0
    for bet in race["bets"]:
        vinto = False
        if bet["type"] == "Vincente" and bet["horse_id"] == id_primo: vinto = True
        elif bet["type"] == "Piazzato" and bet["horse_id"] in [id_primo, id_secondo, id_terzo]: vinto = True
        elif bet["type"] == "Ultimo" and bet["horse_id"] == id_ultimo: vinto = True
        
        if vinto:
            vincita = round(bet["amount"] * bet["quota"], 2)
            data["users"][bet["user"]]["wallet"] = round(data["users"][bet["user"]]["wallet"] + vincita, 2)
            totale_pagato_gara += vincita
            vincitori_gara.append({"user": bet["user"], "vincita": vincita, "tipo": bet["type"]})
            
    data["admin_stats"]["totale_pagato"] = round(data["admin_stats"]["totale_pagato"] + totale_pagato_gara, 2)
    data["admin_stats"]["bilancio"] = round(data["admin_stats"]["totale_incassato"] - data["admin_stats"]["totale_pagato"], 2)
    
    q1 = classifica[0]["quota_v"]
    q2 = classifica[1]["quota_v"]
    q3 = classifica[2]["quota_v"]
    qu = classifica[-1]["quota_u"]
    
    risultato = {
        "gara_num": len(data["history"]) + 1,
        "primo_id": id_primo,
        "primo_nome": classifica[0]["nome"],
        "primo": f"N°{id_primo} - {classifica[0]['nome']}", "q_primo": q1,
        "secondo": f"N°{id_secondo} - {classifica[1]['nome']}",
        "terzo": f"N°{id_terzo} - {classifica[2]['nome']}", 
        "ultimo": f"N°{id_ultimo} - {classifica[-1]['nome']}", "q_ultimo": qu,
        "q_accoppiata": round(q1 * q2, 2), "q_trio": round(q1 * q2 * q3, 2),
        "vincitori": vincitori_gara, "scommesse": race["bets"].copy() 
    }
    data["history"].append(risultato)
    
    socketio.emit('race_finished', risultato)
    socketio.sleep(8) 
    
    race["status"] = "waiting"
    race["horses"] = genera_nuova_corsa()
    race["bets"] = []
    race["timer"] = 0
    socketio.emit('update_data', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
