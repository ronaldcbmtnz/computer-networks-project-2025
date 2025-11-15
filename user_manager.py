import json
import os
from threading import Lock

# Configuración
USERS_FILE = "data/users.json"
USERS_LOCK = Lock()

def _load_users():
    """
    Carga los usuarios desde el archivo JSON.
    
    Returns:
        list: Lista de diccionarios con usuarios y contraseñas
    """
    if not os.path.exists(USERS_FILE):
        print(f"Error: No existe el archivo {USERS_FILE}")
        print("Crea el archivo con la estructura:")
        print('[{"username": "admin", "password": "admin123"}]')
        return []
    
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {USERS_FILE} tiene formato JSON inválido")
        return []

def validate_user(username, password):
    """
    Valida si el usuario y contraseña existen en el JSON.
    
    Args:
        username (str): Nombre de usuario
        password (str): Contraseña
        
    Returns:
        bool: True si las credenciales son válidas, False en caso contrario
    """
    with USERS_LOCK:
        users = _load_users()
        
        for user in users:
            if user.get('username') == username and user.get('password') == password:
                return True
        
        return False



