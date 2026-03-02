import json
import time
import requests
import os
from flask import Flask, request

app = Flask(__name__)

TOKEN = "8202773408:AAGLbNJDAUWQ-5KjvPc7aZaRO4k29XZKG0Y"
API = f"https://api.telegram.org/bot{TOKEN}"

SAVE_FILE = "user_progress.json"
TIME_LIMIT = 600  # 10 دقائق

# ------------------ ملفات الفصول ------------------

CHAPTER_FILES = {
    "الفصل الأول": "chapter1.json",
    "الفصل الثاني": "chapter2.json",
    "الفصل الثالث": "chapter3.json",
    "الفصل الرابع": "chapter4.json",
    "الفصل الخامس": "chapter5.json"
}

CHAPTER_ORDER = [
    "الفصل الأول",
    "الفصل الثاني",
    "الفصل الثالث",
    "الفصل الرابع",
    "الفصل الخامس"
]

# ------------------ إدارة المستخدمين ------------------

def load_users():
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users():
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

users = load_users()

def ensure_keys(chat_id):
    if chat_id not in users:
        users[chat_id] = {}

    user = users[chat_id]
    user.setdefault("index", 0)
    user.setdefault("score", 0)
    user.setdefault("start_from", 0)
    user.setdefault("lastTime", time.time())
    user.setdefault("waiting_jump", False)
    user.setdefault("last_message_id", None)
    user.setdefault("questions", [])
    user.setdefault("current_chapter", None)
    user.setdefault("messages", [])
    save_users()

# ------------------ أدوات الإرسال ------------------

def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    res = requests.post(f"{API}/sendMessage", json=payload).json()
    if res.get("ok"):
        msg_id = res["result"]["message_id"]
        ensure_keys(chat_id)
        users[chat_id]["messages"].append(msg_id)
        save_users()
    return res

def answer_callback(callback_id):
    requests.post(f"{API}/answerCallbackQuery", json={
        "callback_query_id": callback_id
    })

def delete_message(chat_id, message_id):
    requests.post(f"{API}/deleteMessage", json={
        "chat_id": chat_id,
        "message_id": message_id
    })

def clear_chat_for_user(chat_id):
    user = users.get(chat_id, {})
    for mid in user.get("messages", []):
        try:
            delete_message(chat_id, mid)
        except:
            pass
    user["messages"] = []
    save_users()

# ------------------ القوائم ------------------

def send_start_button(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🏁 بدء الاختبار", "callback_data": "start_exam"}]
        ]
    }
    send_message(chat_id, "مرحباً، اضغط على الزر لبدء الاختبار:", keyboard)

def send_chapters_menu(chat_id):
    keyboard = {"inline_keyboard": []}
    for name in CHAPTER_FILES.keys():
        keyboard["inline_keyboard"].append(
            [{"text": name, "callback_data": f"chapter:{name}"}]
        )
    send_message(chat_id, "اختر الفصل الذي تريد الاختبار فيه:", keyboard)

def send_in_exam_controls(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔁 إعادة الاختبار", "callback_data": "restart"}],
            [{"text": "🚀 الانتقال إلى سؤال معين", "callback_data": "jump"}],
            [{"text": "🛑 إيقاف الاختبار", "callback_data": "stop"}]
        ]
    }
    send_message(chat_id, "خيارات الاختبار:", keyboard)

# ------------------ تحميل الأسئلة ------------------

def load_questions_from_file(filename):
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

# ------------------ منطق الاختبار ------------------

def start_chapter(chat_id, chapter_name):
    filename = CHAPTER_FILES[chapter_name]
    questions = load_questions_from_file(filename)

    users[chat_id]["questions"] = questions
    users[chat_id]["current_chapter"] = chapter_name
    users[chat_id]["index"] = 0
    users[chat_id]["score"] = 0
    users[chat_id]["start_from"] = 0
    users[chat_id]["lastTime"] = time.time()
    users[chat_id]["waiting_jump"] = False
    save_users()

    send_message(chat_id, f"تم بدء اختبار: {chapter_name}")
    send_question(chat_id)

