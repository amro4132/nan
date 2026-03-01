from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ضع رابط ديسكورد هنا
WEBHOOK_URL = "https://discord.com/api/webhooks/1477005798855933965/UGo7IuLJ2B-cp00CizKypWijgIOs5_95klXi75FyNw9C0xKSDchP-8Om5kDSRHIoaVbe"

@app.route('/api/data', methods=['POST'])
def handle_data():
    try:
        # استقبال البيانات كـ JSON
        data = request.get_json(force=True)
        device_name = data.get('id', 'Unknown')
        
        # إرسال إلى ديسكورد
        payload = {
            "content": f"🚀 **جهاز جديد متصل:** `{device_name}`"
        }
        requests.post(WEBHOOK_URL, json=payload)
        
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
