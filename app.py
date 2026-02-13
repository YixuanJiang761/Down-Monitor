from flask import Flask, render_template, jsonify
from flask_cors import CORS
import requests
from datetime import datetime
import threading
import time
from collections import deque
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

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

# CONFIGURATION
# 30 seconds interval * 20 items = 600 seconds (10 Minutes)
HISTORY_LENGTH = 20 
UPDATE_INTERVAL = 30

status_history = {site: deque(maxlen=HISTORY_LENGTH) for site in SITES}
current_status = {}
last_check_time = None

def check_website(name, url):
    try:
        start_time = time.time()
        headers = {'User-Agent': 'UIUC-Status-Monitor/1.0'}
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
    logger.info("Monitor thread started")
    while True:
        try:
            for name, url in SITES.items():
                result = check_website(name, url)
                current_status[name] = result
                status_history[name].append(result)
            
            last_check_time = datetime.now()
            logger.info(f"Check complete at {last_check_time}")
        except Exception as e:
            logger.error(f"Error: {e}")
        
        time.sleep(UPDATE_INTERVAL)

# Start Background Thread
threading.Thread(target=monitor_loop, daemon=True).start()

def get_site_data():
    """Compiles the full data payload for frontend"""
    data = {}
    for name in SITES:
        history = list(status_history[name])
        
        # Calculate Uptime
        if history:
            up_count = sum(1 for h in history if h['status'] == 'up')
            uptime = round((up_count / len(history)) * 100, 2)
        else:
            uptime = 0.0

        # Extract History for Graph (Simple list of {time, status})
        graph_data = [{'time': h['time'], 'status': h['status']} for h in history]

        data[name] = {
            'current': current_status.get(name, {}),
            'uptime': uptime,
            'history': graph_data,
            'url': SITES[name]
        }
    
    return {
        'sites': data,
        'last_check': last_check_time.isoformat() if last_check_time else None
    }

@app.route('/')
def index():
    # Inject data directly into template for Instant Load
    return render_template('index.html', initial_data=get_site_data())

@app.route('/api/status')
def get_status():
    # API returns same structure for updates
    return jsonify(get_site_data())

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)