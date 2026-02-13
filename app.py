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
import urllib3

# --- DISABLE SSL WARNINGS ---
# This stops the console from being flooded with warnings because we are verifying=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
HISTORY_FILE = 'history.json'
HISTORY_LENGTH = 20  # 20 items * 30 sec = 10 mins
UPDATE_INTERVAL = 30 # Seconds

# This order is preserved in Python 3.7+ dictionaries
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
status_history = {} 
current_status = {}
last_check_time = None

def load_history():
    global status_history, last_check_time, current_status
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                loaded_history = data.get('history', {})
                status_history = {site: list(loaded_history.get(site, []))[-HISTORY_LENGTH:] for site in SITES}
                current_status = data.get('current', {})
                last_check_time = datetime.fromisoformat(data.get('last_check')) if data.get('last_check') else None
                logger.info("Loaded history from file.")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            status_history = {site: [] for site in SITES}
    else:
        status_history = {site: [] for site in SITES}

def save_history():
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

load_history()

def check_website(name, url):
    try:
        start_time = time.time()
        # USE A REAL BROWSER USER-AGENT TO AVOID BLOCKING
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        # verify=False ignores SSL certificate errors
        response = requests.get(url, timeout=10, headers=headers, verify=False)
        
        response_time = round((time.time() - start_time) * 1000)
        
        # Consider 200 (OK) as UP. Some redirects (301/302) might need handling, 
        # but requests follows redirects by default, so final code should be 200.
        return {
            'status': 'up' if response.status_code == 200 else 'down',
            'time': response_time,
            'code': response.status_code,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error checking {name}: {e}")
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
                current_status[name] = result
                
                if name not in status_history:
                    status_history[name] = []
                
                status_history[name].append(result)
                
                if len(status_history[name]) > HISTORY_LENGTH:
                    status_history[name].pop(0)
            
            last_check_time = datetime.now()
            save_history()
            logger.info(f"Check complete at {last_check_time}")
            
        except Exception as e:
            logger.error(f"Error in monitor loop: {e}")
        
        time.sleep(UPDATE_INTERVAL)

def get_site_data():
    data = {}
    # Iterate over SITES to preserve the order defined in the dictionary
    for name in SITES:
        history = status_history.get(name, [])
        if history:
            up_count = sum(1 for h in history if h['status'] == 'up')
            uptime = round((up_count / len(history)) * 100, 2)
        else:
            uptime = 0.0

        current = current_status.get(name, {'status': 'unknown', 'time': 0})

        data[name] = {
            'current': current,
            'uptime': uptime,
            'history': history,
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
    if os.environ.get('WERKZEUG_RUN_MAIN') or not app.debug:
        threading.Thread(target=monitor_loop, daemon=True).start()
        
    app.run(debug=True, host='0.0.0.0', port=5000)