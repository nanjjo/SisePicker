"""네이버 화면에서 복사한 공개 매물 자료 검증. 네트워크 요청 없음."""
import datetime
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote
from sise_parser import SiseRecord

PREFIX = 'SISEPICKER_NAVER_V1\n'


def parse_naver_text(text):
    if not text.startswith(PREFIX):
        return None
    try:
        if len(text) > 100000:
            raise ValueError()
        data = json.loads(text[len(PREFIX):])
        if not isinstance(data, dict) or data.get('source') != 'https://new.land.naver.com/':
            raise ValueError()
        if not re.fullmatch(r'\d{1,15}', data['complexId']):
            raise ValueError()
        name = data['name']
        if not isinstance(name, str) or not name.strip() or len(name)>100 or any(ord(c)<32 for c in name):
            raise ValueError()
        datetime.date.fromisoformat(data['approvalDate'])
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', data['approvalDate']):
            raise ValueError()
        if not re.fullmatch(r'[1-9]\d{0,6}', data['households']):
            raise ValueError()
        if not isinstance(data['complete'], bool):
            raise ValueError()
        if not isinstance(data['types'], list) or not 1 <= len(data['types']) <= 200:
            raise ValueError()
        seen = set()
        for g in data['types']:
            key=g['key']
            if not isinstance(key,str) or not re.fullmatch(r'\d{1,3}(?:\.\d+)?(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)?',key) or key in seen:
                raise ValueError()
            seen.add(key)
            if not re.fullmatch(r'[1-9]\d{0,2}',g['supplyPyeong']):
                raise ValueError()
            for k in ('sale', 'lease'):
                v=g[k]
                if not isinstance(v,str) or not re.fullmatch(r'\d{1,5}(?:\.\d{1,4})?|[-?]',v):
                    raise ValueError()
            area=g['exclusiveArea']
            if not isinstance(area,str) or not re.fullmatch(r'\d{1,3}(?:\.\d{1,4})?',area) or not 0<float(area)<1000:
                raise ValueError()
        warnings=data.get('warnings',[])
        if not isinstance(warnings,list) or len(warnings)>20 or any(not isinstance(w,str) or len(w)>1000 for w in warnings):
            raise ValueError()

        return data
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ValueError('네이버 가져오기 형식이 올바르지 않습니다. 네이버 전용 즐겨찾기에서 다시 복사해 주세요.') from exc


def group_naver(data, basis='exclusive', cutoff='supply'):
    from decimal import Decimal
    groups={}
    for t in data['types']:
        exclusive=Decimal(t['exclusiveArea'])
        supply=int(t['supplyPyeong'])
        if (supply >= 40 if cutoff=='supply' else exclusive >= Decimal('132.23140496')):
            continue
        area=str(int(exclusive)) if basis=='exclusive' else str(supply)
        g=groups.setdefault(area,dict(area=area,exclusiveAreas=[],sale=[],lease=[]))
        g['exclusiveAreas'].append(t['exclusiveArea'])
        for k in ('sale','lease'):
            g[k].append(t[k])
    def lowest(values):
        numbers=[Decimal(v) for v in values if v not in ('-','?')]
        if numbers:
            value=format(min(numbers),'f')
            return value if '.' in value else value+'.0'
        return '?' if '?' in values else '-'
    return [dict(area=g['area'],exclusiveAreas=g['exclusiveAreas'],sale=lowest(g['sale']),lease=lowest(g['lease']))
            for _,g in sorted(groups.items(),key=lambda pair:int(pair[0]))]


def as_record(data, groups):
    return SiseRecord(name=data['name'],year=data['approvalDate'][2:4],
                      areas=[g['area'] for g in groups],
                      rows=[[g[k] for g in groups] for k in ('sale','lease')])


