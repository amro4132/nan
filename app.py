from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ضع رابط الـ Webhook الخاص بقناتك في ديسكورد هنا
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1477028807960432722/1R2rFE6rNx4dzYBBPJuoBV22YMuCypze7NAKa7hun2r_AxIAqGN8DP8Ew555v3nxGtkO"

@app.route('/api/data', methods=['POST'])
def receive_data():
    data = request.json
    if not data:
        return jsonify({"error": "No data received"}), 400

    # استخراج اسم الجهاز من البيانات القادمة
    device_name = data.get('id', 'Unknown Device')
    message_content = data.get('content', 'No content')

    # تجهيز الرسالة لديسكورد
    payload = {
        "embeds": [{
            "title": "📢 تقرير جديد من جهاز",
            "description": f"**اسم الجهاز:** {device_name}\n**الحالة:** {message_content}",
            "color": 5814783 # لون أزرق
        }]
    }

    # إرسال البيانات إلى ديسكورد
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    
    if response.status_code == 204:
        return jsonify({"status": "success", "sent_to_discord": True}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to send to Discord"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
