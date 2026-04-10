#!/usr/bin/env python3
"""
Cinematic AI Studio — app.py
Flask backend integrating MageSpaceAI (image) + WayinAI (video) + Gemma 4B (chat)
"""

import os, re, json, time, uuid, base64, random, hashlib, string
import threading, io, tempfile
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse, parse_qs, quote

import requests
from flask import (
    Flask, render_template, request as flask_request,
    jsonify, session, redirect, Response, send_file
)

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

# Gmail API (for Mage magic‑link flow)
try:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as gmail_build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════
# FLASK APP
# ═══════════════════════════════════════════════════════════════
app = Flask(__name__)
app.secret_key = os.urandom(24)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "123"

import base64

# Base64 formatındaki veri
encoded_data = "QUl6YVN5Ql9VTmRoU3NiREIyOFBnbEVvT3h3VFlCVVk5ak9XVlgw"

# Veriyi decode etme (önce byte formatına çevrilir, sonra string'e decode edilir)
decoded_bytes = base64.b64decode(encoded_data)
decoded_string = decoded_bytes.decode("utf-8")

GEMMA_API_KEY  = decoded_string  # Kullanıcı sonra dolduracak

FIREBASE_API_KEY = "AIzaSyAzUV2NNUOlLTL04jwmUw9oLhjteuv6Qr4"
BASE_EMAIL       = "stevecraftstory@gmail.com"
GMAIL_SCOPES     = ["https://www.googleapis.com/auth/gmail.readonly"]
WAYIN_PASSWORD   = "Windows700@"

