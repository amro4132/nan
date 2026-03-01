# server.py - سيرفر بسيط للتجربة
# تشغيل: python server.py

from flask import Flask, request, jsonify
import requests
import os
from datetime import datetime

app = Flask(__name__)

# ==================== إعدادات Discord ====================
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1477028807960432722/1R2rFE6rNx4dzYBBPJuoBV22YMuCypze7NAKa7hun2r_AxIAqGN8DP8Ew555v3nxGtkO"

# ==================== صفحة رئيسية ====================
@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "status": "online",
        "server": "Simple Test Server",
        "time": datetime.now().isoformat(),
        "endpoint": "/api/data (POST)"
    })

# ==================== استقبال البيانات ====================
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
        
        # طباعة في الكونسول
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 📥 استقبال من {client_id}")
        print(f"📝 المحتوى: {content}")
        
        # تحضير رسالة Discord
        discord_msg = f"**📡 اختبار ناجح!**\n"
        discord_msg += f"```\n"
        discord_msg += f"العميل: {client_id}\n"
        discord_msg += f"الوقت: {datetime.now().isoformat()}\n"
        discord_msg += f"البيانات: {content}\n"
        discord_msg += f"```"
        
        # إرسال إلى Discord
        try:
            response = requests.post(DISCORD_WEBHOOK, json={"content": discord_msg})
            if response.status_code == 204 or response.status_code == 200:
                print(f"✅ تم الإرسال إلى Discord")
            else:
                print(f"❌ فشل الإرسال إلى Discord: {response.status_code}")
        except Exception as e:
            print(f"❌ خطأ في Discord: {e}")
        
        return jsonify({"status": "success", "received": content}), 200
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return jsonify({"error": str(e)}), 500

# ==================== تشغيل السيرفر ====================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print("\n" + "="*50)
    print("🚀 تشغيل سيرفر الاختبار")
    print("="*50)
    print(f"📡 Discord Webhook: {DISCORD_WEBHOOK[:50]}...")
    print(f"📍 الرابط الرئيسي: http://localhost:{port}")
    print(f"📍 نقطة الإرسال: http://localhost:{port}/api/data")
    print("="*50 + "\n")
    app.run(host='0.0.0.0', port=port, debug=True)
