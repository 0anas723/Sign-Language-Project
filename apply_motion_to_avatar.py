import bpy
import json
import os
import sys
import math
from mathutils import Vector, Euler

# =========================================================
# 🎛️ إعدادات المعايرة النهائية (تم ضبطها لتظهر اليد بوضوح)
# =========================================================

# 1. المقياس (Scale): تكبير مدى الحركة لتكون واضحة
SCALE_X = 1.5   # توسيع الحركة يمين/يسار
SCALE_Y = 0.8   # عمق الحركة
SCALE_Z = 1.6   # ارتفاع الحركة

# 2. الإزاحة (Offset): أهم نقطة لحل مشكلتك
# X=0.0 (المنتصف)
# Y=-0.45 (دفع اليد للأمام بقوة لتخرج من الجسم)
# Z=1.15 (خفض اليد لتناسب طول طفل أو شخص قصير)
R_OFFSET = (0.0, -0.45, 1.15) 

# زاوية الكف الطبيعية
HAND_ROTATION = (math.radians(25), math.radians(20), math.radians(10))

# موقع الكوع (لسحب اليد للخارج ومنع تداخلها مع الصدر)
POLE_R_POS = (2.5, -0.5, 1.0) 

# =========================================================

# إعداد المسارات
if bpy.data.filepath: BASE_DIR = os.path.dirname(bpy.data.filepath)
else: BASE_DIR = os.getcwd()

ANIMATIONS_DIR = os.path.join(BASE_DIR, "static", "animations")

# 🔴 هنا نحدد الكلمة يدوياً للتجربة داخل بلندر
# بعد أن تنجح التجربة، سيأخذ الموقع الكلمة تلقائياً من النظام
if "--" in sys.argv:
    try:
        args = sys.argv[sys.argv.index("--") + 1:]
        gloss_text = args[0] if args else "anta"
    except:
        gloss_text = "anta"
else:
    gloss_text = "anta" # <--- جرب تغيير هذه الكلمة إذا أردت اختبار ملف آخر

print(f"🚀 Processing Word: {gloss_text}")
words = gloss_text.lower().split()

# =========================================================
# 🦴 إعداد العظام (بناءً على الكشف الذي أرسلته)
# =========================================================

ARMATURE_NAME = "Armature"
PREFIX = "mixamorig9:" # تم التثبيت بناءً على اللوج الخاص بك

RIGHT_HAND_BONE = f"{PREFIX}RightHand"
LEFT_HAND_BONE = f"{PREFIX}LeftHand"

# مصفوفة الأصابع (Thumb1, Index1... etc)
FINGERS = {
    "RIGHT": [
        [f"{PREFIX}RightHandThumb{i}" for i in range(1, 4)],
        [f"{PREFIX}RightHandIndex{i}" for i in range(1, 4)],
        [f"{PREFIX}RightHandMiddle{i}" for i in range(1, 4)],
        [f"{PREFIX}RightHandRing{i}" for i in range(1, 4)],
        [f"{PREFIX}RightHandPinky{i}" for i in range(1, 4)],
    ],
    "LEFT": [
        [f"{PREFIX}LeftHandThumb{i}" for i in range(1, 4)],
        [f"{PREFIX}LeftHandIndex{i}" for i in range(1, 4)],
        [f"{PREFIX}LeftHandMiddle{i}" for i in range(1, 4)],
        [f"{PREFIX}LeftHandRing{i}" for i in range(1, 4)],
        [f"{PREFIX}LeftHandPinky{i}" for i in range(1, 4)],
    ]
}
MP_INDICES = [[4,2], [8,5], [12,9], [16,13], [20,17]]
FINGER_POWER = 1.5

# =========================================================
# ⚙️ التجهيز (Cleaning & Setup)
# =========================================================

armature = bpy.data.objects.get(ARMATURE_NAME)
if not armature:
    # محاولة بحث بديلة
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE':
            armature = obj
            break
if not armature:
    print("❌ خطأ: لم يتم العثور على Armature!")
    sys.exit()

# تنظيف الحركة السابقة
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode='POSE')
bpy.ops.pose.select_all(action='SELECT')
bpy.ops.pose.transforms_clear()
bpy.ops.object.mode_set(mode='OBJECT')
if armature.animation_data:
    armature.animation_data_clear()

# إنشاء الأهداف (Targets)
def get_target(name):
    obj = bpy.data.objects.get(name)
    if not obj:
        bpy.ops.object.empty_add(type='SPHERE', radius=0.05)
        obj = bpy.context.active_object
        obj.name = name
    obj.animation_data_clear()
    return obj

target_R = get_target("Target_Hand_R")
target_L = get_target("Target_Hand_L")
pole_R = get_target("Pole_Elbow_R")
pole_R.location = POLE_R_POS

