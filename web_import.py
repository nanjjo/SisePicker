"""선택한 시세통 화면 텍스트를 검증해서 가져온다. 네트워크 요청은 하지 않는다."""
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from sise_parser import SiseRecord

PREFIX = "SISEPICKER_WEB_V1\n"


def parse_web_text(text):
    if not text.startswith(PREFIX):
        return None
    if len(text)>50000:
        raise ValueError("가져올 내용이 너무 큽니다.")
    try:
        data=json.loads(text[len(PREFIX):])
        if not isinstance(data,dict) or data.get("source") not in ("https://sisetong.kr/", "https://www.sisetong.kr/"):
            raise ValueError()
        name,year,areas,rows=(data[k] for k in ("name","year","areas","rows"))
        if not isinstance(name,str) or not name.strip() or len(name)>100 or any(ord(c)<32 for c in name):
            raise ValueError()
        if not isinstance(year,str) or not re.fullmatch(r"\d{2}",year):
            raise ValueError()
        if not isinstance(areas,list) or not 1<=len(areas)<=30 or any(not isinstance(a,str) or not re.fullmatch(r"[1-9]\d{1,2}",a) for a in areas):
            raise ValueError()
        if not isinstance(rows,list) or not 2<=len(rows)<=5:
            raise ValueError()
        for row in rows:
            if not isinstance(row,list) or len(row)!=len(areas) or any(not isinstance(v,str) or not re.fullmatch(r"-?\d+(?:\.\d+)?|-",v) or len(v)>15 for v in row):
                raise ValueError()
        return SiseRecord(name=name.strip(),year=year,areas=areas,rows=rows)
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("시세통 가져오기 데이터의 형식 또는 열 개수가 맞지 않습니다. 웹페이지에서 다시 복사해 주세요.") from exc


def create_guide(directory):
    base=Path(getattr(sys,"_MEIPASS",Path(__file__).parent))
    code=base.joinpath("web_extract.js").read_text(encoding="utf-8")+'\n'+base.joinpath("web_picker.js").read_text(encoding="utf-8")
    url="javascript:"+quote("(()=>{"+code+"})()",safe="")
    path=Path(directory)/"SisePicker-웹가져오기.html"
    path.write_text('''<!doctype html><html lang="ko"><meta charset="utf-8"><title>SisePicker 웹 가져오기</title>
<body style="font:18px sans-serif;max-width:760px;margin:50px auto;line-height:1.8"><h1>시세통 텍스트 가져오기</h1>
<p>아래 버튼을 Chrome 또는 Edge의 <b>즐겨찾기 모음으로 끌어다 놓으세요.</b> 모음이 안 보이면 Ctrl+Shift+B를 누르세요.</p>
<p><a style="background:#2563eb;color:white;padding:14px;border-radius:8px" href="'''+html.escape(url,quote=True)+'''">시세통 → SisePicker</a></p>
<ol><li>시세통 지도를 열고 원하는 단지 표가 보이도록 확대합니다.</li><li>등록한 즐겨찾기를 누릅니다.</li><li>단지명과 매매·전세 값을 확인한 뒤 ‘이 단지 복사’를 누릅니다.</li><li>SisePicker의 ‘시세통’ 탭에서 ‘시세통 값 붙여넣기’를 누릅니다.</li></ol>
<p>웹 가져오기는 결과 표에만 표시됩니다. 확인 후 복사 또는 PPT 추가를 눌러 저장합니다.</p>
<p>현재 화면에 표시된 이름과 값을 읽습니다. 이름이 줄여 표시됐다면 그대로 가져옵니다. 지도에서 이름이나 표를 따로 옮겼다면 ‘마커 초기화’ 후 다시 시도하세요.</p>
<p>사이트 구조가 바뀌거나 좌표 연결이 불분명하면 가져오지 않습니다. 외부 서버로 데이터를 전송하지 않습니다.</p></body></html>''',encoding="utf-8")
    return path
