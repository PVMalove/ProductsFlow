import os
import shutil
import re

ROOT_DIR = r"c:\Users\Malove\Documents\Projects\Python\ProductsFlow_AI"
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
SERVICES_DIR = os.path.join(BACKEND_DIR, "services")

moves = {
    'http': ['main.py', 'dependencies.py', 'schemas.py', 'security.py', 'endpoints'],
    'workers': ['worker.py', 'outbox_worker.py'],
    'workers/commands': ['reservation_commands.py', 'payment_commands.py', 'reservation_result_handler.py'],
    'workers/cron': ['reservation_sweep.py']
}

def move_files(service_path):
    api_dir = os.path.join(service_path, 'src', 'api')
    if not os.path.exists(api_dir):
        return
    
    # Create target dirs
    for target_dir in moves.keys():
        os.makedirs(os.path.join(api_dir, target_dir), exist_ok=True)
        # Create __init__.py
        init_file = os.path.join(api_dir, target_dir, '__init__.py')
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                pass
                
        # for nested like workers/commands
        if '/' in target_dir:
            parent = target_dir.split('/')[0]
            parent_init = os.path.join(api_dir, parent, '__init__.py')
            if not os.path.exists(parent_init):
                with open(parent_init, 'w') as f:
                    pass

    # Move items
    for item in os.listdir(api_dir):
        if item == '__pycache__':
            continue
        item_path = os.path.join(api_dir, item)
        
        # Find where it should go
        target_sub = None
        for t_dir, items in moves.items():
            if item in items:
                target_sub = t_dir
                break
                
        if target_sub:
            dest = os.path.join(api_dir, target_sub, item)
            print(f"Moving {item_path} to {dest}")
            shutil.move(item_path, dest)

def replace_in_file(filepath, replacements):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in replacements:
        new_content = new_content.replace(old, new)
        
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def update_imports():
    replacements = [
        ("api.main", "api.http.main"),
        ("api.dependencies", "api.http.dependencies"),
        ("api.schemas", "api.http.schemas"),
        ("api.security", "api.http.security"),
        ("api.endpoints", "api.http.endpoints"),
        ("api.worker", "api.workers.worker"),
        ("api.outbox_worker", "api.workers.outbox_worker"),
        ("api.reservation_commands", "api.workers.commands.reservation_commands"),
        ("api.reservation_sweep", "api.workers.cron.reservation_sweep"),
        ("api.reservation_result_handler", "api.workers.commands.reservation_result_handler"),
        ("api.payment_commands", "api.workers.commands.payment_commands"),
        ("from api import main", "from api.http import main"),
        ("from api import dependencies", "from api.http import dependencies"),
        ("from api import schemas", "from api.http import schemas"),
        ("from api import security", "from api.http import security"),
        ("from api import endpoints", "from api.http import endpoints"),
        ("from api import worker", "from api.workers import worker"),
        ("from api import outbox_worker", "from api.workers import outbox_worker"),
        ("from api import reservation_commands", "from api.workers.commands import reservation_commands"),
        ("from api import reservation_sweep", "from api.workers.cron import reservation_sweep"),
        ("from api import reservation_result_handler", "from api.workers.commands import reservation_result_handler"),
        ("from api import payment_commands", "from api.workers.commands import payment_commands"),
    ]
    
    # Process all python files in backend/services
    for root, dirs, files in os.walk(SERVICES_DIR):
        if '__pycache__' in root or '.venv' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                replace_in_file(os.path.join(root, file), replacements)
                
    # Also process docker-compose and Makefile in backend/
    for root, dirs, files in os.walk(BACKEND_DIR):
        if '__pycache__' in root or '.venv' in root or 'services' in root or 'libs' in root:
            continue
        for file in files:
            if file.endswith('.yml') or file == 'Makefile':
                replace_in_file(os.path.join(root, file), replacements)

if __name__ == '__main__':
    for s_dir in os.listdir(SERVICES_DIR):
        full_path = os.path.join(SERVICES_DIR, s_dir)
        if os.path.isdir(full_path):
            move_files(full_path)
    update_imports()
