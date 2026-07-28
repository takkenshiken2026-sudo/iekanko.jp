#!/usr/bin/env python3
"""raw/ の画像を 16:10 にセンタークロップして cropped/ に JPEG 出力する。"""
from PIL import Image
import os

RAW = os.path.join(os.path.dirname(__file__), "..", "docs", "assets", "photos", "raw")
CROP = os.path.join(os.path.dirname(__file__), "..", "docs", "assets", "photos", "cropped")
TARGET_W = 1536
RATIO = 16 / 10

# raw_filename -> cropped_slug.jpg
MAPPING = {
    # 新規追加（repo root から移動済み想定）
    "Gemini_Generated_Image_45p9kv45p9kv45p9.png": "preg-funin-consult.jpg",
    "Gemini_Generated_Image_uywoyhuywoyhuywo.png": "preg-tamondo-support.jpg",
    # 未処理 raw → cropped（差し替え・新規）
    "ChatGPT Image 2026年7月28日 13_26_42.png": "child-study-desk.jpg",
    "ChatGPT Image 2026年7月28日 13_28_36.png": "eld-haishoku.jpg",
    "ChatGPT Image 2026年7月28日 14_04_01.png": "child-ninkagai.jpg",
    "ChatGPT Image 2026年7月28日 14_05_04.png": "med-sosai.jpg",
    "ChatGPT Image 2026年7月28日 14_08_29.png": "house-reform.jpg",
    "ChatGPT Image 2026年7月28日 14_13_28.png": "house-rent.jpg",
    "ChatGPT Image 2026年7月28日 14_14_33.png": "child-parent.jpg",
    "ChatGPT Image 2026年7月28日 15_06_52.png": "preg-birth.jpg",
    "ChatGPT Image 2026年7月28日 15_07_40.png": "house-sansedai.jpg",
    "ChatGPT Image 2026年7月28日 15_07_51.png": "preg-sango-care.jpg",
    "ChatGPT Image 2026年7月28日 15_10_24.png": "house-taishin.jpg",
    "ChatGPT Image 2026年7月28日 15_12_55.png": "job-shurou.jpg",
    "ChatGPT Image 2026年7月28日 15_16_46.png": "eld-kaigo-consult.jpg",
    "ChatGPT Image 2026年7月28日 15_17_44.png": "dis-teate-consult.jpg",
    "ChatGPT Image 2026年7月28日 15_19_44.png": "eld-iwai-consult.jpg",
    "ChatGPT Image 2026年7月28日 15_21_57.png": "child-hitorioya-clinic.jpg",
    "ChatGPT Image 2026年7月28日 15_23_25.png": "child-iwai-coupon.jpg",
    "Gemini_Generated_Image_5bux2c5bux2c5bux.png": "child-hoiku.jpg",
    "Gemini_Generated_Image_idrfwaidrfwaidrf.png": "eld-home-care.jpg",
    "Gemini_Generated_Image_lnwglqlnwglqlnwg.png": "dis-iryo-hospital.jpg",
    "Gemini_Generated_Image_lwpzbmlwpzbmlwpz.png": "low-bus.jpg",
    "Gemini_Generated_Image_oshrvloshrvloshr.png": "child-iryo-clinic.jpg",
    "Gemini_Generated_Image_p3bqddp3bqddp3bq.png": "eld-vaccine-consult.jpg",
    "Gemini_Generated_Image_pfcwcspfcwcspfcw.png": "child-omutsu-milk.jpg",
    "Gemini_Generated_Image_yyx313yyx313yyx3.png": "job-kashitsuke-consult.jpg",
    "34242263_s.jpg": "eld-aircon.jpg",
    "AI-26312B0132_TP_V4.jpg": "house-solar.jpg",
    "adpDSC_8574.jpg": "low-taxi.jpg",
    "ChatGPT Image 2026年7月28日 13_21_11.png": "child-park.jpg",
    "ChatGPT Image 2026年7月28日 13_22_00.png": "med-clinic-waiting.jpg",
    "ChatGPT Image 2026年7月28日 13_22_58.png": "child-baby-gear.jpg",
    "ChatGPT Image 2026年7月28日 13_24_11.png": "moving-boxes.jpg",
    "ChatGPT Image 2026年7月28日 13_34_54.png": "eld-care-equipment.jpg",
    "ChatGPT Image 2026年7月28日 13_37_35.png": "eld-hochoki.jpg",
    "ChatGPT Image 2026年7月28日 13_39_39.png": "procedure-cityhall.jpg",
    "ChatGPT Image 2026年7月28日 14_11_50.png": "eld-kaigo-card.jpg",
    "ChatGPT Image 2026年7月28日 14_15_59.png": "child-clinic.jpg",
    "Gemini_Generated_Image_chhsf7chhsf7chhs.png": "procedure-kyufukin.jpg",
    "3318181_s.jpg": "preg-boshi-techo.jpg",
    "34392924_s.jpg": "child-infant.jpg",
    "ookawa221061325_TP_V4.jpg": "procedure-mynumber.jpg",
}


def center_crop_16_10(im):
    w, h = im.size
    if w / h > RATIO:
        new_w = int(h * RATIO)
        left = (w - new_w) // 2
        box = (left, 0, left + new_w, h)
    else:
        new_h = int(w / RATIO)
        top = (h - new_h) // 2
        box = (0, top, w, top + new_h)
    return im.crop(box)


def process(src_path, dst_path):
    im = Image.open(src_path)
    if im.mode != "RGB":
        im = im.convert("RGB")
    im = center_crop_16_10(im)
    target_h = int(TARGET_W / RATIO)
    im = im.resize((TARGET_W, target_h), Image.LANCZOS)
    im.save(dst_path, "JPEG", quality=85, optimize=True)
    print(f"  {os.path.basename(src_path)} -> {os.path.basename(dst_path)} ({TARGET_W}x{target_h})")


def main():
    os.makedirs(CROP, exist_ok=True)
    done = skipped = 0
    for raw_name, slug in MAPPING.items():
        src = os.path.join(RAW, raw_name)
        if not os.path.isfile(src):
            # repo root fallback
            alt = os.path.join(os.path.dirname(RAW), "..", "..", raw_name)
            alt = os.path.normpath(alt)
            if os.path.isfile(alt):
                src = alt
            else:
                print(f"SKIP (not found): {raw_name}")
                skipped += 1
                continue
        dst = os.path.join(CROP, slug)
        process(src, dst)
        done += 1
    print(f"\nDone: {done} cropped, {skipped} skipped")


if __name__ == "__main__":
    main()
