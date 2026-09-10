import os
import json
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

CREDENTIALS_FILE = 'users.json'

def initialize_users():
    """Checks if the user database exists. If not, seeds it based on .env."""
    if not os.path.exists(CREDENTIALS_FILE):
        initial_users = {}
        
        seed_user = os.getenv('SEED_USER', 'False').lower() == 'true'
        default_user = os.getenv('ATTENDANCE_ADMIN_USER', 'admin')
        default_pass = os.getenv('ATTENDANCE_ADMIN_PASS', 'Admin@123')
        
        if seed_user:
            initial_users[default_user] = default_pass
            print(f"Default admin account ({default_user}) seeded.")
            
        with open(CREDENTIALS_FILE, 'w') as f:
            json.dump(initial_users, f, indent=4)

def _load_users():
    """Internal function to load current users from the JSON file."""
    initialize_users()
    with open(CREDENTIALS_FILE, 'r') as f:
        return json.load(f)

def _save_users(users):
    """Internal function to save updated users to the JSON file."""
    with open(CREDENTIALS_FILE, 'w') as f:
        json.dump(users, f, indent=4)

def login(user_id, password):
    """Validates login credentials."""
    users = _load_users()
    return users.get(user_id) == password

def change_credentials(current_user_id, new_user_id, new_password):
    """Allows a logged-in admin to change their user_id and password."""
    users = _load_users()
    
    if current_user_id not in users:
        return False, "Error: Current user does not exist."
    if new_user_id != current_user_id and new_user_id in users:
        return False, "Error: The new admin ID is already taken."
    
    del users[current_user_id]
    users[new_user_id] = new_password
    
    _save_users(users)
    return True, "Credentials updated successfully! Please log in again."

def create_admin(new_admin_id, new_admin_password):
    """Allows an existing admin to create an additional admin account."""
    users = _load_users()
    
    if new_admin_id in users:
        return False, "Error: This Admin ID already exists."
    
    users[new_admin_id] = new_admin_password
    _save_users(users)
    return True, f"New admin '{new_admin_id}' created successfully."