from flask import Flask, request, jsonify, send_from_directory
import google.genai as genai
from google.genai import types
import time
import os
import threading

app = Flask(__name__, static_folder='.', static_url_path='')

# ================== GEMINI CLIENT ==================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = None

if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
    print("✅ Gemini API Connected")
else:
    print("❌ WARNING: GEMINI_API_KEY not found!")

# ================== SYSTEM PROMPT ==================
SYSTEM_CHAT = """
    Bạn là Chatbot Điện học thông minh, hỗ trợ học sinh tìm hiểu về điện.

    Nhiệm vụ:
    - Giải thích các khái niệm: cường độ dòng điện (I), điện áp (U), công suất (P), điện trở (R), nhiệt lượng (Q)
    - Hệ thống có 1 cảm biến dòng (I) và 2 cảm biến điện áp (U1, U2)
    - Từ đó tính: P1=I*U1, R1=U1/I, Q1=P1*t và P2=I*U2, R2=U2/I, Q2=P2*t
    - Giải thích ý nghĩa các số liệu đo được
    - Trả lời ngắn gọn, dễ hiểu, phù hợp học sinh THPT

    Phong cách: thân thiện, dễ hiểu, có ví dụ thực tế.
    Nếu không chắc: "Bạn nên kiểm tra thêm tài liệu vật lý hoặc hỏi giáo viên nhé!"
"""

# ================== GLOBAL VARIABLES ==================
chat_history = []
exp_chat_histories = {}

latest_data = {"I": 0.0, "U1": 0.0, "U2": 0.0, "V": 0.0, "timestamp": ""}
history_data = {"I": [], "U1": [], "U2": [], "R1": [], "R2": [], "Q1": [], "Q2": [], "timestamps": []}
Q1_total = 0.0
Q2_total = 0.0
last_recv_time = None
MAX_HISTORY = 60
data_lock = threading.Lock()

# ================== ROUTES ==================

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')


@app.route('/data', methods=['POST'])
def receive_data():
    global Q1_total, Q2_total, last_recv_time
    try:
        d = request.get_json(force=True)
        I = float(d.get('I', 0))
        U1 = float(d.get('U1', 0))
        U2 = float(d.get('U2', 0))
        V = float(d.get('V', 0))
        ts = time.strftime('%H:%M:%S')

        now = time.time()
        dt = (now - last_recv_time) if last_recv_time else 1.0
        last_recv_time = now

        with data_lock:
            latest_data.update({'I': I, 'U1': U1, 'U2': U2, 'V': V, 'timestamp': ts})
            history_data['I'].append(I)
            history_data['U1'].append(U1)
            history_data['U2'].append(U2)
            history_data['R1'].append(round((U1 / I) if I != 0 else 0, 4))
            history_data['R2'].append(round((U2 / I) if I != 0 else 0, 4))
            history_data['Q1'].append(round(Q1_total + (I*U1*dt), 4))
            history_data['Q2'].append(round(Q2_total + (I*U2*dt), 4))
            history_data['timestamps'].append(ts)

            for k in list(history_data.keys()):
                if len(history_data[k]) > MAX_HISTORY:
                    history_data[k] = history_data[k][-MAX_HISTORY:]

        print(f"✅ [{ts}] I={I:.4f}A")
        return jsonify({"status": "ok"})
    except Exception as e:
        print("❌ receive_data error:", e)
        return jsonify({"status": "error"}), 400


@app.route('/api/latest')
def api_latest():
    with data_lock:
        return jsonify({
            "I": latest_data['I'], "U1": latest_data['U1'], "U2": latest_data['U2'], "V": latest_data['V'],
            "R1": history_data['R1'][-1] if history_data['R1'] else 0,
            "R2": history_data['R2'][-1] if history_data['R2'] else 0,
            "Q1": history_data['Q1'][-1] if history_data['Q1'] else 0,
            "Q2": history_data['Q2'][-1] if history_data['Q2'] else 0,
            "timestamp": latest_data['timestamp'],
            "histI": history_data['I'][-60:],
            "histU1": history_data['U1'][-60:],
            "histU2": history_data['U2'][-60:],
            "histR1": history_data['R1'][-60:],
            "histR2": history_data['R2'][-60:],
            "histQ1": history_data['Q1'][-60:],
            "histQ2": history_data['Q2'][-60:],
            "timestamps": history_data['timestamps'][-60:],
            "count": len(history_data['I'])
        })


@app.route('/chat', methods=['POST'])
def chat():
    global chat_history
    try:
        data = request.get_json()
        msg = data.get('message', '')
        if not msg:
            return jsonify({"response": "Bạn muốn hỏi gì về điện học?"})

        chat_history.append({"role": "user", "parts": [{"text": msg}]})

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=chat_history,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_CHAT)
        )

        reply = response.text
        chat_history.append({"role": "model", "parts": [{"text": reply}]})

        if len(chat_history) > 30:
            chat_history = chat_history[-30:]

        return jsonify({"response": reply})
    except Exception as e:
        print("Chat error:", e)
        return jsonify({"response": "Xin lỗi, AI đang bận. Thử lại sau nhé!"})


@app.route('/exp_chat', methods=['POST'])
def exp_chat():
    try:
        data = request.get_json()
        msg = data.get('message', '')
        if not msg:
            return jsonify({"response": "Em muốn hỏi gì về thí nghiệm?"})
        return jsonify({"response": "AI đang hỗ trợ thí nghiệm. Bạn đang gặp khó khăn ở phần nào?"})
    except:
        return jsonify({"response": "Lỗi kết nối AI"})


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    print(f"⚡ Server ESP32-S3 đang chạy trên port {port}")
    app.run(host='0.0.0.0', port=port)