def handle_timeout(chat_id):
    user = users.get(chat_id)
    if not user:
        return

    questions = user.get("questions", [])
    answered = max(0, user["index"] - user["start_from"])

    clear_chat_for_user(chat_id)

    send_message(
        chat_id,
        f"⏳ انتهى الوقت (10 دقائق بدون تفاعل)\n"
        f"النتيجة: {user['score']} من {answered}"
    )

    users.pop(chat_id, None)
    save_users()
    send_start_button(chat_id)

def check_inactivity(chat_id):
    ensure_keys(chat_id)
    user = users[chat_id]
    now = time.time()
    if now - user["lastTime"] > TIME_LIMIT and user.get("questions"):
        handle_timeout(chat_id)
        return True
    return False

def send_question(chat_id):
    if check_inactivity(chat_id):
        return

    user = users[chat_id]
    questions = user.get("questions", [])
    idx = user["index"]
    total = len(questions)

    if idx >= total:
        return

    q = questions[idx]

    keyboard = [
        [{"text": opt, "callback_data": f"ans:{i}"}]
        for i, opt in enumerate(q["options"])
    ]

    res = send_message(
        chat_id,
        f"سؤال ({idx+1}/{total})\n\n{q['question']}",
        {"inline_keyboard": keyboard}
    )

    if res.get("ok"):
        users[chat_id]["last_message_id"] = res["result"]["message_id"]
        users[chat_id]["lastTime"] = time.time()
        save_users()

def finish_chapter(chat_id):
    user = users[chat_id]
    questions = user.get("questions", [])
    answered = max(0, user["index"] - user["start_from"])

    # ------------------ اختبار عبدالعزيز (بدون انتقال للفصل التالي) ------------------
    if user.get("current_chapter") == "اختبار عبدالعزيز":
        send_message(
            chat_id,
            f"🎉 انتهى اختبار عبدالعزيز\n"
            f"النتيجة: {user['score']} من {answered}"
        )
        users.pop(chat_id, None)
        save_users()
        send_start_button(chat_id)
        return
    # ------------------------------------------------------------------------------

    total = len(questions)

    send_message(
        chat_id,
        f"🎉 انتهى اختبار {user.get('current_chapter')}\n"
        f"النتيجة: {user['score']} من {answered}"
    )

    current_chapter = user.get("current_chapter")
    next_chapter = None
    if current_chapter in CHAPTER_ORDER:
        idx = CHAPTER_ORDER.index(current_chapter)
        if idx + 1 < len(CHAPTER_ORDER):
            next_chapter = CHAPTER_ORDER[idx + 1]

    keyboard = {"inline_keyboard": []}
    if next_chapter:
        keyboard["inline_keyboard"].append(
            [{"text": f"الانتقال إلى {next_chapter}", "callback_data": f"chapter:{next_chapter}"}]
        )
    keyboard["inline_keyboard"].append(
        [{"text": "🛑 إيقاف الاختبار", "callback_data": "stop"}]
    )

    send_message(chat_id, "ماذا تريد أن تفعل الآن؟", keyboard)

def next_question(chat_id):
    if check_inactivity(chat_id):
        return

    user = users[chat_id]
    user["index"] += 1
    save_users()

    questions = user.get("questions", [])
    if user["index"] >= len(questions):
        finish_chapter(chat_id)
        return

    send_question(chat_id)

def process_answer(chat_id, ans):
    if check_inactivity(chat_id):
        return

    user = users[chat_id]
    questions = user.get("questions", [])
    idx = user["index"]

    if idx >= len(questions):
        return

    q = questions[idx]

    now = time.time()
    if now - user["lastTime"] > TIME_LIMIT:
        handle_timeout(chat_id)
        return

    user["lastTime"] = now

    correct_idx = q["answer_index"]
    user_ans_idx = int(ans)

    if user_ans_idx == correct_idx:
        user["score"] += 1

    keyboard = []
    for i, opt in enumerate(q["options"]):
        if i == correct_idx:
            text = f"{opt} ✔️"
        elif i == user_ans_idx:
            text = f"{opt} ❌"
        else:
            text = opt

        keyboard.append([{"text": text, "callback_data": "done"}])

    try:
        requests.post(f"{API}/editMessageReplyMarkup", json={
            "chat_id": chat_id,
            "message_id": user["last_message_id"],
            "reply_markup": {"inline_keyboard": keyboard}
        })
    except:
        pass

    save_users()
    next_question(chat_id)

