"""설정(dataclass) + JSON 저장/로드. 알 수 없는 키는 무시, 없는 키는 기본값(하위 호환)."""
import dataclasses
import json
import os
from dataclasses import dataclass, field

from app_paths import app_dir

CONFIG_FILENAME = "SisePicker_config.json"


def default_pptx_path() -> str:
    """다른 PC 에서도 동작하도록 현재 사용자 문서 폴더 기준으로 기본값을 잡는다."""
    return os.path.join(os.path.expanduser("~"), "Documents", "생활권 시세따기.pptx")


@dataclass
class Config:
    # v2.0: 아래 OCR/사전 관련 필드는 v1 설정 호환용이며 웹 전용 GUI에서는 사용하지 않는다.
    # 결과를 붙여 넣을 PPT 파일 (PC 마다 다르므로 config JSON 에 저장되어 따라간다)
    pptx_path: str = field(default_factory=default_pptx_path)
    # winocr 언어 코드 (ko / en / ja ...)
    ocr_lang: str = "ko"
    # OCR 전 이미지 확대 배율 (작은 캡쳐는 확대해야 숫자 인식률이 올라간다)
    ocr_scale: int = 4
    # 인식 성공 시 결과를 자동으로 클립보드에 복사
    auto_copy: bool = True
    # 클립보드에 새 이미지가 들어오면 자동 인식
    watch_clipboard: bool = False
    # 인식 성공 시 선택한 PPT 에 텍스트 박스를 자동 추가
    auto_add_ppt: bool = False
    # 이름이 "…N단" 으로 잘려 있으면 "지" 를 붙여 "…N단지" 로 보정
    fix_danji_suffix: bool = True
    # 시세 행 중 몇 번째까지 쓸지 (첫 행/둘째 행 = 매매/전세)
    rows_to_use: int = 2
    # 결과/클립보드/PPT 의 면적을 평형으로 출력 ('60)' → '24)')
    result_in_pyeong: bool = False   # 기본: 결과/클립보드/PPT 는 표의 원래 숫자(전용 m²) 그대로. 기록 파일은 항상 평형별로 분류
    # 인식 후 "면적 → 평형" 변환 확인창을 띄운다 (기본 꺼짐; 켜면 취소 시 기록/복사/PPT 를 건너뜀)
    show_confirm_dialog: bool = False
    # PPT 텍스트 박스 배치 (cm)
    box_left_cm: float = 1.0
    box_top_cm: float = 1.0
    box_width_cm: float = 4.5
    box_height_cm: float = 2.6
    box_gap_cm: float = 0.3
    box_font_pt: int = 11
    box_columns: int = 5
    # 생활권 — PPT 슬라이드 제목 및 기록 파일 이름(<생활권>_<평형>평.txt)에 쓴다
    zone: str = ""
    zone_catalogs: dict = field(default_factory=dict)  # PPT 경로별 생활권/슬라이드 연결
    zone_slide_id: int | None = None
    zone_history: list = field(default_factory=list)   # 최근 사용한 생활권 (콤보박스)
    # 기록 파일 (인식 결과를 생활권별·평형별 파일에 누적, Excel 붙여넣기용)
    record_enabled: bool = True
    record_dir: str = ""                 # 비어 있으면(기본) <PPT 파일 폴더>\records. 다른 곳에 두려면 절대 경로
    record_separator: str = " "          # "\t" 로 하면 Excel 열이 자동 분리
        # 전용면적 → 공급평형 환산 계수 = 3.3058(m²/평) × 전용률 0.75 ≈ 2.48
    #   59→24, 84→34, 114→46, 135→54 평.  공급면적이 표기된 표라면 3.3058 로 바꿀 것.
    pyeong_divisor: float = 2.48
    # 단지명 사전(OCR 오독 보정): <PPT 폴더>\단지목록.txt. 사용자가 결과의 단지명을 고치면 자동 추가(학습)
    use_name_dict: bool = True
    name_dict_path: str = ""             # 비어 있으면 PPT 폴더의 단지목록.txt, 절대 경로면 그곳
    # 창을 항상 다른 창 위에 (지도 위에 띄워 두고 캡쳐→붙여넣기 할 때)
    always_on_top: bool = False
    # 창 크기 기억
    window_geometry: str = ""


def config_path() -> str:
    return os.path.join(app_dir(), CONFIG_FILENAME)


def load_config(path: str | None = None) -> Config:
    path = path or config_path()
    cfg = Config()
    if not os.path.isfile(path):
        return cfg
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return cfg
    names = {f.name for f in dataclasses.fields(Config)}
    for k, v in data.items():
        if k in names:
            setattr(cfg, k, v)
    if isinstance(cfg.ocr_scale, int) and cfg.ocr_scale < 4:
        cfg.ocr_scale = 4        # 실측: 3배는 작은 숫자를 놓친다 → 최소 4배
    if cfg.record_dir and not os.path.isabs(str(cfg.record_dir)):
        cfg.record_dir = ""      # 구버전 기본값 "records"(exe 폴더 기준) → PPT 폴더 기준으로
    return cfg


def save_config(cfg: Config, path: str | None = None) -> None:
    path = path or config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(dataclasses.asdict(cfg), f, ensure_ascii=False, indent=2)
