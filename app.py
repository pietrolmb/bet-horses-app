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
        "max_bet_singola": 0.0, "max_bet_accoppiata": 0.0, "max_bet_trio": 0.0,
        "timer_duration": 60,
        "min_horses": 6, "max_horses": 9,
        "yt_wait_enable": True, "yt_wait_url": "L_LUpnjgPso", "yt_wait_start": 0, "yt_wait_end": 0,    
        "yt_race_enable": True, "yt_race_url": "XqEQJe1kRHA", "yt_race_start": 23, "yt_race_end": 0,   
        "yt_win_enable": True, "yt_win_url": "E3m-XH1Kij0",  "yt_win_start": 54, "yt_win_end": 65     
    }
}

NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    min_h = data["settings"]["min_horses"]
    max_h = data["settings"]["max_horses"]
    if min_h > max_h: min_h, max_h = max_h, min_h 
    num = random.randint(min_h, max_h) 
    
    horses = []
    nomi = random.sample([f"{a} {b}" for a in NOMI_A for b in NOMI_B], num)
    
    # Crea pesi casuali ma ben distribuiti
    weights = [random.uniform(20, 100) for _ in range(num)]
    weights[0] = random.uniform(80, 130) # Assicura almeno un buon favorito
    random.shuffle(weights) 
    
    tot_weight = sum(weights)
    p_vittoria = [w / tot_weight for w in weights]
    
    inv_weights = [1.0 / p for p in p_vittoria]
    tot_inv = sum(inv_weights)
    p_ultimo = [iw / tot_inv for iw in inv_weights]
    
    house_edge = 1.25 # Margine banco del 25%

    for i in range(num):
        q_v = max(1.10, round(1 / (p_vittoria[i] * house_edge), 2))
        q_p = max(1.05, round(q_v / 3.0, 2))
        q_u = max(1.10, round(1 / (p_ultimo[i] * house_edge), 2))

        horses.append({
            "id": i + 1, "nome": nomi[i], "prob_vittoria": p_vittoria[i], 
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

@socketio.on('admin_login')
def admin_login(req):
    if req.get('user') == "admincorsacavalli" and req.get('pass') == "cavallino01":
        emit('admin_auth_success')
    else:
        emit('admin_auth_error', "Credenziali Admin Errate!")

@socketio.on('admin_update_wallet')
def handle_wallet(req):
    user = req['user'].strip()
    password = req.get('password', '').strip()
    amount = float(req['amount'])
    
    if user not in data["users"]: 
        data["users"][user] = {"wallet": 0.0, "password": password if password else "1234", "tot_dep":0.0, "tot_vin":0.0, "tot_per":0.0}
    else:
        if password != "": data["users"][user]["password"] = password
        
    data["users"][user]["wallet"] = round(data["users"][user]["wallet"] + amount, 2)
    if amount > 0: data["users"][user]["tot_dep"] += amount 
    socketio.emit('update_data', data)

@socketio.on('admin_update_settings')
def update_settings(req):
    for key in req:
        if key in data["settings"]:
            data["settings"][key] = type(data["settings"][key])(req[key])
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
    dettaglio = bet_data['dettaglio']
    quota = float(bet_data['quota'])
    
    if user not in data["users"] or data["users"][user]["wallet"] < importo:
        emit('login_error', "Saldo insufficiente!")
        return

    limit = 0.0
    if tipo in ["Vincente", "Piazzato", "Ultimo"]: limit = data["settings"]["max_bet_singola"]
    elif tipo == "Accoppiata": limit = data["settings"]["max_bet_accoppiata"]
    elif tipo == "Trio": limit = data["settings"]["max_bet_trio"]

    if limit > 0:
        giocate_precedenti = sum(b['amount'] for b in race['bets'] if b['user'] == user and b['dettaglio'] == dettaglio and b['type'] == tipo)
        if giocate_precedenti + importo > limit:
            emit('login_error', f"Limite superato! Hai già puntato {giocate_precedenti}€ su questa opzione. Massimo consentito: {limit}€.")
            return
            
    if race["status"] in ["waiting", "countdown"]:
        data["users"][user]["wallet"] = round(data["users"][user]["wallet"] - importo, 2)
        data["users"][user]["tot_per"] += importo 
        data["admin_stats"]["totale_incassato"] = round(data["admin_stats"]["totale_incassato"] + importo, 2)
        
        race["bets"].append({
            "user": user, "type": tipo, "dettaglio": dettaglio, "amount": importo, "quota": quota,
            "h1": bet_data.get('h1'), "h2": bet_data.get('h2'), "h3": bet_data.get('h3'), "ordine": bet_data.get('ordine', True),
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
    socketio.emit('update_data', data) # Chiusura immediata banner
    socketio.emit('race_start')
    
    posizioni = {h["id"]: 0.0 for h in race["horses"]}
    classifica_finale = []
    arrivati = set()
    
    # MOTORE ADRENALINICO: Ogni cavallo ha uno slancio che cambia continuamente
    momentum = {h["id"]: random.uniform(0.8, 1.2) for h in race["horses"]}
    step_count = 0

    # Continua finché l'ULTIMO cavallo non ha tagliato il traguardo
    while len(classifica_finale) < len(race["horses"]):
        step_count += 1
        
        # Orizzonte Sorpassi: ogni ~1.5 secondi cambiano le velocità
        if step_count % 12 == 0:
            for h in race["horses"]: 
                momentum[h["id"]] = random.uniform(0.7, 1.3)

        for h in race["horses"]:
            if h["id"] not in arrivati:
                # La probabilità aiuta, ma l'rng e il momentum dominano per garantire spettacolo
                edge = h["prob_vittoria"] * 0.003
                step_dist = random.uniform(0.015, 0.030) * momentum[h["id"]] + edge
                
                posizioni[h["id"]] += step_dist
                
                # Se taglia il traguardo (1 Giro esatto = 2 * Pi Greco)
                if posizioni[h["id"]] >= 2 * math.pi:
                    posizioni[h["id"]] = 2 * math.pi # Lo blocca visivamente sulla linea
                    arrivati.add(h["id"])
                    classifica_finale.append(h)
                    
        socketio.emit('race_update', posizioni)
        socketio.sleep(0.12)

    id_1 = classifica_finale[0]["id"]
    id_2 = classifica_finale[1]["id"]
    id_3 = classifica_finale[2]["id"]
    id_ult = classifica_finale[-1]["id"]
    
    vincitori_gara = []
    totale_pagato_gara = 0.0
    
    for bet in race["bets"]:
        vinto = False
        if bet["type"] == "Vincente" and bet["h1"] == id_1: vinto = True
        elif bet["type"] == "Piazzato" and bet["h1"] in [id_1, id_2, id_3]: vinto = True
        elif bet["type"] == "Ultimo" and bet["h1"] == id_ult: vinto = True
        elif bet["type"] == "Accoppiata":
            if bet["ordine"] and bet["h1"] == id_1 and bet["h2"] == id_2: vinto = True
            elif not bet["ordine"] and (set([bet["h1"], bet["h2"]]) == set([id_1, id_2])): vinto = True
        elif bet["type"] == "Trio":
            if bet["ordine"] and bet["h1"] == id_1 and bet["h2"] == id_2 and bet["h3"] == id_3: vinto = True
            elif not bet["ordine"] and (set([bet["h1"], bet["h2"], bet["h3"]]) == set([id_1, id_2, id_3])): vinto = True
        
        if vinto:
            bet["esito"] = "Vinta"
            vincita = round(bet["amount"] * bet["quota"], 2)
            data["users"][bet["user"]]["wallet"] = round(data["users"][bet["user"]]["wallet"] + vincita, 2)
            data["users"][bet["user"]]["tot_vin"] += vincita
            data["users"][bet["user"]]["tot_per"] -= bet["amount"] 
            totale_pagato_gara += vincita
            vincitori_gara.append({"user": bet["user"], "vincita": vincita, "dettaglio": bet["dettaglio"]})
        else:
            bet["esito"] = "Persa"
            
    data["admin_stats"]["totale_pagato"] = round(data["admin_stats"]["totale_pagato"] + totale_pagato_gara, 2)
    data["admin_stats"]["bilancio"] = round(data["admin_stats"]["totale_incassato"] - data["admin_stats"]["totale_pagato"], 2)
    
    risultato = {
        "gara_num": len(data["history"]) + 1,
        "primo_id": id_1, "primo_nome": classifica_finale[0]["nome"],
        "primo": f"N°{id_1} - {classifica_finale[0]['nome']}", "q_primo": classifica_finale[0]["quota_v"],
        "secondo": f"N°{id_2} - {classifica_finale[1]['nome']}",
        "terzo": f"N°{id_3} - {classifica_finale[2]['nome']}", 
        "ultimo": f"N°{id_ult} - {classifica_finale[-1]['nome']}", "q_ultimo": classifica_finale[-1]["quota_u"],
        "vincitori": vincitori_gara, "scommesse": race["bets"].copy() 
    }
    data["history"].append(risultato)
    
    socketio.emit('race_finished', risultato)
    socketio.sleep(15) 
    
    race["status"] = "waiting"
    race["horses"] = genera_nuova_corsa()
    race["bets"] = []
    race["timer"] = 0
    socketio.emit('update_data', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