def recording_text(groups, raw_text):
    """공급평수를 역산하지 않고 각 그룹의 전용면적을 사용해 기존 기록 분류에 연결."""
    lines=raw_text.splitlines()
    if not lines:
        return ''
    out=[lines[0]]
    by_area={g['area']:g for g in groups}
    for line in lines[1:]:
        area, sep, values=line.partition(')')
        group=by_area.get(area.strip())
        if not sep or not group:
            continue
        areas=[float(a) for a in group['exclusiveAreas']]
        buckets={24 if 55<=a<=65 else 34 if 80<=a<=90 else None for a in areas}
        if len(buckets)==1 and None not in buckets:
            out.append(('60' if buckets=={24} else '85')+')'+values)
    return '\n'.join(out)


def create_guide(directory):
    base=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))
    code=base.joinpath('naver_extract.js').read_text('utf-8-sig')+'\n'+base.joinpath('naver_picker.js').read_text('utf-8-sig')
    bookmark='javascript:'+quote('(()=>{'+code+'})()',safe='')
    path=Path(directory)/'SisePicker-네이버가져오기.html'
    path.write_text('''<!doctype html><html lang="ko"><meta charset="utf-8"><title>네이버 부동산 가져오기</title>
<body style="font:18px/1.8 sans-serif;max-width:850px;margin:40px auto;padding:20px"><h1>네이버 부동산 가져오기</h1>
<p>아래 링크를 Chrome/Edge 즐겨찾기 모음으로 끌어 놓으세요. 모음 표시: Ctrl+Shift+B</p>
<a style="display:inline-block;background:#b9e878;padding:14px;color:#162516" href="'''+html.escape(bookmark,quote=True)+'''">네이버 부동산 → SisePicker</a>
<ol><li>new.land.naver.com에서 단지를 선택하고 <b>단지정보</b>를 엽니다.</li>
<li>가격·층 등 불필요한 상단 검색조건을 해제합니다. 즐겨찾기는 현재 검색조건에 포함된 매물을 읽습니다.</li>
<li>등록한 즐겨찾기에서 <b>매매·전세 수집 시작</b>을 누릅니다. 매매·전세, 전체면적·전체동, 낮은가격순으로 전환하고 목록을 스크롤합니다. 앱에서 40평 미만 필터 기준(공급/전용)을 선택합니다.</li>
<li>수집 중에는 단지·필터를 바꾸지 마세요. 면적 타입별로 매매·전세 최저가를 수집합니다. 앱은 기본적으로 같은 정수 전용㎡로 묶습니다.</li>
<li>미리보기를 확인하고 <b>결과 복사</b>를 누릅니다. 앱의 <b>네이버 부동산</b> 탭에서 붙여넣습니다.</li>
<li>세대수·승인일·가격을 검수하고 PPT에 추가합니다. 부분 수집이면 원본을 확인한 뒤 확인 체크도 해야 합니다.</li></ol>
<p>가격은 억원 단위입니다. 12억 5,000 → 12.5. 월세와 실거래가는 제외합니다. 전체 목록 확인 시 매물 없음은 -, 불완전한 목록은 ?입니다.</p>
<p>세대수·사용승인일을 가져옵니다. 결과의 면적 선택 상자로 전용㎡(기본) 또는 공급평수로 묶을 수 있습니다. 전용㎡ 소수점 이하는 네이버 매물 표시처럼 버려서 묶으며, 예를 들어 84.03~84.95㎡는 84㎡입니다. 40평 미만 필터는 공급평수 기준이 기본이고, 전용 기준은 132.2314㎡ 미만입니다. 첫 줄은 단지명 두 자리 연식' 세대수^ 순서입니다. 기록 파일은 연결된 전용면적이 55~65㎡ 또는 80~90㎡에 속할 때만 저장합니다.</p>
<p>외부 서버에 전송하거나 비공개 API를 호출하지 않습니다. 사이트 구조 변경, 로딩 지연, 접근 제한 시 수집을 중단하거나 부분 수집으로 표시합니다. 즐겨찾기 업데이트 시 기존 링크를 새 링크로 교체하세요.</p></body></html>''',encoding='utf-8')
    return path