# تطبيق IK
bpy.context.view_layer.objects.active = armature
bpy.ops.object.mode_set(mode='POSE')

def setup_ik(bone_name, target, pole=None):
    b = armature.pose.bones.get(bone_name)
    if not b: 
        print(f"⚠️ Warning: Bone {bone_name} not found!")
        return
    
    # إزالة القديم
    for c in b.constraints:
        if c.type == 'IK': b.constraints.remove(c)
    
    ik = b.constraints.new('IK')
    ik.target = target
    ik.chain_count = 3
    ik.use_rotation = True
    if pole:
        ik.pole_target = pole
        ik.pole_angle = 0

setup_ik(RIGHT_HAND_BONE, target_R, pole_R)
setup_ik(LEFT_HAND_BONE, target_L, None)

# =========================================================
# 🎬 التحريك (Animation Loop)
# =========================================================

def update_fingers(landmarks, side, frame):
    wrist = landmarks.get("0")
    if not wrist: return
    for i in range(5):
        tip = landmarks.get(str(MP_INDICES[i][0]))
        mcp = landmarks.get(str(MP_INDICES[i][1]))
        if tip and mcp:
            dist = math.sqrt((tip['x']-wrist['x'])**2 + (tip['y']-wrist['y'])**2)
            MAX_OPEN = 0.45 
            MIN_CLOSED = 0.10
            factor = max(0.0, min(1.0, (MAX_OPEN - dist) / (MAX_OPEN - MIN_CLOSED)))
            angle = factor * FINGER_POWER
            
            for bn_name in FINGERS[side][i]:
                b = armature.pose.bones.get(bn_name)
                if b:
                    b.rotation_mode = 'XYZ'
                    rot = -angle if side == "RIGHT" else angle
                    if i == 0: b.rotation_euler = (0, rot*0.5, rot*0.5)
                    else: b.rotation_euler = (0, 0, rot)
                    b.keyframe_insert("rotation_euler", frame=frame)

current_frame = 1

for word in words:
    json_path = os.path.join(ANIMATIONS_DIR, f"{word}.json")
    
    if not os.path.exists(json_path):
        print(f"❌ ملف الحركة غير موجود: {json_path}")
        continue

    print(f"📂 Reading: {word}.json")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for d in data:
        # --- معالجة اليد اليمنى ---
        rh = d.get("right_hand", {})
        if rh and rh.get("0"):
            w = rh["0"]
            
            # المعادلة المصححة للمحاور
            x = (w["x"] - 0.5) * -SCALE_X + R_OFFSET[0]
            # في بلندر Z هو الارتفاع، وفي الفيديو Y هو الارتفاع (مقلوب)
            z = R_OFFSET[2] + (w["y"] - 0.5) * -SCALE_Z 
            # العمق
            y = R_OFFSET[1] + (w["z"]) * SCALE_Y

            target_R.location = (x, y, z)
            target_R.keyframe_insert("location", frame=current_frame)
            
            target_R.rotation_euler = HAND_ROTATION
            target_R.keyframe_insert("rotation_euler", frame=current_frame)
            
            pole_R.location = POLE_R_POS
            pole_R.keyframe_insert("location", frame=current_frame)

            update_fingers(rh, "RIGHT", current_frame)
        
        # --- معالجة اليد اليسرى ---
        lh = d.get("left_hand", {})
        # نحرك اليسار فقط إذا كانت اليد مرفوعة (لتجنب الأخطاء أثناء الراحة)
        has_motion = False
        if lh and lh.get("0"):
            if lh["0"]["y"] < 0.9: has_motion = True # 0.9 يعني اليد ليست في أسفل الشاشة تماماً
        
        if has_motion:
            w = lh["0"]
            x = (w["x"] - 0.5) * -SCALE_X
            z = 1.15 + (w["y"] - 0.5) * -SCALE_Z # ارتفاع مشابه لليمنى
            y = -0.45 + (w["z"]) * SCALE_Y      # عمق مشابه لليمنى

            target_L.location = (x, y, z)
            target_L.keyframe_insert("location", frame=current_frame)
            update_fingers(lh, "LEFT", current_frame)
        else:
            # وضعية الراحة لليسار
            target_L.location = (-0.3, -0.2, 0.9)
            target_L.keyframe_insert("location", frame=current_frame)

        current_frame += 1
    
    current_frame += 15 # فاصل بين الكلمات

bpy.context.scene.frame_end = current_frame
print(f"✅ Animation Done! Total frames: {current_frame}")

# (اختياري) يمكنك إلغاء التعليق عن السطور التالية إذا أردت الريندر فوراً
# scn = bpy.context.scene
# scn.render.filepath = os.path.join(BASE_DIR, "output", "test_render.webm")
# bpy.ops.render.render(animation=True)