import os
import subprocess
from pathlib import Path
import whisper
from flask import Flask, render_template, request, jsonify, send_from_directory
import shutil
import uuid
import json

# مكتبات معالجة النص العربي
import arabic_reshaper
from bidi.algorithm import get_display

app = Flask(__name__)

# ==========================================
# 1. إعداد المسارات
# ==========================================
os.environ["PATH"] += os.pathsep + r"C:\ffmpeg\bin"
BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
ANIMATIONS_DIR = BASE_DIR / "static" / "animations"
BLENDER_EXE = r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
BLEND_FILE = BASE_DIR / "anas.blend"
SCRIPT_FILE = BASE_DIR / "apply_motion_to_avatar.py"

# مسار الخط (سنقوم بمعالجته لاحقاً ليعمل مع FFmpeg)
FONT_PATH = "C:/Windows/Fonts/arial.ttf"

UPLOADS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
ANIMATIONS_DIR.mkdir(parents=True, exist_ok=True)

# ==========================================
# 2. القاموس المدمج
# ==========================================
INTERNAL_GLOSS_MAP = {
    "أنا": "ana", "انا": "ana",
    "أنت": "anta", "انت": "anta",
    "أنتم": "antum", "أنتهم": "antum",
    "شكرا": "shukran", "شكراً": "shukran",
    "أهلا": "ahla shla", "اهلا": "ahla shla", "مرحبا": "ahla shla", "صباح": "ahla shla",
    "اسم": "asm", "الاسم": "asm",
    "ضيوف": "guests",
    "أب": "father", "أبي": "father", "والد": "father",
    "أم": "mother", "أمي": "mother", "والدة": "mother",
    "ابن": "son", "أبنا": "son",
    "أخي": "brother", "أخ": "brother",
    "أخت": "sister", "أختي": "sister",
    "عائلة": "family",
    "رجل": "man",
    "بنت": "girl", "فتاة": "girl",
    "ولد": "boy", "أولاد": "boy",
    "صغير": "little_boy",
    "طفل": "baby", "رضيع": "baby",
    "جد": "grandfather",
    "جدة": "grandmother",
    "هنا": "here",
    "هو": "he", "هي": "she", "هم": "they",
    "ناس": "people", "شخص": "person",
    "أصدقاء": "friend", "صديق": "friend",
    "زواج": "marriage",
    "أجنبي": "foreigner",
    "عربي": "arab",
    "شعب": "people_general",
    "أقارب": "relatives",
    "توام": "twins",
    "شاب": "young_man", "شابة": "young_woman",
    "عجوز": "old_man",
    "بنات": "girls",
    "اخوان": "brothers", "أخوان": "brothers",
    "أوكرانيا": "ûkr"
}

# ==========================================
# 3. الدوال
# ==========================================

def convert_audio_to_text(audio_path):
    try:
        model = whisper.load_model("tiny") 
        result = model.transcribe(audio_path, language="ar")
        return result["text"].strip()
    except Exception as e:
        print(f"❌ Whisper Error: {e}")
        return ""

def text_to_gloss(text):
    words = text.split()
    gloss_list = []
    available_animations = {f.stem for f in ANIMATIONS_DIR.glob("*.json")}

    for w in words:
        clean_word = w.replace("،", "").replace(".", "").replace("!", "").strip()
        mapped_name = INTERNAL_GLOSS_MAP.get(clean_word)
        if mapped_name:
            if mapped_name in available_animations:
                gloss_list.append(mapped_name)
        elif clean_word in available_animations:
            gloss_list.append(clean_word)
        else:
            print(f"⚠️ تحذير: لا توجد حركة للكلمة '{clean_word}'")

    return " ".join(gloss_list)

def run_blender(gloss_text):
    cmd = [
        str(BLENDER_EXE), 
        str(BLEND_FILE), 
        "--background", 
        "--python", str(SCRIPT_FILE), 
        "--", gloss_text
    ]
    try:
        print(f"🔄 جاري تشغيل بلندر للكلمات: {gloss_text}")
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ خطأ في بلندر:\n{e.stderr}")
        return False
    except Exception as e:
        print(f"❌ خطأ عام: {e}")
        return False