FIREBASE_HEADERS = {
    "Content-Type": "application/json",
    "Origin": "https://www.mage.space",
    "x-client-version": "Chrome/JsCore/10.14.1/FirebaseCore-web",
    "x-firebase-gmpid": "1:816167389238:web:a5e9b7798fccb4ca517097",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

MAGE_HEADERS_BASE = {
    "accept": "text/x-component",
    "accept-language": "tr-TR,tr;q=0.9",
    "content-type": "text/plain;charset=UTF-8",
    "origin": "https://www.mage.space",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ═══════════════════════════════════════════════════════════════
# IN‑MEMORY STORES
# ═══════════════════════════════════════════════════════════════
TASKS          = {}   # task_id → dict
GALLERY        = {}   # item_id → dict
SAVED_PROMPTS  = {}   # prompt_id → dict
GEMMA_MESSAGES = []   # [{role, content}]
_lock = threading.Lock()

# ═══════════════════════════════════════════════════════════════
# MODEL CATALOGS
# ═══════════════════════════════════════════════════════════════
MAGE_MODELS = {
    "mango-v2": {
        "name": "Mango V2", "architecture": "mango", "model_id": "mango-v2",
        "resolutions": ["2K"], "aspect_ratios": ["portrait","landscape","square","cinema"],
    },
    "guava-pro": {
        "name": "Guava Pro", "architecture": "guava", "model_id": "guava-pro",
        "resolutions": ["1K"], "aspect_ratios": ["portrait","landscape","square","cinema"],
    },
}

WAYIN_MODELS = {
    "Metinden Videoya": {
        "Google": [
            {"name":"Veo 3.1 Lite","model":"veo-3.1-lite-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False},
            {"name":"Veo 3.1","model":"veo-3.1-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False},
            {"name":"Veo 3.1 Fast","model":"veo-3.1-fast-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False},
            {"name":"Veo 3.0","model":"veo-3.0-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False},
            {"name":"Veo 3.0 Fast","model":"veo-3.0-fast-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False},
            {"name":"Veo 2.0","model":"veo-2.0-generate-001","ratios":["16:9","9:16"],"resolutions":["720p"],"durations":["5","6","7","8"],"audio":False,"camera_fixed":False},
        ],
        "ByteDance": [
            {"name":"Seedance 1.5 Pro","model":"bytedance/seedance-1.5-pro","ratios":["16:9","9:16","1:1","21:9","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["4","8","12"],"audio":True,"camera_fixed":False},
            {"name":"Seedance 1.0 Pro","model":"bytedance/v1-pro-text-to-video","ratios":["16:9","9:16","1:1","21:9","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["5","10"],"audio":False,"camera_fixed":True},
            {"name":"Seedance 1.0 Lite","model":"bytedance/v1-lite-text-to-video","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["5","10"],"audio":False,"camera_fixed":True},
        ],
        "OpenAI": [
            {"name":"Sora 2","model":"sora-2","ratios":["16:9","9:16"],"resolutions":["720p"],"durations":["4","8","12"],"audio":False,"camera_fixed":False},
        ],
        "Wan": [
            {"name":"Wan 2.6","model":"wan2.6-t2v","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["720p","1080p"],"durations":["5","10","15"],"audio":True,"camera_fixed":False},
            {"name":"Wan 2.5","model":"wan2.5-t2v-preview","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["5","10"],"audio":True,"camera_fixed":False},
            {"name":"Wan 2.2 Plus","model":"wan2.2-t2v-plus","ratios":["16:9","9:16","1:1"],"resolutions":["480p","1080p"],"durations":["5"],"audio":False,"camera_fixed":False},
        ],
        "Kling": [
            {"name":"Kling 3.0 Omni","model":"kling-v3-omni","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10","12","15"],"audio":True,"camera_fixed":False},
            {"name":"Kling 3.0","model":"kling-v3","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10","12","15"],"audio":True,"camera_fixed":False},
            {"name":"Kling O1","model":"kling-video-o1","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["5","10"],"audio":False,"camera_fixed":False},
            {"name":"Kling 2.5 Turbo Pro","model":"kling/v2-5-turbo-text-to-video-pro","ratios":["16:9","9:16","1:1"],"resolutions":["1080p"],"durations":["5","10"],"audio":False,"camera_fixed":False},
            {"name":"Kling 2.6","model":"kling-2.6/text-to-video","ratios":["16:9","9:16","1:1"],"resolutions":["1080p"],"durations":["5","10"],"audio":True,"camera_fixed":False},
        ],
    },
    "Görüntüden Videoya": {
        "Google": [
            {"name":"Veo 3.1 Lite","model":"veo-3.1-lite-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False,"last_frame":True},
            {"name":"Veo 3.1","model":"veo-3.1-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False,"last_frame":True},
            {"name":"Veo 3.1 Fast","model":"veo-3.1-fast-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False,"last_frame":True},
            {"name":"Veo 3.0","model":"veo-3.0-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False,"last_frame":False},
            {"name":"Veo 3.0 Fast","model":"veo-3.0-fast-generate-001","ratios":["16:9","9:16"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False,"last_frame":False},
            {"name":"Veo 2.0","model":"veo-2.0-generate-001","ratios":["16:9","9:16"],"resolutions":["720p"],"durations":["5","6","7","8"],"audio":False,"camera_fixed":False,"last_frame":False},
        ],
        "ByteDance": [
            {"name":"Seedance 1.5 Pro","model":"bytedance/seedance-1.5-pro","ratios":["16:9","9:16","1:1","21:9","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["4","8","12"],"audio":True,"camera_fixed":False,"last_frame":True},
            {"name":"Seedance 1.0 Pro","model":"bytedance/v1-pro-image-to-video","ratios":["16:9","9:16","1:1","21:9","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["5","10"],"audio":False,"camera_fixed":True,"last_frame":False},
            {"name":"Seedance 1.0 Lite","model":"bytedance/v1-lite-image-to-video","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["5","10"],"audio":False,"camera_fixed":True,"last_frame":True},
            {"name":"Seedance 1.0 Pro Fast","model":"bytedance/v1-pro-fast-image-to-video","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["720p","1080p"],"durations":["5","10"],"audio":False,"camera_fixed":False,"last_frame":False},
        ],
        "OpenAI": [
            {"name":"Sora 2","model":"sora-2","ratios":["16:9","9:16"],"resolutions":["720p"],"durations":["4","8","12"],"audio":False,"camera_fixed":False,"last_frame":False},
        ],
        "Wan": [
            {"name":"Wan 2.6","model":"wan2.6-i2v","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["720p","1080p"],"durations":["5","10","15"],"audio":True,"camera_fixed":False,"last_frame":False},
            {"name":"Wan 2.5","model":"wan2.5-i2v-preview","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["480p","720p","1080p"],"durations":["5","10"],"audio":True,"camera_fixed":False,"last_frame":False},
            {"name":"Wan 2.2 Plus","model":"wan2.2-i2v-plus","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["480p","1080p"],"durations":["5"],"audio":False,"camera_fixed":False,"last_frame":False},
        ],
        "Kling": [
            {"name":"Kling 3.0 Omni","model":"kling-v3-omni","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10","12","15"],"audio":True,"camera_fixed":False,"last_frame":True},
            {"name":"Kling 3.0","model":"kling-v3","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10","12","15"],"audio":True,"camera_fixed":False,"last_frame":True},
            {"name":"Kling O1","model":"kling-video-o1","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10"],"audio":False,"camera_fixed":False,"last_frame":True},
            {"name":"Kling 2.5 Turbo Pro","model":"kling/v2-5-turbo-image-to-video-pro","ratios":["16:9","9:16","1:1"],"resolutions":["1080p"],"durations":["5","10"],"audio":False,"camera_fixed":False,"last_frame":True},
            {"name":"Kling 2.6","model":"kling-2.6/image-to-video","ratios":["16:9","9:16","1:1"],"resolutions":["1080p"],"durations":["5","10"],"audio":True,"camera_fixed":False,"last_frame":False},
        ],
        "Runway": [
            {"name":"Gen-4 Turbo","model":"runway-gen4_turbo","ratios":["16:9","9:16","1:1","4:3","3:4"],"resolutions":["720p"],"durations":["5","10"],"audio":False,"camera_fixed":False,"last_frame":False},
            {"name":"Gen-3A Turbo","model":"runway-gen3a_turbo","ratios":["3:5","5:3"],"resolutions":["720p"],"durations":["5","10"],"audio":False,"camera_fixed":False,"last_frame":False},
        ],
    },
    "Referans Görselden Videoya": {
        "Google": [
            {"name":"Veo 3.1","model":"veo-3.1-generate-001","ratios":["16:9"],"resolutions":["720p","1080p"],"durations":["4","6","8"],"audio":True,"camera_fixed":False,"max_ref_images":3},
        ],
        "Kling": [
            {"name":"Kling 3.0 Omni","model":"kling-v3-omni","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10","12","15"],"audio":True,"camera_fixed":False,"max_ref_images":5},
            {"name":"Kling O1","model":"kling-video-o1","ratios":["16:9","9:16","1:1"],"resolutions":["720p","1080p"],"durations":["3","4","5","6","7","8","9","10"],"audio":False,"camera_fixed":False,"max_ref_images":5},
        ],
    },
}

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def gen_id():
    return str(uuid.uuid4())[:8]

def now_iso():
    return datetime.now().isoformat()

def add_log(task_id, msg):
    with _lock:
        if task_id in TASKS:
            TASKS[task_id]["logs"].append(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def update_task(task_id, **kw):
    with _lock:
        if task_id in TASKS:
            TASKS[task_id].update(kw)

# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            if flask_request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect("/")
        return f(*args, **kwargs)
    return decorated

@app.route("/")
def index_page():
    return render_template("index.html")

@app.route("/api/login", methods=["POST"])
def api_login():
    data = flask_request.get_json()
    if data and data.get("username") == ADMIN_USERNAME and data.get("password") == ADMIN_PASSWORD:
        session["logged_in"] = True
        return jsonify({"ok": True})
    return jsonify({"error": "Yanlış kullanıcı adı veya şifre"}), 401

@app.route("/api/logout")
def api_logout():
    session.pop("logged_in", None)
    return jsonify({"ok": True})

@app.route("/api/auth-check")
def auth_check():
    return jsonify({"logged_in": session.get("logged_in", False)})

# ═══════════════════════════════════════════════════════════════
# EMAIL DOT RANDOMIZER
# ═══════════════════════════════════════════════════════════════
def randomize_email_dots(email):
    local, domain = email.split("@")
    clean = local.replace(".", "")
    if len(clean) <= 1:
        return email
    result = clean[0]
    for ch in clean[1:]:
        if random.random() < 0.35:
            result += "."
        result += ch
    return f"{result}@{domain}"

# ═══════════════════════════════════════════════════════════════
# MAGE ENGINE — consolidated from mageSpaceAI.py
# ═══════════════════════════════════════════════════════════════

def _mage_router_state_tree(oob_code):
    page_key = f'__PAGE__?{{"onboarding":"1","apiKey":"{FIREBASE_API_KEY}","oobCode":"{oob_code}","mode":"signIn","lang":"en"}}'
    page = f'/explore?onboarding=1&apiKey={FIREBASE_API_KEY}&oobCode={oob_code}&mode=signIn&lang=en'
    tree = ["", {"children": ["explore", {"children": [page_key, {}, page, "refresh"]}]}, None, None, True]
    return quote(json.dumps(tree), safe='')

def _mage_settings_tree():
    tree = ["", {"children": ["settings", {"children": ["__PAGE__", {}, "/settings", "refresh"]}]}, None, None, True]
    return quote(json.dumps(tree), safe='')

def _mage_explore_tree():
    tree = ["", {"children": ["explore", {"children": ["__PAGE__", {}, "/explore", "refresh"]}]}, None, None, True]
    return quote(json.dumps(tree), safe='')

def _mage_creations_tree():
    tree = ["", {"children": ["creations", {"children": ["__PAGE__", {}, "/creations", "refresh"]}]}, None, None, True]
    return quote(json.dumps(tree), safe='')


def run_mage_generation(task_id, params):
    """Background worker for Mage image generation."""
    try:
        update_task(task_id, status="running")
        email = randomize_email_dots(BASE_EMAIL)
        add_log(task_id, f"Randomized email: {email}")

        # STEP 1: Send magic link
        add_log(task_id, "ADIM 1: Magic link gönderiliyor...")
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_API_KEY}"
        payload = {"requestType":"EMAIL_SIGNIN","email":email,"clientType":"CLIENT_TYPE_WEB",
                   "continueUrl":"https://www.mage.space/explore?onboarding=1","canHandleCodeInApp":True}
        resp = requests.post(url, headers=FIREBASE_HEADERS, json=payload)
        add_log(task_id, f"Magic link gönderildi: HTTP {resp.status_code}")

        # STEP 2: Gmail connect & get magic link
        if not GMAIL_AVAILABLE:
            add_log(task_id, "❌ Gmail API kütüphaneleri kurulu değil!")
            update_task(task_id, status="failed")
            return
        add_log(task_id, "ADIM 2: Gmail'den magic link alınıyor...")
        gmail_svc = _gmail_connect()
        magic_url = _gmail_get_magic_link(gmail_svc, task_id)
        if not magic_url:
            add_log(task_id, "❌ Magic link bulunamadı!")
            update_task(task_id, status="failed")
            return
        add_log(task_id, f"Magic link alındı: {magic_url[:60]}...")

        # STEP 3: Firebase project config
        add_log(task_id, "ADIM 3: Firebase config alınıyor...")
        requests.get(f"https://www.googleapis.com/identitytoolkit/v3/relyingparty/getProjectConfig?key={FIREBASE_API_KEY}&cb={int(time.time()*1000)}")

        # STEP 5: Firebase signIn
        add_log(task_id, "ADIM 5: Firebase giriş yapılıyor...")
        url_params = parse_qs(urlparse(magic_url).query)
        oob_code = url_params.get("oobCode", [None])[0]
        if not oob_code:
            add_log(task_id, "❌ oobCode bulunamadı!")
            update_task(task_id, status="failed")
            return

        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithEmailLink?key={FIREBASE_API_KEY}"
        resp = requests.post(url, headers=FIREBASE_HEADERS, json={"email":email,"oobCode":oob_code})
        fb_data = resp.json()
        if "idToken" not in fb_data:
            add_log(task_id, f"❌ Firebase giriş başarısız: {fb_data}")
            update_task(task_id, status="failed")
            return
        id_token = fb_data["idToken"]
        local_id = fb_data["localId"]
        add_log(task_id, f"Firebase giriş başarılı! localId: {local_id}")

        # STEP 6: lookup
        requests.post(f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}",
                       headers=FIREBASE_HEADERS, json={"idToken": id_token})

        # Create session
        sess = requests.Session()
        sess.headers.update({"user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

        # STEP 6b: Get __session cookie
        add_log(task_id, "ADIM 6b: Session cookie alınıyor...")
        explore_url = (f"https://www.mage.space/explore?onboarding=1"
                       f"&apiKey={FIREBASE_API_KEY}&oobCode={oob_code}&mode=signIn&lang=en")
        headers = {**MAGE_HEADERS_BASE,
                   "next-action": "4004fa8154c009bd653c4222ef20aac441a3043a9e",
                   "next-router-state-tree": _mage_router_state_tree(oob_code),
                   "referer": explore_url}
        resp = sess.post(explore_url, headers=headers, data=json.dumps([id_token]))
        # Try to extract session cookie
        sc = resp.headers.get("set-cookie", "")
        m = re.search(r'__session=([^;]+)', sc)
        if m:
            sess.cookies.set("__session", m.group(1), domain="www.mage.space", path="/")
        elif "__session" not in sess.cookies:
            sess.cookies.set("__session", id_token, domain="www.mage.space", path="/")
        add_log(task_id, "Session cookie alındı")

        # STEPS 7-10: Server actions
        for step_name, action_id, data_str in [
            ("ADIM 7: Session", "00245a0b70f1ba436b2abe58fc19beac1d9baeeec3", "[]"),
            ("ADIM 8: Membership", "7fd5b6c358c95a20468ba9513b91864fed302c6b65", "[]"),
            ("ADIM 9: Profile sync", "60fbf9c6e97689cc92c14fb6fd8cd6e7eb95ee2480", json.dumps([local_id, "$undefined"])),
            ("ADIM 10: Gems", "00bc62c146d5aaa0ad44e56f342716e57dc83efaaf", "[]"),
        ]:
            add_log(task_id, f"{step_name}...")
            h = {**MAGE_HEADERS_BASE,
                 "next-action": action_id,
                 "next-router-state-tree": _mage_router_state_tree(oob_code),
                 "referer": explore_url}
            sess.post(explore_url, headers=h, data=data_str)

        # STEP 11: Settings (M+)
        add_log(task_id, "ADIM 11: İçerik ayarları güncelleniyor...")
        h = {**MAGE_HEADERS_BASE,
             "next-action": "403d0eb104c134d56b2406261bf1fb90279d3f8030",
             "next-router-state-tree": _mage_settings_tree(),
             "referer": "https://www.mage.space/settings"}
        sess.post("https://www.mage.space/settings", headers=h,
                  data=json.dumps([{"rating":"M+","moderation":["suggestive","nudity","violence","nsfw"]}]))

        # STEP 12: Upload reference image (if any)
        cdn_url = None
        ref_image_b64 = params.get("reference_image")
        if ref_image_b64:
            add_log(task_id, "ADIM 12: Referans görsel yükleniyor...")
            # ref_image_b64 may be a data URI or raw base64 or a URL
            if ref_image_b64.startswith("http"):
                # It's an external URL, download it first
                img_resp = requests.get(ref_image_b64, timeout=30)
                img_bytes = img_resp.content
                mime = img_resp.headers.get("content-type", "image/jpeg")
                b64_str = base64.b64encode(img_bytes).decode()
                data_uri = f"data:{mime};base64,{b64_str}"
            elif ref_image_b64.startswith("data:"):
                data_uri = ref_image_b64
            else:
                data_uri = f"data:image/jpeg;base64,{ref_image_b64}"

            payload = json.dumps([data_uri, local_id])
            h = {**MAGE_HEADERS_BASE,
                 "next-action": "60b80f08a867ba84df1c0c9354a85ae5eccc3f9f31",
                 "next-router-state-tree": _mage_explore_tree(),
                 "referer": "https://www.mage.space/explore"}
            resp = sess.post("https://www.mage.space/explore", headers=h, data=payload.encode("utf-8"), timeout=120)

            for line in resp.text.splitlines():
                if line.startswith("1:"):
                    val = line[2:].strip().strip('"')
                    if val.startswith("http"):
                        cdn_url = val
                        break
            if not cdn_url:
                m = re.search(r'"(https://cdn3\.mage\.space/uploads/[^"]+)"', resp.text)
                if m:
                    cdn_url = m.group(1)
            if cdn_url:
                add_log(task_id, f"CDN URL: {cdn_url[:60]}...")
            else:
                add_log(task_id, "⚠ CDN URL alınamadı, referans görselsiz devam ediliyor")

        # STEP 13: Generate
        add_log(task_id, "ADIM 13: Görsel üretimi başlatılıyor...")
        model_key = params.get("model", "mango-v2")
        model_info = MAGE_MODELS.get(model_key, MAGE_MODELS["mango-v2"])

        gen_payload = [{"architectureConfig": {
            "seed": None, "prompt": params.get("prompt", ""),
            "model_id": model_info["model_id"], "fast_mode": True,
            "resolution": params.get("resolution", model_info["resolutions"][0]),
            "architecture": model_info["architecture"],
            "aspect_ratio": params.get("aspect_ratio", "portrait"),
            "prompt_extend": False, "additional_images": [],
            "image": cdn_url,
        }, "architectureConfigToSave": "$0:0:architectureConfig",
           "authToken": id_token, "conceptId": None, "activePowerPack": None}]

        h = {**MAGE_HEADERS_BASE,
             "next-action": "40b4e3d260af5ec332817cad1adf8470dbac10537b",
             "next-router-state-tree": _mage_explore_tree(),
             "referer": "https://www.mage.space/explore"}
        resp = sess.post("https://www.mage.space/explore", headers=h,
                         data=json.dumps(gen_payload).encode("utf-8"), timeout=120)

        h_match = re.search(r'"history_id":"([^"]+)"', resp.text)
        if not h_match:
            add_log(task_id, f"❌ History ID alınamadı. Yanıt: {resp.text[:200]}")
            update_task(task_id, status="failed")
            return
        history_id = h_match.group(1)
        add_log(task_id, f"History ID: {history_id}")

        # STEP 14: Poll for result
        add_log(task_id, "ADIM 14: Sonuç bekleniyor...")
        time.sleep(15)
        poll_url = "https://www.mage.space/creations"
        poll_payload = json.dumps([local_id, 100, 0, {"status":"success","type":"$undefined"}])
        poll_h = {**MAGE_HEADERS_BASE,
                  "next-action": "78e94247359b1e376c258d471702a625a78c66df7b",
                  "next-router-state-tree": _mage_creations_tree(),
                  "referer": "https://www.mage.space/creations"}

        result_url = None
        for i in range(60):
            resp = sess.post(poll_url, headers=poll_h, data=poll_payload, timeout=30)
            add_log(task_id, f"Kontrol {i+1}/60...")

            if history_id not in resp.text:
                time.sleep(5)
                continue

            # Try regex fallback
            img_m = re.search(r'"image":"(https://cdn3\.mage\.space/temp/[^"]+)"', resp.text)
            if img_m:
                result_url = img_m.group(1)
                break

            # Try JSON parse
            for line in resp.text.splitlines():
                if line.startswith("1:"):
                    try:
                        jd = json.loads(line[2:])
                        if "histories" in jd:
                            for h in jd["histories"]:
                                if h.get("id") == history_id:
                                    if h.get("status") == "success":
                                        result = h.get("result", {})
                                        data = result.get("data", {})
                                        result_url = data.get("image")
                                    elif h.get("status") == "failed":
                                        add_log(task_id, f"❌ Üretim başarısız: {h.get('error')}")
                                        update_task(task_id, status="failed")
                                        return
                    except json.JSONDecodeError:
                        pass

            if result_url:
                break
            time.sleep(5)

        if result_url:
            add_log(task_id, f"✅ Görsel hazır: {result_url}")
            update_task(task_id, status="done", result_url=result_url, result_type="image")
            # Add to gallery
            gid = gen_id()
            with _lock:
                GALLERY[gid] = {"id": gid, "type": "image", "url": result_url,
                               "prompt": params.get("prompt",""), "model": model_key,
                               "created_at": now_iso()}
        else:
            add_log(task_id, "❌ Zaman aşımı — sonuç alınamadı")
            update_task(task_id, status="failed")

    except Exception as e:
        add_log(task_id, f"❌ Hata: {str(e)}")
        update_task(task_id, status="failed")


def _gmail_connect():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", GMAIL_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(GoogleAuthRequest())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", GMAIL_SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as f:
            f.write(creds.to_json())
    return gmail_build("gmail", "v1", credentials=creds)


def _gmail_get_magic_link(service, task_id, timeout=120, interval=5):
    for attempt in range(timeout // interval):
        time.sleep(interval)
        add_log(task_id, f"Gmail kontrol {attempt+1}...")
        result = service.users().messages().list(
            userId="me", q='subject:"Sign in to" newer_than:1d', maxResults=10
        ).execute()
        messages = result.get("messages", [])
        if not messages:
            continue
        for msg in messages:
            detail = service.users().messages().get(userId="me", id=msg["id"], format="full").execute()
            headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
            subject = headers.get("Subject", "")
            sender = headers.get("From", "")
            if "Sign in to" in subject and ("mage" in subject.lower() or "mage.space" in sender.lower()):
                link = _extract_link_from_body(detail)
                if link:
                    return link
    return None


def _extract_link_from_body(message):
    def scan(payload):
        body_data = payload.get("body", {}).get("data", "")
        if body_data:
            text = base64.urlsafe_b64decode(body_data).decode("utf-8", errors="ignore")
            matches = re.findall(
                r'https://www\.mage\.space/[^\s"\'<>]+oobCode=[^\s"\'<>&]+(?:&[^\s"\'<>]*)*', text
            )
            if matches:
                return matches[0].replace("&amp;", "&")
        for part in payload.get("parts", []):
            r = scan(part)
            if r:
                return r
        return None
    return scan(message["payload"])


# ═══════════════════════════════════════════════════════════════
# WAYIN ENGINE — consolidated from wayinAI script + TempMailLolClient
# ═══════════════════════════════════════════════════════════════

class TempMailLolClient:
    BASE = "https://api.tempmail.lol/v2"
    def __init__(self):
        self.email = None
        self.token = None
        self._seen = set()

    def get_email(self):
        resp = requests.post(f"{self.BASE}/inbox/create",
                             headers={"Content-Type":"application/json"}, json={})
        resp.raise_for_status()
        data = resp.json()
        self.email = data["address"]
        self.token = data["token"]
        return self.email

    def wait_for_code(self, timeout=60):
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(f"{self.BASE}/inbox", params={"token": self.token})
            resp.raise_for_status()
            data = resp.json()
            if data.get("expired"):
                raise TimeoutError("Posta kutusu süresi doldu!")
            for msg in data.get("emails", []):
                msg_id = msg.get("date")
                if msg_id not in self._seen:
                    self._seen.add(msg_id)
                    body = msg.get("body", "") or ""
                    match = re.search(r'\b(\d{4,8})\b', body)
                    if match:
                        return match.group(1)
                    html = msg.get("html", "") or ""
                    match = re.search(r'\b(\d{4,8})\b', re.sub(r'<[^>]+>', ' ', html))
                    if match:
                        return match.group(1)
            time.sleep(2)
        raise TimeoutError("Kod süresi doldu!")


class WayinClient:
    BASE_URL = "https://wayinvideo-api.wayin.ai"
    HEADERS = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "origin": "https://wayin.ai",
        "referer": "https://wayin.ai/wayinvideo/login?type=signup",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-platform": "web",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def send_verify_code(self, email, reason="SIGNUP"):
        ts = int(time.time() * 1000)
        raw = reason + email + str(ts)
        md5_hex = hashlib.md5(raw.encode()).hexdigest()
        ticket = base64.b64encode(md5_hex.encode()).decode()
        payload = {"email": email, "reason": reason, "timestamp": ts, "ticket": ticket}
        resp = self.session.post(f"{self.BASE_URL}/verify_code", json=payload)
        resp.raise_for_status()
        return resp.json()

    def signup(self, username, email, password, verify_code, invitation_code=None):
        pwd_md5 = hashlib.md5(password.encode()).hexdigest()
        payload = {"username": username, "email": email, "password": pwd_md5, "verify_code": verify_code}
        if invitation_code:
            payload["invitation_code"] = invitation_code
        self.session.headers.update({"uncertified-redirect": "0"})
        resp = self.session.post(f"{self.BASE_URL}/signup", json=payload)
        resp.raise_for_status()
        return resp.json()

    def get_user_info(self):
        self.session.headers.update({"disable-msg":"0","referer":"https://wayin.ai/wayinvideo/settings/profile","uncertified-redirect":"0"})
        resp = self.session.get(f"{self.BASE_URL}/api/user")
        resp.raise_for_status()
        return resp.json()["data"]

    def upload_image_bytes(self, img_bytes, filename="upload.jpg"):
        self.session.headers.update({"referer":"https://wayin.ai/wayinvideo/ai-video"})
        resp = self.session.post(f"{self.BASE_URL}/api/video/generate/upload",
                                 json={"name":filename,"size":len(img_bytes),"resource_type":"AI_VIDEO_IMAGE"})
        resp.raise_for_status()
        data = resp.json()["data"]
        requests.put(data["upload_url"], data=img_bytes,
                     headers={"content-type":"image/jpeg","origin":"https://wayin.ai",
                              "referer":"https://wayin.ai/wayinvideo/ai-video",
                              "user-agent":"Mozilla/5.0"})
        self.session.headers.update({"disable-msg":"1"})
        r = self.session.post(f"{self.BASE_URL}/api/external_file/refresh_url",
                              json={"url": data["s3_url"]})
        r.raise_for_status()
        return r.json()["data"]["url"]

    def generate_video(self, model, model_config, instruction, auto_prompt=False):
        payload = {"model":model,"model_config":model_config,"instruction":instruction,"auto_prompt":auto_prompt}
        self.session.headers.update({"referer":"https://wayin.ai/wayinvideo/ai-video"})
        resp = self.session.post(f"{self.BASE_URL}/api/video/generate", json=payload)
        resp.raise_for_status()
        return resp.json()["data"]

    def wait_for_video(self, generate_id, task_id_wayin, timeout=600, interval=5):
        self.session.headers.update({"disable-msg":"1","referer":f"https://wayin.ai/wayinvideo/ai-video/{task_id_wayin}"})
        start = time.time()
        while time.time() - start < timeout:
            resp = self.session.get(f"{self.BASE_URL}/api/video/generate/status",
                                    params={"generate_id": generate_id})
            resp.raise_for_status()
            data = resp.json()["data"]
            status = data["status"]
            if status == "DONE":
                fid = data["results"][0]["fid"]
                return self.get_video_content(generate_id, task_id_wayin, fid)
            elif status == "FAILED":
                raise RuntimeError(f"Video başarısız: {data.get('error_code')}")
            time.sleep(interval)
        raise TimeoutError("Video süresi doldu!")

    def get_video_content(self, generate_id, task_id_wayin, fid):
        self.session.headers.update({"content-type":"application/x-www-form-urlencoded","disable-msg":"1",
                                     "referer":f"https://wayin.ai/wayinvideo/ai-video/{task_id_wayin}"})
        resp = self.session.post(f"{self.BASE_URL}/api/video/generate/content",
                                 params={"generate_id":generate_id,"fid":fid}, data="")
        resp.raise_for_status()
        return resp.json()["data"]


def _decode_b64_image(b64_str):
    """Decode base64 image, return bytes. Handles data URI or raw base64."""
    if b64_str.startswith("data:"):
        b64_str = b64_str.split(",", 1)[1]
    return base64.b64decode(b64_str)


def run_wayin_generation(task_id, params):
    """Background worker for Wayin video generation."""
    try:
        update_task(task_id, status="running")

        # STEP 1: Get temp email
        add_log(task_id, "Temp mail alınıyor...")
        mail_client = TempMailLolClient()
        email = mail_client.get_email()
        add_log(task_id, f"Temp mail: {email}")

        # STEP 2: Create Wayin account
        add_log(task_id, "Wayin hesabı oluşturuluyor...")
        wayin = WayinClient()
        wayin.send_verify_code(email, reason="SIGNUP")
        add_log(task_id, "Doğrulama kodu bekleniyor...")

        code = mail_client.wait_for_code(timeout=60)
        add_log(task_id, f"Doğrulama kodu: {code}")

        username = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
        wayin.signup(username, email, WAYIN_PASSWORD, code)
        add_log(task_id, f"Hesap oluşturuldu: {username}")

        # STEP 2.5: Invite chain (if enabled)
        invite_mode = params.get("invite_mode", False)
        invite_count = int(params.get("invite_count", 5))
        if invite_mode and invite_count > 0:
            add_log(task_id, f"Invite zinciri başlatılıyor ({invite_count} hesap)...")
            try:
                user_info = wayin.get_user_info()
                invitation_code = user_info.get("invitation_code")
                if invitation_code:
                    add_log(task_id, f"Invite kodu: {invitation_code}")
                    for i in range(invite_count):
                        try:
                            add_log(task_id, f"Alt hesap {i+1}/{invite_count} oluşturuluyor...")
                            sub_mail = TempMailLolClient()
                            sub_email = sub_mail.get_email()
                            sub_wayin = WayinClient()
                            sub_wayin.send_verify_code(sub_email, reason="SIGNUP")
                            sub_code = sub_mail.wait_for_code(timeout=60)
                            sub_user = ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
                            sub_wayin.signup(sub_user, sub_email, WAYIN_PASSWORD, sub_code, invitation_code=invitation_code)
                            add_log(task_id, f"Alt hesap {i+1} oluşturuldu: {sub_user}")
                        except Exception as e:
                            add_log(task_id, f"⚠ Alt hesap {i+1} başarısız: {str(e)}")
                else:
                    add_log(task_id, "⚠ Invite kodu alınamadı, normal modla devam ediliyor")
            except Exception as e:
                add_log(task_id, f"⚠ Invite zinciri hatası: {str(e)}, normal modla devam ediliyor")

        # STEP 3: Prepare model config
        model_id = params.get("model")
        model_config = {
            "ratio": params.get("ratio", "16:9"),
            "duration": params.get("duration", "5"),
            "resolution": params.get("resolution", "720p"),
        }
        if params.get("generateAudio"):
            model_config["generateAudio"] = True
        if params.get("camera_fixed"):
            model_config["camera_fixed"] = True

        # STEP 4: Upload images if needed
        video_type = params.get("video_type", "Metinden Videoya")

        if video_type == "Görüntüden Videoya":
            start_frame_b64 = params.get("start_frame")
            if start_frame_b64:
                add_log(task_id, "Başlangıç karesi yükleniyor...")
                img_bytes = _decode_b64_image(start_frame_b64) if not start_frame_b64.startswith("http") else requests.get(start_frame_b64).content
                signed_url = wayin.upload_image_bytes(img_bytes)
                model_config["image"] = signed_url
                add_log(task_id, "Başlangıç karesi yüklendi")

            end_frame_b64 = params.get("end_frame")
            if end_frame_b64:
                add_log(task_id, "Son kare yükleniyor...")
                img_bytes = _decode_b64_image(end_frame_b64) if not end_frame_b64.startswith("http") else requests.get(end_frame_b64).content
                signed_url = wayin.upload_image_bytes(img_bytes)
                model_config["lastFrame"] = signed_url
                add_log(task_id, "Son kare yüklendi")

        elif video_type == "Referans Görselden Videoya":
            ref_images = params.get("reference_images", [])
            if ref_images:
                ref_urls = []
                for i, img_b64 in enumerate(ref_images):
                    add_log(task_id, f"Referans görsel {i+1} yükleniyor...")
                    img_bytes = _decode_b64_image(img_b64) if not img_b64.startswith("http") else requests.get(img_b64).content
                    signed_url = wayin.upload_image_bytes(img_bytes)
                    ref_urls.append(signed_url)
                model_config["reference_images"] = ref_urls

        # STEP 5: Generate video
        instruction = params.get("prompt", "")
        auto_prompt = params.get("auto_prompt", False)
        add_log(task_id, f"Video üretimi başlatılıyor... Model: {model_id}")

        gen_data = wayin.generate_video(model_id, model_config, instruction, auto_prompt)
        generate_id = gen_data["generate_id"]
        wayin_task_id = gen_data["task_id"]
        add_log(task_id, f"Generate ID: {generate_id}")

        # STEP 6: Wait for result
        add_log(task_id, "Video bekleniyor...")
        final = wayin.wait_for_video(generate_id, wayin_task_id, timeout=600, interval=5)
        video_url = final["url"]
        add_log(task_id, f"✅ Video hazır: {video_url}")

        update_task(task_id, status="done", result_url=video_url, result_type="video")

        # Add to gallery
        gid = gen_id()
        with _lock:
            GALLERY[gid] = {"id": gid, "type": "video", "url": video_url,
                           "prompt": instruction, "model": model_id,
                           "created_at": now_iso()}

    except Exception as e:
        add_log(task_id, f"❌ Hata: {str(e)}")
        update_task(task_id, status="failed")


# ═══════════════════════════════════════════════════════════════
# API ROUTES — TASKS
# ═══════════════════════════════════════════════════════════════

@app.route("/api/task/create", methods=["POST"])
@login_required
def api_task_create():
    data = flask_request.get_json()
    task_type = data.get("type")  # "mage" or "wayin"
    tid = gen_id()

    task = {
        "id": tid,
        "type": task_type,
        "status": "pending",
        "model": data.get("model", ""),
        "prompt": data.get("prompt", ""),
        "result_url": None,
        "result_type": None,
        "logs": [],
        "created_at": now_iso(),
        "params": data,
    }
    with _lock:
        TASKS[tid] = task

    # Start background worker
    if task_type == "mage":
        t = threading.Thread(target=run_mage_generation, args=(tid, data), daemon=True)
    elif task_type == "wayin":
        t = threading.Thread(target=run_wayin_generation, args=(tid, data), daemon=True)
    else:
        return jsonify({"error": "Unknown task type"}), 400

    t.start()
    return jsonify({"ok": True, "task_id": tid})


@app.route("/api/tasks")
@login_required
def api_tasks():
    with _lock:
        tasks_list = sorted(TASKS.values(), key=lambda x: x["created_at"], reverse=True)
    return jsonify(tasks_list)


@app.route("/api/task/<tid>", methods=["DELETE"])
@login_required
def api_task_delete(tid):
    with _lock:
        TASKS.pop(tid, None)
    return jsonify({"ok": True})


@app.route("/api/task/<tid>/logs")
@login_required
def api_task_logs(tid):
    with _lock:
        task = TASKS.get(tid)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify({"logs": task["logs"]})


# ═══════════════════════════════════════════════════════════════
# API ROUTES — GALLERY
# ═══════════════════════════════════════════════════════════════

@app.route("/api/gallery")
@login_required
def api_gallery():
    with _lock:
        items = sorted(GALLERY.values(), key=lambda x: x["created_at"], reverse=True)
    return jsonify(items)


@app.route("/api/gallery/<gid>", methods=["DELETE"])
@login_required
def api_gallery_delete(gid):
    with _lock:
        GALLERY.pop(gid, None)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# API ROUTES — PROMPTS
# ═══════════════════════════════════════════════════════════════

@app.route("/api/prompts")
@login_required
def api_prompts():
    with _lock:
        items = sorted(SAVED_PROMPTS.values(), key=lambda x: x["created_at"], reverse=True)
    return jsonify(items)


@app.route("/api/prompts", methods=["POST"])
@login_required
def api_prompt_save():
    data = flask_request.get_json()
    pid = gen_id()
    prompt = {
        "id": pid,
        "text": data.get("text", ""),
        "label": data.get("label", ""),
        "created_at": now_iso(),
    }
    with _lock:
        SAVED_PROMPTS[pid] = prompt
    return jsonify({"ok": True, "id": pid})


@app.route("/api/prompts/<pid>", methods=["DELETE"])
@login_required
def api_prompt_delete(pid):
    with _lock:
        SAVED_PROMPTS.pop(pid, None)
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# API ROUTES — GEMMA CHAT
# ═══════════════════════════════════════════════════════════════

@app.route("/api/gemma/chat", methods=["POST"])
@login_required
def api_gemma_chat():
    data = flask_request.get_json()
    user_msg = data.get("message", "")
    image_b64 = data.get("image")  # optional base64 image

    if GEMMA_API_KEY == "X":
        return jsonify({"error": "Gemma API key henüz ayarlanmadı. app.py'de GEMMA_API_KEY değişkenini güncelleyin."}), 400

    # Build request for Gemini API
    parts = []
    if image_b64:
        if image_b64.startswith("data:"):
            mime, b64_data = image_b64.split(";base64,")
            mime = mime.split(":")[1]
        else:
            mime = "image/jpeg"
            b64_data = image_b64
        parts.append({"inline_data": {"mime_type": mime, "data": b64_data}})
    parts.append({"text": user_msg})

    # Add to history
    GEMMA_MESSAGES.append({"role": "user", "content": user_msg, "image": bool(image_b64)})

    try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-3-4b-it:generateContent?key={GEMMA_API_KEY}"
        payload = {"contents": [{"parts": parts}]}
        resp = requests.post(api_url, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()

        reply = ""
        candidates = result.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            for part in content.get("parts", []):
                reply += part.get("text", "")

        GEMMA_MESSAGES.append({"role": "assistant", "content": reply})
        return jsonify({"reply": reply})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/gemma/history")
@login_required
def api_gemma_history():
    return jsonify(GEMMA_MESSAGES)


@app.route("/api/gemma/clear", methods=["POST"])
@login_required
def api_gemma_clear():
    GEMMA_MESSAGES.clear()
    return jsonify({"ok": True})


# ═══════════════════════════════════════════════════════════════
# API ROUTES — MODEL CATALOGS
# ═══════════════════════════════════════════════════════════════

@app.route("/api/mage/models")
@login_required
def api_mage_models():
    return jsonify(MAGE_MODELS)


@app.route("/api/wayin/models")
@login_required
def api_wayin_models():
    return jsonify(WAYIN_MODELS)


# ═══════════════════════════════════════════════════════════════
# PROXY — for CORS-free media access
# ═══════════════════════════════════════════════════════════════

@app.route("/api/proxy")
@login_required
def api_proxy():
    url = flask_request.args.get("url")
    if not url:
        return jsonify({"error": "url required"}), 400
    try:
        resp = requests.get(url, timeout=30, stream=True)
        content_type = resp.headers.get("content-type", "application/octet-stream")
        return Response(resp.iter_content(chunk_size=8192),
                        content_type=content_type,
                        headers={"Cache-Control": "public, max-age=3600"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    os.makedirs("templates", exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=5000)
