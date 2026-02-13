from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import threading
import time
from collections import deque
import logging
import json
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
HISTORY_FILE = 'history.json'
HISTORY_LENGTH = 20  # 20 items * 30 sec = 10 mins
UPDATE_INTERVAL = 30 # Seconds

SITES = {
    'Self-Service': 'https://apps.uillinois.edu/selfservice',
    'Canvas': 'https://canvas.illinois.edu',
    'MyIllini': 'https://myillini.illinois.edu',
    'Course Explorer': 'https://courses.illinois.edu',
    'UIUC Status': 'https://status.illinois.edu',
    'Media Space': 'https://mediaspace.illinois.edu',
    'APPS Directory': 'https://apps.uillinois.edu',
    'Illinois.edu': 'https://illinois.edu',
    'Student Affairs': 'https://studentaffairs.illinois.edu',
    'Admissions': 'https://admissions.illinois.edu',
    'University Housing': 'https://housing.illinois.edu',
    'Library': 'https://library.illinois.edu',
    'Technology Services': 'https://techservices.illinois.edu',
    'Box': 'https://uofi.box.com',
    'Webstore': 'https://webstore.illinois.edu'
}

# --- DATA PERSISTENCE ---
# We use a dictionary of lists instead of deques for JSON compatibility
status_history = {} 
current_status = {}
last_check_time = None

def load_history():
    """Load history from JSON file on startup"""
    global status_history, last_check_time, current_status
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                # Convert lists back to deque-like behavior (keep last 20)
                loaded_history = data.get('history', {})
                status_history = {site: list(loaded_history.get(site, []))[-HISTORY_LENGTH:] for site in SITES}
                
                # Load last known status
                current_status = data.get('current', {})
                last_check_time = datetime.fromisoformat(data.get('last_check')) if data.get('last_check') else None
                logger.info("Loaded history from file.")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            status_history = {site: [] for site in SITES}
    else:
        status_history = {site: [] for site in SITES}

def save_history():
    """Save current state to JSON file"""
    try:
        data = {
            'history': status_history,
            'current': current_status,
            'last_check': last_check_time.isoformat() if last_check_time else None
        }
        with open(HISTORY_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        logger.error(f"Failed to save history: {e}")

# Load immediately on start
load_history()

def check_website(name, url):
    try:
        start_time = time.time()
        headers = {'User-Agent': 'UIUC-Status-Monitor/1.0'}
        # Shorter timeout to prevent hanging
        response = requests.get(url, timeout=5, headers=headers)
        response_time = round((time.time() - start_time) * 1000)
        
        return {
            'status': 'up' if response.status_code == 200 else 'down',
            'time': response_time,
            'code': response.status_code,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {
            'status': 'down',
            'time': 0,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

def monitor_loop():
    global last_check_time
    logger.info("Monitor thread started...")
    while True:
        try:
            for name, url in SITES.items():
                result = check_website(name, url)
                
                # Update Current
                current_status[name] = result
                
                # Update History
                if name not in status_history:
                    status_history[name] = []
                
                status_history[name].append(result)
                
                # Trim to max length
                if len(status_history[name]) > HISTORY_LENGTH:
                    status_history[name].pop(0)
            
            last_check_time = datetime.now()
            save_history() # Save to file after every check
            logger.info(f"Check complete & saved at {last_check_time}")
            
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")
        
        time.sleep(UPDATE_INTERVAL)

# --- FLASK ROUTES ---

def get_site_data():
    """Prepare data for frontend"""
    data = {}
    for name in SITES:
        history = status_history.get(name, [])
        
        # Calculate Uptime
        if history:
            up_count = sum(1 for h in history if h['status'] == 'up')
            uptime = round((up_count / len(history)) * 100, 2)
        else:
            uptime = 0.0

        # Get Current Status (or default to unknown)
        current = current_status.get(name, {'status': 'unknown', 'time': 0})

        data[name] = {
            'current': current,
            'uptime': uptime,
            'history': history, # List of dicts {time, status, ...}
            'url': SITES[name]
        }
    
    return {
        'sites': data,
        'last_check': last_check_time.isoformat() if last_check_time else None
    }

@app.route('/')
def index():
    return render_template('index.html', initial_data=get_site_data())

@app.route('/api/status')
def get_status():
    return jsonify(get_site_data())

if __name__ == '__main__':
    # PREVENT DUPLICATE THREADS IN DEBUG MODE
    # The monitor only runs in the main server process, not the reloader
    if os.environ.get('WERKZEUG_RUN_MAIN') or not app.debug:
        threading.Thread(target=monitor_loop, daemon=True).start()
        
    app.run(debug=True, host='0.0.0.0', port=5000)