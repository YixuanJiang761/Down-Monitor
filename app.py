from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import threading
import time
import json
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
HISTORY_FILE = 'history.json'
HISTORY_LENGTH = 20  # 20 items * 30 sec = 10 mins
UPDATE_INTERVAL = 30 # Seconds

# NEW: Grouped Configuration
SERVICE_GROUPS = {
    'UIUC Services': {
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
    },
    'General Services': {
        'OpenAI (ChatGPT)': 'https://api.openai.com/v1/models', # API endpoint usually returns 401 (Auth required) or 200, good for uptime check
        'AWS (Amazon)': 'https://aws.amazon.com',
        'Google': 'https://www.google.com',
        'Microsoft': 'https://www.microsoft.com',
        'Apple': 'https://www.apple.com',
        'GitHub': 'https://github.com',
        'Chase Bank': 'https://www.chase.com',
        'Bank of America': 'https://www.bankofamerica.com',
        'PayPal': 'https://www.paypal.com',
        'Stripe': 'https://status.stripe.com'
    }
}

# Flattened list for easy history tracking key access
status_history = {}
current_status = {}
last_check_time = None

def load_history():
    """Load history from JSON file on startup"""
    global status_history, current_status, last_check_time
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                data = json.load(f)
                status_history = data.get('history', {})
                # Trim to max length
                for name in status_history:
                    status_history[name] = status_history[name][-HISTORY_LENGTH:]
                
                current_status = data.get('current', {})
                if data.get('last_check'):
                    last_check_time = datetime.fromisoformat(data.get('last_check'))
        except Exception as e:
            logger.error(f"Failed to load history: {e}")

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

# Load immediately
load_history()

def check_website(url):
    try:
        start_time = time.time()
        headers = {'User-Agent': 'UIUC-Status-Monitor/1.0'}
        
        # Note: OpenAI API returns 401 without key, which means it's UP. 
        # We treat any response (even 401/403) as UP because the server replied.
        response = requests.get(url, timeout=5, headers=headers)
        
        # Calculate response time
        response_time = round((time.time() - start_time) * 1000)
        
        # Consider it UP if we get a response, even if it's 401/403 (common for APIs/Banks)
        is_up = response.status_code in [200, 201, 202, 301, 302, 401, 403]
        
        return {
            'status': 'up' if is_up else 'down',
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
            # Iterate through Groups -> Sites
            for group, sites in SERVICE_GROUPS.items():
                for name, url in sites.items():
                    result = check_website(url)
                    
                    # Update Current
                    current_status[name] = result
                    
                    # Update History
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

def get_payload():
    """Format data for frontend groups"""
    groups_data = {}
    
    for group_name, sites in SERVICE_GROUPS.items():
        site_list = []
        for name, url in sites.items():
            history = status_history.get(name, [])
            
            # Calculate Uptime
            if history:
                up_count = sum(1 for h in history if h['status'] == 'up')
                uptime = round((up_count / len(history)) * 100, 1)
            else:
                uptime = 0.0
            
            # Add to list
            site_list.append({
                'name': name,
                'url': url,
                'uptime': uptime,
                'current': current_status.get(name, {'status': 'unknown', 'time': 0}),
                'history': history
            })
        
        # Sort alphabetically within group
        site_list.sort(key=lambda x: x['name'])
        groups_data[group_name] = site_list

    return {
        'last_check': last_check_time.isoformat() if last_check_time else None,
        'groups': groups_data
    }

@app.route('/')
def index():
    return render_template('index.html', initial_data=get_payload())

@app.route('/api/status')
def get_status():
    return jsonify(get_payload())

if __name__ == '__main__':
    # Prevent duplicate threads in debug mode
    if os.environ.get('WERKZEUG_RUN_MAIN') or not app.debug:
        threading.Thread(target=monitor_loop, daemon=True).start()
        
    app.run(debug=True, host='0.0.0.0', port=5000)