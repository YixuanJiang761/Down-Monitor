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
            'status': 'up'