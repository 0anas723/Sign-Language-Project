import cv2
import mediapipe as mp
import numpy as np
import os
from tensorflow.keras.utils import to_categorical

# ===========================
# ⚙️ إعدادات التجهيز
# ===========================
DATASET_PATH = "dataset"  # اسم المجلد الذي يحتوي الفيديوهات
SEQUENCE_LENGTH = 40      # توحيد طول الحركة (40 فريم للحركة الواحدة)
# ===========================

mp_holistic = mp.solutions.holistic

def extract_keypoints(results):
    # نستخرج اليد اليمنى واليسرى فقط (لأنها الأهم)
    # كل يد 21 نقطة * 3 إحداثيات (x,y,z) = 63 رقم
    # إذا اليد مخفية نضع أصفاراً
    
    rh = np.array([[res.x, res.y, res.z] for res in results.right_hand_landmarks.landmark]).flatten() if results.right_hand_landmarks else np.zeros(21*3)
    lh = np.array([[res.x, res.y, res.z] for res in results.left_hand_landmarks.landmark]).flatten() if results.left_hand_landmarks else np.zeros(21*3)
    
    # ندمجهم في مصفوفة واحدة (126 رقم لكل فريم)
    return np.concatenate([rh, lh])

def process_data():
    actions = np.array(os.listdir(DATASET_PATH))
    label_map = {label:num for num, label in enumerate(actions)}
    
    sequences, labels = [], []

    print(f"🚀 بدء معالجة البيانات للكلاسات: {actions}")

    with mp_holistic.Holistic(min_detection_confidence=0.5, min_tracking_confidence=0.5) as holistic:
        for action in actions:
            action_path = os.path.join(DATASET_PATH, action)
            videos = os.listdir(action_path)
            
            for video_name in videos:
                video_path = os.path.join(action_path, video_name)
                cap = cv2.VideoCapture(video_path)
                
                window = [] # لتخزين فريمات الفيديو الحالي
                
                while cap.isOpened():
                    ret, frame = cap.read()
                    if not ret: break
                    
                    # معالجة الصورة
                    image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    results = holistic.process(image)
                    
                    # استخراج الأرقام
                    keypoints = extract_keypoints(results)
                    window.append(keypoints)
                
                cap.release()
                
                # 📏 توحيد الطول (Padding/Truncating)
                # إذا الفيديو أطول من 40، نأخذ أول 40
                # إذا أقصر، نكرر آخر فريم أو نضيف أصفار (هنا سنأخذ عينات منتظمة)
                if len(window) > 0:
                    # تقنية بسيطة: نعيد تشكيل المصفوفة لتكون بطول ثابت
                    # في النسخة البسيطة: نأخذ أول SEQUENCE_LENGTH فريم
                    # إذا كانت أقل، نملأ الباقي أصفار
                    data_seq = np.zeros((SEQUENCE_LENGTH, 126)) # 126 = (21*3)*2
                    length = min(len(window), SEQUENCE_LENGTH)
                    data_seq[:length] = window[:length]
                    
                    sequences.append(data_seq)
                    labels.append(label_map[action])
                    print(f"✅ تمت معالجة: {action}/{video_name}")

    # حفظ البيانات
    X = np.array(sequences)
    y = to_categorical(labels).astype(int) # تحويل الأسماء لأرقام (One-Hot)
    
    np.save('X_data.npy', X) # بيانات الحركة
    np.save('y_data.npy', y) # أسماء الحركات
    np.save('classes.npy', actions) # قائمة الكلمات
    
    print("\n🎉 تم تجهيز البيانات بنجاح! الملفات جاهزة للتدريب.")
    print(f"عدد الفيديوهات: {len(X)}")
    print(f"أبعاد البيانات: {X.shape}")

if __name__ == "__main__":
    process_data()