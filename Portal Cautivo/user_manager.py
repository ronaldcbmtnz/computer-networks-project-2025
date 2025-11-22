"""
user_manager.py
Módulo para la gestión de usuarios: registro, autenticación y almacenamiento.
"""
import json
import os

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'users.json')

def load_users():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        try:
            return json.load(f)
        except Exception:
            return {}

def save_users(users):
    with open(DATA_FILE, 'w') as f:
        json.dump(users, f)

def register_user(username, password):
    users = load_users()
    if username in users:
        return False  # Usuario ya existe
    users[username] = {'password': password}
    save_users(users)
    return True

def authenticate_user(username, password):
    users = load_users()
    user = users.get(username)
    if user and user['password'] == password:
        return True
    return False
import json
import os
from threading import Lock

# Configuración
USERS_FILE = "data/users.json"
USERS_LOCK = Lock()




