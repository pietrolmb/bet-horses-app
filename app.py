# QUESTE DUE RIGHE DEVONO ESSERE LE PRIME IN ASSOLUTO!
import eventlet
eventlet.monkey_patch()

import os
import random
import math
import certifi
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from pymongo import MongoClient

app = Flask(__name__)
# Sostituisci la vecchia riga di socketio con questa:
socketio = SocketIO(
    app, 
    cors_allowed_origins="*", 
    async_mode='eventlet', 
    ping_timeout=60,      # Aspetta fino a 60 secondi prima di dare errore
    ping_interval=25,     # Manda un segnale di "sono vivo" ogni 25 secondi
    manage_session=False
)
# ==========================================
# CONNESSIONE AL DATABASE MONGODB
# ==========================================
MONGO_URI = os.environ.get("MONGO_URI")

try:
    # Ho aggiunto tls=True per forzare la sicurezza SSL
    client = MongoClient(MONGO_URI, tls=True, tlsCAFile=certifi.where())
    db = client['horse_racing_db']
    print("✅ Connesso a MongoDB con successo!")
except Exception as e:
    print("❌ Errore di connessione a MongoDB:", e)

# ... (LASCIA TUTTO IL RESTO DEL CODICE IDENTICO FINO ALLA FINE) ...

try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client['horse_racing_db']
    print("✅ Connesso a MongoDB con successo!")
except Exception as e:
    print("❌ Errore di connessione a MongoDB:", e)

# ==========================================
# STRUTTURA DATI GLOBALE E SINCRONIZZAZIONE
# ==========================================
data = {
    "users": {},
    "online_users": [],
    "admin_stats": {"totale_incassato": 0.0, "totale_pagato": 0.0, "bilancio": 0.0},
    "current_race": {"status": "waiting", "horses": [], "bets": [], "timer": 0},
    "history": [],
    "settings": {
        "auto_timer": True, "max_bet_singola": 0.0, "max_bet_accoppiata": 0.0, "max_bet_trio": 0.0,
        "timer_duration": 60, "race_duration": 30, "min_horses": 6, "max_horses": 9,
        "yt_wait_enable": True, "yt_wait_url": "L_LUpnjgPso", "yt_wait_start": 0, "yt_wait_end": 0,    
        "yt_race_enable": True, "yt_race_url": "XqEQJe1kRHA", "yt_race_start": 23, "yt_race_end": 0,   
        "yt_win_enable": True, "yt_win_url": "E3m-XH1Kij0",  "yt_win_start": 54, "yt_win_end": 65     
    }
}

# CARICAMENTO INIZIALE DAL DATABASE
def carica_dati_da_db():
    global data
    
    # Carica Impostazioni
    db_settings = db.settings.find_one({"_id": "global"})
    if db_settings:
        db_settings.pop("_id", None)
        data["settings"].update(db_settings)
    else:
        db.settings.insert_one({"_id": "global", **data["settings"]})
        
    # Carica Statistiche Admin
    db_stats = db.admin_stats.find_one({"_id": "global"})
    if db_stats:
        db_stats.pop("_id", None)
        data["admin_stats"].update(db_stats)
    else:
        db.admin_stats.insert_one({"_id": "global", **data["admin_stats"]})
        
    # Carica Utenti
    for u in db.users.find():
        data["users"][u["_id"]] = {
            "wallet": u.get("wallet", 0.0),
            "password": u.get("password", "1234"),
            "tot_dep": u.get("tot_dep", 0.0),
            "tot_vin": u.get("tot_vin", 0.0),
            "tot_per": u.get("tot_per", 0.0)
        }
        
    # Carica Storico (Ultime 20 gare per non appesantire la ram)
    storico_db = list(db.history.find().sort("gara_num", -1).limit(20))
    for h in storico_db:
        h.pop("_id", None)
    data["history"] = storico_db[::-1] # Li rimette in ordine cronologico

carica_dati_da_db()

# FUNZIONI DI SALVATAGGIO RAPIDO
def salva_utente(username):
    db.users.update_one({"_id": username}, {"$set": data["users"][username]}, upsert=True)

