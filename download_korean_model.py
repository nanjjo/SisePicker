"""RapidOCR 한국어 인식 모델(PaddleOCR korean_PP-OCRv4_rec_mobile, ONNX) 내려받기.

    python download_korean_model.py          → models\korean_PP-OCRv4_rec_mobile.onnx (약 10MB)

build.bat 이 빌드 전에 자동으로 실행한다(실패해도 빌드는 계속 — 그때는 Windows OCR 로 단지명 인식).
모델이 models\ 에 있으면 SisePicker.spec 이 exe 에 포함하고, ocr_engine 이 단지명 행에 이 모델을 우선 사용한다.
출처: RapidAI/RapidOCR 모델 저장소 (modelscope / huggingface 미러 순으로 시도).
"""
import os
import sys
import urllib.request

NAME = "korean_PP-OCRv4_rec_mobile.onnx"
URLS = [
    "https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/" + NAME,
    "https://huggingface.co/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/" + NAME,
    "https://hf-mirror.com/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/rec/" + NAME,
]
MIN_BYTES = 2_000_000    # 10MB 안팎이어야 정상. 그보다 작으면 오류 페이지를 받은 것


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(here, "models")
    out = os.path.join(out_dir, NAME)
    if os.path.isfile(out) and os.path.getsize(out) >= MIN_BYTES:
        print(f"[OK] already present: {out} ({os.path.getsize(out)//1024} KB)")
        return 0
    os.makedirs(out_dir, exist_ok=True)
    for url in URLS:
        try:
            print(f"[..] downloading {url}")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(out + ".part", "wb") as f:
                while True:
                    chunk = r.read(1 << 16)
                    if not chunk:
                        break
                    f.write(chunk)
            size = os.path.getsize(out + ".part")
            if size < MIN_BYTES:
                print(f"[!!] too small ({size} bytes) — not a model file, trying next mirror")
                os.remove(out + ".part")
                continue
            os.replace(out + ".part", out)
            print(f"[OK] saved {out} ({size//1024} KB)")
            return 0
        except Exception as e:
            print(f"[!!] failed: {e}")
            try:
                os.remove(out + ".part")
            except OSError:
                pass
    print("[WARN] Korean model not downloaded. SisePicker will use Windows OCR for the complex name.")
    print("       Manual: download the file from one of the URLs above and put it at", out)
    return 1


if __name__ == "__main__":
    sys.exit(main())