# ------------------ Webhook ------------------

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = request.get_json()

    if "message" in update:
        chat_id = str(update["message"]["chat"]["id"])
        text = update["message"].get("text", "").strip()

        ensure_keys(chat_id)

        # ------------------ استدعاء اختبار عبدالعزيز ------------------
        if text == "عبدالعزيز":
            try:
                with open("questions.json", "r", encoding="utf-8") as f:
                    questions = json.load(f)

                users[chat_id]["questions"] = questions
                users[chat_id]["current_chapter"] = "اختبار عبدالعزيز"
                users[chat_id]["index"] = 0
                users[chat_id]["score"] = 0
                users[chat_id]["start_from"] = 0
                users[chat_id]["lastTime"] = time.time()
                users[chat_id]["waiting_jump"] = False
                save_users()

                send_message(chat_id, "تم بدء اختبار عبدالعزيز 🎯")
                send_question(chat_id)
            except:
                send_message(chat_id, "⚠️ لم يتم العثور على ملف questions.json")
            return "ok"
        # ------------------------------------------------------------------

        user = users[chat_id]

        if check_inactivity(chat_id):
            return "ok"

        if user.get("waiting_jump"):
            if text.isdigit():
                target = int(text) - 1
                questions = user.get("questions", [])
                total = len(questions)
                if 0 <= target < total:
                    user["index"] = target
                    user["start_from"] = target
                    user["score"] = 0
                    user["waiting_jump"] = False
                    user["lastTime"] = time.time()
                    save_users()
                    send_question(chat_id)
                else:
                    send_message(chat_id, f"أدخل رقم بين 1 و {total}")
            else:
                send_message(chat_id, "الرجاء إدخال رقم سؤال صحيح.")
            return "ok"

        if user.get("questions"):
            send_in_exam_controls(chat_id)
        else:
            send_start_button(chat_id)

        return "ok"

    if "callback_query" in update:
        chat_id = str(update["callback_query"]["message"]["chat"]["id"])
        data = update["callback_query"]["data"]
        callback_id = update["callback_query"]["id"]

        answer_callback(callback_id)
        ensure_keys(chat_id)

        if check_inactivity(chat_id):
            return "ok"

        user = users[chat_id]

        if data == "start_exam":
            send_chapters_menu(chat_id)

        elif data.startswith("chapter:"):
            chapter_name = data.split(":", 1)[1]
            start_chapter(chat_id, chapter_name)

        elif data == "restart":
            chapter_name = user.get("current_chapter")
            if chapter_name:
                start_chapter(chat_id, chapter_name)
            else:
                send_start_button(chat_id)

        elif data == "jump":
            if not user.get("questions"):
                send_message(chat_id, "لا يوجد اختبار نشط حالياً.")
            else:
                user["waiting_jump"] = True
                save_users()
                send_message(chat_id, "اكتب رقم السؤال الذي تريد البدء منه:")

        elif data == "stop":
            if user.get("questions"):
                questions = user.get("questions", [])
                answered = max(0, user["index"] - user["start_from"])
                send_message(
                    chat_id,
                    f"🛑 تم إيقاف الاختبار\nالنتيجة الحالية: {user['score']} من {answered}"
                )
            users.pop(chat_id, None)
            save_users()
            send_start_button(chat_id)

        elif data.startswith("ans:"):
            process_answer(chat_id, data.split(":")[1])

        return "ok"

    return "ok"

# ------------------ تشغيل السيرفر ------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