def prepare_arabic_text_for_ffmpeg(text):
    try:
        reshaped_text = arabic_reshaper.reshape(text)
        bidi_text = get_display(reshaped_text)
        return bidi_text
    except Exception as e:
        print(f"Error processing text: {e}")
        return text

def merge_videos_with_text(original, avatar, output_name, text_to_display):
    final_output = OUTPUT_DIR / output_name
    
    # 1. تجهيز النص العربي
    processed_text = prepare_arabic_text_for_ffmpeg(text_to_display)
    # تنظيف النص من الرموز التي قد تكسر سطر الأوامر
    processed_text = processed_text.replace("'", "").replace(":", " ")

    # 2. إصلاح مسار الخط لـ FFmpeg (هذا هو الحل للمشكلة السابقة)
    # نقوم بتحويل "C:/" إلى "C\:/" لأن FFmpeg يكره النقطتين في المسارات
    font_path_fixed = FONT_PATH.replace(":", r"\:")

    # 3. إعداد فلتر الكتابة
    text_filter = (
        f"drawtext=fontfile='{font_path_fixed}':"
        f"text='{processed_text}':"
        "fontcolor=white:fontsize=40:"
        "x=(w-text_w)/2:y=h-th-50:"
        "box=1:boxcolor=black@0.6:boxborderw=10"
    )

    # 4. أمر الدمج
    cmd = (
        f'ffmpeg -i "{original}" -i "{avatar}" '
        f'-filter_complex "[1:v]scale=iw*0.5:-1[av];[0:v][av]overlay=W-w-20:20[v_with_avatar];[v_with_avatar]{text_filter}" '
        f'-c:a copy "{final_output}" -y'
    )
    
    print(f"🎬 جاري دمج الفيديو وإضافة الترجمة: {processed_text}")
    subprocess.run(cmd, shell=True)
    return final_output.exists()

# ==========================================
# 4. المسارات
# ==========================================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    if 'video' not in request.files:
        return jsonify({'status': 'error', 'message': 'لم يتم رفع فيديو'})
    
    file = request.files['video']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': 'اسم الملف فارغ'})

    unique_name = f"video_{uuid.uuid4().hex[:8]}.mp4"
    video_path = UPLOADS_DIR / unique_name
    file.save(video_path)

    # 1. الصوت
    audio_path = OUTPUT_DIR / "temp_audio.wav"
    subprocess.run(f'ffmpeg -i "{video_path}" -vn -acodec pcm_s16le -ar 16000 -ac 1 "{audio_path}" -y', shell=True)

    # 2. النص
    text = convert_audio_to_text(str(audio_path))
    if not text:
        return jsonify({'status': 'error', 'message': 'الصوت غير واضح.'})
    
    print(f"📝 النص المستخرج: {text}")

    # 3. الحركة
    gloss = text_to_gloss(text)
    if not gloss:
        return jsonify({'status': 'error', 'message': f'تم التعرف على: "{text}" لكن لا توجد حركات.'})
    
    print(f"🤖 سيقوم الأفاتار بتنفيذ: {gloss}")

    # 4. بلندر
    if run_blender(gloss):
        avatar_video = OUTPUT_DIR / "avatar_motion.webm"
        
        if not avatar_video.exists():
            return jsonify({'status': 'error', 'message': 'فشل إنشاء فيديو الأفاتار.'})

        # 5. الدمج + الترجمة
        final_filename = f"result_{uuid.uuid4().hex[:8]}.mp4"
        
        if merge_videos_with_text(video_path, avatar_video, final_filename, text):
            return jsonify({
                'status': 'success',
                'text': text,
                'video_url': f'/download/{final_filename}'
            })
    
    return jsonify({'status': 'error', 'message': 'حدث خطأ أثناء المعالجة.'})

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_DIR, filename)

if __name__ == '__main__':
    print("🚀 الموقع يعمل الآن على: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)