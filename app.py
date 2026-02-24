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
    "settings": {
        "auto_timer": True, 
        "max_bet_singola": 0.0, 
        "max_bet_accoppiata": 0.0, 
        "max_bet_trio": 0.0,
        "timer_duration": 60,
        "min_horses": 6, 
        "max_horses": 9,
        "yt_wait_enable": True, "yt_wait_url": "L_LUpnjgPso", "yt_wait_start": 0, "yt_wait_end": 0,    
        "yt_race_enable": True, "yt_race_url": "XqEQJe1kRHA", "yt_race_start": 23, "yt_race_end": 0,   
        "yt_win_enable": True, "yt_win_url": "E3m-XH1Kij0",  "yt_win_start": 54, "yt_win_end": 65     
    }
}

def genera_nuova_corsa():
    min_h = data["settings"]["min_horses"]
    max_h = data["settings"]["max_horses"]
    if min_h > max_h: 
        min_h, max_h = max_h, min_h 
    num = random.randint(min_h, max_h) 
    
    nomi = random.sample(["Western Smoke", "Più Forte", "Lord Thunder", "Stud Rocket", "National Man", "Golden King", "Pocket Delight", "Diamond Fire", "Wild Lester", "Cowboy Muffin"], num)
    
    # MATEMATICA: 1/3 di super favoriti
    num_fav = max(1, num // 3)
    weights = []
    for i in range(num):
        if i < num_fav: 
            weights.append(random.uniform(100, 180)) # Super favoriti
        else: 
            weights.append(random.uniform(10, 50)) # Outsider
    
    random.shuffle(weights)
    tot_w = sum(weights)
    p_vittoria = [w / tot_w for w in weights]
    
    # Lavagna (Margine Banco) al 35% (Garantisce utili nel lungo periodo)
    house_edge = 1.35 

    horses = []
    for i in range(num):
        q_v = max(1.02, round(1 / (p_vittoria[i] * house_edge), 2))
        q_p = max(1.01, round(q_v / 3.5, 2))
        horses.append({
            "id": i + 1, 
            "nome": nomi[i], 
            "prob_vittoria": p_vittoria[i], 
            "quota_v": q_v, 
            "quota_p": q_p, 
            "quota_u": max(1.10, round(5/q_v, 2)),
            "colore": f"#{random.randint(100,255):02x}{random.randint(100,255):02x}{random.randint(100,255):02x}"
        })
    return horses

data["current_race"]["horses"] = genera_nuova_corsa()

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/admin')
def admin(): 
    return render_template('admin.html')

@socketio.on('request_update')
def send_update(): 
    emit('update_data', data)

@socketio.on('admin_login')
def admin_login(req):
    # LOGIN ADMIN
    if req.get('user') == "admincorsacavalli" and req.get('pass') == "cavallino01":
        emit('admin_auth_success')
    else:
        emit('admin_auth_error', "Credenziali Admin Errate!")

@socketio.on('admin_update_wallet')
def handle_wallet(req):
    u = req['user'].strip()
    amt = float(req['amount'])
    if u not in data["users"]: 
        data["users"][u] = {
            "wallet": 0.0, 
            "password": req.get('password','1234'), 
            "tot_dep": 0.0, 
            "tot_vin": 0.0, 
            "tot_per": 0.0
        }
    data["users"][u]["wallet"] = round(data["users"][u]["wallet"] + amt, 2)
    if amt > 0: 
        data["users"][u]["tot_dep"] += amt 
    socketio.emit('update_data', data)

@socketio.on('admin_update_settings')
def update_settings(req):
    for k in req:
        if k in data["settings"]: 
            data["settings"][k] = type(data["settings"][k])(req[k])
    socketio.emit('update_data', data)

@socketio.on('admin_force_start')
def force_start():
    if data["current_race"]["status"] in ["waiting", "countdown"]:
        data["current_race"]["timer"] = 1
        if data["current_race"]["status"] == "waiting":
            data["current_race"]["status"] = "countdown"
            socketio.start_background_task(run_countdown)
        socketio.emit('update_data', data)

@socketio.on('tentativo_login')
def login_check(req):
    u = req.get('user','').strip()
    p = req.get('password','').strip()
    if u in data["users"] and data["users"][u]["password"] == p:
        if u not in data["online_users"]: 
            data["online_users"].append(u)
        emit('login_success', {"user": u})
        socketio.emit('update_data', data)
    else: 
        emit('login_error', "Credenziali errate!")

@socketio.on('place_bet')
def handle_bet(bet_data):
    race = data["current_race"]
    u = bet_data['user']
    amt = float(bet_data['amount'])
    tipo = bet_data['type']
    
    if u not in data["users"] or data["users"][u]["wallet"] < amt:
        emit('login_error', "Saldo insufficiente!")
        return
    
    if race["status"] in ["waiting", "countdown"]:
        data["users"][u]["wallet"] = round(data["users"][u]["wallet"] - amt, 2)
        data["users"][u]["tot_per"] += amt
        data["admin_stats"]["totale_incassato"] = round(data["admin_stats"]["totale_incassato"] + amt, 2)
        
        race["bets"].append({
            "user": u, 
            "type": tipo, 
            "dettaglio": bet_data['dettaglio'], 
            "amount": amt, 
            "quota": float(bet_data['quota']),
            "h1": bet_data.get('h1'), 
            "h2": bet_data.get('h2'), 
            "h3": bet_data.get('h3'), 
            "ordine": bet_data.get('ordine', True), 
            "esito": "In Attesa"
        })
        
        if data["settings"]["auto_timer"] and race["status"] == "waiting":
            race["timer"] = data["settings"]["timer_duration"]
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
    
    # Aggiorna subito i client per far comparire il banner "Scommesse Chiuse" in tempo reale
    socketio.emit('update_data', data) 
    socketio.emit('race_start')
    
    steps = 250 
    
    # LA VARIANZA ESTREMA
    # Ogni cavallo ha una "giornata" diversa. Anche il favorito può correre malissimo.
    forma_segreta = {h["id"]: random.uniform(0.6, 1.4) for h in race["horses"]}
    
    raw_progress = {h["id"]: [0]*steps for h in race["horses"]}
    for h in race["horses"]:
        for step in range(steps):
            # Il caos puro (fino a 0.09) domina sulla statistica (fino a 0.01)
            caos = random.uniform(0.005, 0.09) 
            spinta_quota = h["prob_vittoria"] * 0.01 
            raw_progress[h["id"]][step] = (caos + spinta_quota) * forma_segreta[h["id"]]
            
    totals = {hid: sum(raw_progress[hid]) for hid in raw_progress}
    winner_id = max(totals, key=totals.get)
    scale = (2 * math.pi) / totals[winner_id]
    
    current_pos = {h["id"]: 0 for h in race["horses"]}
    for step in range(steps):
        for h in race["horses"]: 
            current_pos[h["id"]] += (raw_progress[h["id"]][step] * scale)
        socketio.emit('race_update', current_pos)
        socketio.sleep(0.12)

    classifica = sorted(race["horses"], key=lambda h: current_pos[h["id"]], reverse=True)
    id_1 = classifica[0]["id"]
    id_2 = classifica[1]["id"]
    id_3 = classifica[2]["id"]
    id_ult = classifica[-1]["id"]
    
    tot_pagato = 0.0
    for b in race["bets"]:
        vinto = False
        if b["type"] == "Vincente" and b["h1"] == id_1: vinto = True
        elif b["type"] == "Piazzato" and b["h1"] in [id_1, id_2, id_3]: vinto = True
        elif b["type"] == "Ultimo" and b["h1"] == id_ult: vinto = True
        elif b["type"] == "Accoppiata":
            if b["ordine"] and b["h1"] == id_1 and b["h2"] == id_2: vinto = True
            elif not b["ordine"] and (set([b["h1"], b["h2"]]) == set([id_1, id_2])): vinto = True
        elif b["type"] == "Trio":
            if b["ordine"] and b["h1"] == id_1 and b["h2"] == id_2 and b["h3"] == id_3: vinto = True
            elif not b["ordine"] and (set([b["h1"], b["h2"], b["h3"]]) == set([id_1, id_2, id_3])): vinto = True
        
        if vinto:
            b["esito"] = "Vinta"
            vincita = round(b["amount"] * b["quota"], 2)
            data["users"][b["user"]]["wallet"] = round(data["users"][b["user"]]["wallet"] + vincita, 2)
            data["users"][b["user"]]["tot_vin"] += vincita
            data["users"][b["user"]]["tot_per"] -= b["amount"]
            tot_pagato += vincita
        else: 
            b["esito"] = "Persa"
            
    data["admin_stats"]["totale_pagato"] = round(data["admin_stats"]["totale_pagato"] + tot_pagato, 2)
    data["admin_stats"]["bilancio"] = round(data["admin_stats"]["totale_incassato"] - data["admin_stats"]["totale_pagato"], 2)
    
    res = {
        "gara_num": len(data["history"]) + 1, 
        "primo_id": id_1, 
        "primo_nome": classifica[0]["nome"],
        "primo": f"N°{id_1} - {classifica[0]['nome']}", 
        "q_primo": classifica[0]["quota_v"],
        "secondo": f"N°{id_2} - {classifica[1]['nome']}", 
        "terzo": f"N°{id_3} - {classifica[2]['nome']}", 
        "ultimo": f"N°{id_ult} - {classifica[-1]['nome']}", 
        "q_ultimo": classifica[-1]["quota_u"],
        "vincitori": [{"user": b["user"], "vincita": round(b["amount"]*b["quota"],2), "dettaglio": b["dettaglio"]} for b in race["bets"] if b["esito"] == "Vinta"],
        "scommesse": race["bets"].copy() 
    }
    
    data["history"].append(res)
    socketio.emit('race_finished', res)
    socketio.sleep(15) # Attesa per canzone finale
    
    race["status"] = "waiting"
    race["horses"] = genera_nuova_corsa()
    race["bets"] = []
    race["timer"] = 0
    socketio.emit('update_data', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