def elimina_utente_db(username):
    db.users.delete_one({"_id": username})

def salva_settings():
    db.settings.update_one({"_id": "global"}, {"$set": data["settings"]}, upsert=True)

def salva_stats():
    db.admin_stats.update_one({"_id": "global"}, {"$set": data["admin_stats"]}, upsert=True)

def salva_storico(risultato):
    db_res = risultato.copy()
    db.history.insert_one(db_res)


NOMI_A = ["Western", "Più Forte", "Lord", "Stud", "National", "Golden", "Pocket", "Diamond", "Wild", "Cowboy"]
NOMI_B = ["Smoke", "Non Si Può", "Lester", "Muffin", "Pride", "Thunder", "Rocket", "Delight", "Man", "King"]

def genera_nuova_corsa():
    min_h = data["settings"]["min_horses"]
    max_h = data["settings"]["max_horses"]
    if min_h > max_h: min_h, max_h = max_h, min_h 
    num = random.randint(min_h, max_h) 
    
    horses = []
    nomi = random.sample([f"{a} {b}" for a in NOMI_A for b in NOMI_B], num)
    
    num_fav = 2
    num_mid = max(2, num // 2 - 1)
    num_out = num - num_fav - num_mid
    
    weights = []
    for _ in range(num_fav): weights.append(random.uniform(90, 140))
    for _ in range(num_mid): weights.append(random.uniform(40, 75))
    for _ in range(num_out): weights.append(random.uniform(10, 30))
            
    random.shuffle(weights) 
    tot_w = sum(weights)
    p_vittoria = [w / tot_w for w in weights]
    
    inv_weights = [1.0 / p for p in p_vittoria]
    tot_inv = sum(inv_weights)
    p_ultimo = [iw / tot_inv for iw in inv_weights]
    
    house_edge = 1.35 

    for i in range(num):
        q_v = max(1.05, round(1 / (p_vittoria[i] * house_edge), 2))
        q_u = max(1.05, round(1 / (p_ultimo[i] * house_edge), 2))

        horses.append({
            "id": i + 1, "nome": nomi[i], "prob_vittoria": p_vittoria[i], 
            "quota_v": q_v, "quota_u": q_u, 
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
    
    salva_utente(user) # Salva su Database
    socketio.emit('update_data', data)

@socketio.on('admin_delete_user')
def admin_delete_user(req):
    user = req.get('user', '').strip()
    if user in data["users"]:
        del data["users"][user]
        if user in data["online_users"]:
            data["online_users"].remove(user)
        elimina_utente_db(user) # Elimina da Database
        socketio.emit('update_data', data)

@socketio.on('user_delete_self')
def user_delete_self(req):
    user = req.get('user', '').strip()
    if user in data["users"]:
        del data["users"][user]
        if user in data["online_users"]:
            data["online_users"].remove(user)
        elimina_utente_db(user) # Elimina da Database
        socketio.emit('update_data', data)

@socketio.on('admin_update_settings')
def update_settings(req):
    for key in req:
        if key in data["settings"]:
            data["settings"][key] = type(data["settings"][key])(req[key])
    salva_settings() # Salva su Database
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
    if tipo in ["Vincente", "Ultimo"]: limit = data["settings"]["max_bet_singola"]
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
        
        salva_utente(user) # Salva su DB
        salva_stats() # Salva su DB
        
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
    socketio.emit('update_data', data) 
    socketio.emit('race_start')
    
    total_steps = int(data["settings"]["race_duration"] / 0.12)
    if total_steps < 50: total_steps = 50 
    
    cavalli_rimasti = race["horses"].copy()
    ordine_arrivo = []
    
    while cavalli_rimasti:
        pesi = [h["prob_vittoria"] for h in cavalli_rimasti]
        totale_pesi = sum(pesi)
        r = random.uniform(0, totale_pesi)
        cumulato = 0
        for h in cavalli_rimasti:
            cumulato += h["prob_vittoria"]
            if r <= cumulato:
                ordine_arrivo.append(h)
                cavalli_rimasti.remove(h)
                break
                
    target_steps = {}
    step_spread = max(10, int(total_steps * 0.20)) 
    base_step = total_steps - step_spread
    
    for i, h in enumerate(ordine_arrivo):
        if i == len(ordine_arrivo) - 1:
            target_steps[h["id"]] = total_steps
        else:
            distanza_proporzionale = int(i * (step_spread / max(1, len(ordine_arrivo) - 1)))
            target_steps[h["id"]] = base_step + distanza_proporzionale
            
    profili_corsa = {}
    for h in race["horses"]:
        ts = target_steps[h["id"]]
        passi_grezzi = [random.uniform(0.1, 1.0) for _ in range(ts)]
        
        momentum = 1.0
        for j in range(ts):
            if j % 15 == 0: 
                momentum = random.uniform(0.4, 1.8) 
            passi_grezzi[j] *= momentum
            
        totale_grezzo = sum(passi_grezzi)
        scala = (2 * math.pi) / totale_grezzo 
        
        profili_corsa[h["id"]] = [p * scala for p in passi_grezzi]

    posizioni_attuali = {h["id"]: 0.0 for h in race["horses"]}
    
    for step in range(total_steps):
        frame = {}
        for h in race["horses"]:
            if step < len(profili_corsa[h["id"]]):
                posizioni_attuali[h["id"]] += profili_corsa[h["id"]][step]
            frame[h["id"]] = min(posizioni_attuali[h["id"]], 2 * math.pi)
            
        socketio.emit('race_update', frame)
        socketio.sleep(0.12)

    id_1 = ordine_arrivo[0]["id"]
    id_2 = ordine_arrivo[1]["id"]
    id_3 = ordine_arrivo[2]["id"]
    id_ult = ordine_arrivo[-1]["id"]
    
    vincitori_gara = []
    totale_pagato_gara = 0.0
    utenti_modificati = set()
    
    for bet in race["bets"]:
        vinto = False
        if bet["type"] == "Vincente" and bet["h1"] == id_1: vinto = True
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
            utenti_modificati.add(bet["user"])
        else:
            bet["esito"] = "Persa"
            
    data["admin_stats"]["totale_pagato"] = round(data["admin_stats"]["totale_pagato"] + totale_pagato_gara, 2)
    data["admin_stats"]["bilancio"] = round(data["admin_stats"]["totale_incassato"] - data["admin_stats"]["totale_pagato"], 2)
    
    # Salva Database Multiplo a fine gara
    salva_stats()
    for u in utenti_modificati:
        salva_utente(u)
    
    # DB: Recupera l'ultimo numero di gara assoluto dal DB per la sequenza esatta
    last_db_race = db.history.find_one({}, sort=[("gara_num", -1)])
    next_num = (last_db_race["gara_num"] + 1) if last_db_race else 1
    
    q1 = ordine_arrivo[0]["quota_v"]
    q2 = ordine_arrivo[1]["quota_v"]
    q3 = ordine_arrivo[2]["quota_v"]
    
    risultato = {
        "gara_num": next_num,
        "primo_id": id_1, "primo_nome": ordine_arrivo[0]["nome"],
        "primo": f"N°{id_1} - {ordine_arrivo[0]['nome']}", "q_primo": q1,
        "secondo": f"N°{id_2} - {ordine_arrivo[1]['nome']}",
        "terzo": f"N°{id_3} - {ordine_arrivo[2]['nome']}", 
        "ultimo": f"N°{id_ult} - {ordine_arrivo[-1]['nome']}", "q_ultimo": ordine_arrivo[-1]["quota_u"],
        "q_accoppiata": round(q1 * q2, 2), "q_trio": round(q1 * q2 * q3, 2),
        "vincitori": vincitori_gara, "scommesse": race["bets"].copy() 
    }
    
    salva_storico(risultato) # Salva su DB
    
    data["history"].append(risultato)
    if len(data["history"]) > 20: 
        data["history"].pop(0) # Mantiene leggera la RAM
    
    socketio.emit('race_finished', risultato)
    socketio.sleep(8) 
    
    race["status"] = "waiting"
    race["horses"] = genera_nuova_corsa()
    race["bets"] = []
    race["timer"] = 0
    socketio.emit('update_data', data)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=10000)
