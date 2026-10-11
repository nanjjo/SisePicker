# SisePicker 재구현 명세

기준: 2026-10-11 / 배포 버전 v1.0. Windows 데스크톱 앱이며 HTTP API가 아니다.

## 목적과 범위
네이버 부동산과 시세통의 화면에 보이는 단지별 매매·전세 호가를 가져와 검수하고 생활권 PPT에 추가한다. 화면 텍스트 수집을 우선하고 이미지 OCR을 보조로 제공한다. 비공개 API, 로그인 자동화, 사이트 전체 크롤링, AI 초해상도는 구현하지 않는다. 별도 ppt_excel_api 프로젝트는 이 명세 및 배포 대상이 아니다.

## 플랫폼·구성
Windows x64, Python 3.12.10, tkinter/ttk, Pillow, RapidOCR/ONNX Runtime, Windows OCR, python-pptx 및 pywin32. 빌드 PC에는 Node.js도 필요하다. 배포 PC는 Python/Node 없이 단일 SisePicker.exe로 실행한다. 실행 중 PowerPoint 제어에는 설치된 PowerPoint가 필요하다. 한국어 Windows OCR은 해당 OS 언어팩에 의존한다.

파일 책임:
- main.py/app_paths.py: 진입점, 로그, exe 기준 쓰기 경로와 번들 자산 경로 구분.
- gui_app.py/result_grid.py: 세 입력 탭, 상태·비동기 OCR, 공통 편집 표, 출력 제어.
- naver_extract.js/naver_picker.js/naver_import.py: 화면 파싱, 즐겨찾기 수집 UI, Python 계약 검증·그룹화.
- web_extract.js/web_picker.js/web_import.py: 시세통 이름/표 연결, 단지 선택·복사, 계약 검증.
- ocr_engine.py/cell_reader.py/sise_parser.py: 좌표 기반 OCR·셀 재검증·공통 레코드.
- zone_dialog.py/pptx_writer.py: 생활권 표 편집, PPT 슬라이드 탐색·삽입 및 COM 경로.
- record_writer.py/name_dict.py/config_manager.py: 기록, 단지명 보정, JSON 설정.
- smoke_test.py/build.bat/SisePicker.spec: 독립 실행 검사와 배포.

## 화면과 상태
탭 순서는 네이버 부동산(항상 기본), 시세통, 이미지 OCR. 붙여넣기 버튼은 #FFAA45, 처음 사용 · 즐겨찾기 등록 방법 안내는 #B9E878. 웹 탭은 결과 표 전체 너비, OCR 탭은 원본/결과 좌우 절반이며 이미지 종횡비를 유지해 자동 확대한다. 기본 창 1100×820을 화면에 맞추며 최소 너비 640, 최소 높이는 700과 가용 높이 중 작은 값이다. 저장된 창 크기는 화면 범위에 맞춘다.

세 탭은 편집 결과 하나를 공유한다. 탭별 이력은 없다. Ctrl+V와 자동 감시는 선택 탭에 맞게 라우팅하되 셀 편집 중 붙여넣기를 가로채지 않는다. 표는 단지명·연식·면적·매매·전세와 상태를 제공한다. 노랑은 빈값/물음표/형식 오류, 초록은 수정된 정상 형식이다. Tab/Enter와 다음 확인 칸을 지원한다. 색은 사실 정확도 보증이 아니다. 클립보드 복사·단지목록 버튼은 제공하지 않는다. OCR 자동 복사 옵션은 남긴다.

네이버는 세대수와 YYYY-MM-DD 승인일을 별도 편집한다. 표시·묶음 선택은 전용면적(기본)/공급평수, 40평 미만 기준은 공급평수(기본)/전용면적이다. 원본으로 다시 적용은 편집값을 버리고 수집 원본으로 재구성한다. 부분 수집은 명시적인 원본 확인 체크 후 출력한다. 가져오기 자체로 자동 PPT/기록을 실행하지 않는다.

## 데이터와 출력 계약
공통 SiseRecord는 name, year, areas 문자열 목록, rows 가격 행 목록, warnings를 갖는다. rows의 각 길이는 areas 길이와 같아야 한다. `-`는 실제 없음, `?`는 미확인이다. 내부 편집 텍스트는 `단지명 19` 및 `59) 6.0/4.0`처럼 구성한다. 정수 가격은 .0을 붙일 수 있지만 125를 임의로 12.5로 바꾸면 안 된다.

네이버 출력 첫 줄은 `단지명 19' 224^`이며 승인연도 두 자리와 세대수를 쓴다. 시세통/OCR은 기존 `단지명 92` 형식을 유지한다. 헤더 장식과 내부 기록 파싱을 분리한다.

클립보드는 식별자 다음 줄 JSON:
```text
SISEPICKER_NAVER_V1
{"source":"https://new.land.naver.com/","complexId":"1335","name":"예시단지","households":"224","approvalDate":"1991-03-30","complete":true,"warnings":[],"types":[{"key":"76D1","supplyPyeong":"23","exclusiveArea":"59.1","sale":"6.0","lease":"4.0"}]}
```
```text
SISEPICKER_WEB_V1
{"source":"https://sisetong.kr/","name":"예시단지","year":"92","areas":["60","85"],"rows":[["6.5","8.5"],["3.3","3.5"]]}
```
출처 필드는 진위 인증이 아니다. 타입·날짜·양수 세대수·숫자 형식·중복 키·행열 길이를 검사한다. 네이버 JSON은 100000자 이하, 타입 1~200개, 경고 최대20개/각1000자, 이름100자 이하·제어문자 금지. 잘못된 접두사는 해당 입력으로 처리하지 않는다.

## 네이버 수집 알고리즘
1. new.land.naver.com/complexes/<숫자>에서만 실행. 단지정보 패널이 있어야 한다. 수집 시작마다 현재 단지 ID를 새로 읽는다.
2. #complexTitle 및 #summaryInfo .complex_feature의 세대수·사용승인일을 읽는다. 상세 평형 탭 제목에서 전용면적을 가져온다.
3. 면적 필터의 제곱미터/평 옵션을 같은 option value로 연결한다. 면적 문자열은 아래 패턴으로 숫자와 타입을 분리한다. 숫자만 면적 계산에 쓰고 전체 키는 타입별 전용면적·매물 연결에 보존한다. 타입을 일찍 없애면 같은 공급면적의 서로 다른 전용면적을 섞게 된다.
```javascript
/^(\d+(?:\.\d+)?)(?:[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*)?\s*(㎡|m²|평)?$/i
// 76D1 -> 76, 83A-2 -> 83; 소수 면적은 보존
```
4. 전체면적/전체동, 매매 A1+전세 B1, 동일매물 묶기 해제, 낮은가격순으로 설정한다. 상단 가격·층 등 추가 조건은 사용자가 먼저 해제해야 한다.
5. #articleListArea .item_link의 거래유형·가격·면적을 읽는다. 116A/84m²는 공급 타입116A와 전용84이다. 전용면적 정수부가 상세와 다르면 오류로 센다. 월세는 제외한다.
6. 가격은 억×10000+만원의 정수로 변환한 뒤 타입별 매매·전세 최저를 독립 집계한다. 12억5,000=125000만원=12.5억원. 두 최저 호가는 같은 매물이 아닐 수 있다.
7. 목록의 실제 스크롤 부모를 내려 추가 로딩한다. 최대100회, 회당1100ms 대기, 목록 개수5회 연속 정체 시 종료한다. 지도 선택 단지의 매매+전세 건수와 읽은 개수가 같으면 완료로 판단한다. 개수를 확인 못 하거나 형식 오류가 있으면 부분 수집이다. 부분 수집에는 최저가 보장이 없다.
8. 수집 시작 즉시 버튼 비활성·수집 중 문구·주황 상태·진행 막대. 면적확인→필터설정→매물읽기 단계, 단지명·읽은 수를 표시한다. 완료 녹색/부분 주황/오류 붉은색. 종료 시 버튼 복구. 수집 중 단지/필터 변경은 중단하고, 완료 후 단지 변경 시 이전 결과 복사는 차단한다.
9. Python에서 공급평수<40 또는 전용<132.23140496㎡로 필터링한다. 전용 표시값은 Decimal 전용면적의 정수부, 공급 표시는 네이버 평수. 같은 표시 면적을 합쳐 매매·전세 각각 최솟값을 취한다. 숫자가 없으면 ?가 하나라도 있을 때 ?, 모두 -이면 -.

## 시세통 연결
같은 부모 안의 지도 앵커 left/top이 정확히 같은 이름/연식과 표만 연결한다. 화면과 교차하는 표만 대상으로 하며 중복·모호한 연결과 열수 불일치는 제외한다. 가까운 거리나 DOM 순서로 단지를 추측하지 않는다. 셀별 문자열을 읽어 소수점을 보존한다. 사용자가 단지를 골라 복사한다. 두 사이트 모두 공개 DOM만 사용하며 수집값을 외부 서버에 보내지 않는다.

## OCR
이미지→확대·색상처리→RapidOCR 숫자/Windows 한국어 OCR→좌표 기반 행열 구성→중복 제거·누락 칸 보존→글자/셀 전체 재인식→공통 파서 순서. 언어 기본 ko, 배율4. OCR은 작업 스레드에서 수행하고 Tk 갱신은 메인 스레드 큐로 전달한다.

전체 표 후보, 원본색/강조색 반전, NEAREST 확대, 흑백 반전 등 셀 후보를 비교한다. 정수 후보도 소수점 누락 가능성을 검증한다. 작은 점 형태는 보류 근거이며 숫자 생성 근거가 아니다. 원본 글자 높이10px 미만은 기본 보류; 전체와 다섯 재인식 방식이 같은 소수값이고 각각 신뢰도0.95 이상일 때만 예외를 허용한다. 합성 좌표 빈칸은 값 복구 대상으로 쓰지 않는다. 면적이 불명확해도 다른 열 연결을 유지한다. 미확인 칸이 있으면 자동 출력·기록 보류. AI 초해상도는 도입하지 않는다.

## PPT·생활권·기록
PPT의 생활권 제목을 표로 가져오고 추가/수정/삭제 및 페이지 연결을 제공한다. 목록 수정은 PPT 페이지나 제목을 변경하지 않는다. PPT 경로별 목록과 slide ID를 저장한다. 연결 페이지가 삭제됐으면 다시 가져오도록 안내한다.
새 텍스트 상자는 매번 슬라이드 중앙에 추가한다: left=max(0,(slide_width-box_width)/2), top도 동일. 기본 박스4.5×2.6cm, 글자11pt. 기존 상자는 옮기지 않아 새 상자끼리 겹칠 수 있다. 실행 중 PowerPoint는 COM으로 처리하고 파일 경로는 python-pptx를 사용한다. 저장 실패는 상태로 알린다.
기록은 PPT 폴더/records/<생활권>_<평형>평.txt에 매매값만 저장한다. 원본 전용55~65㎡→24평,80~90㎡→34평(경계 포함), 나머지 제외. 네이버 묶음은 포함된 모든 원래 전용면적이 같은 범위일 때만 기록한다. 기존 파일은 삭제하지 않는다. 미확인 결과의 최초 저장은 새 항목, 같은 결과 재편집은 해당 항목 갱신이다. 화면 평형 옵션은 시세통/OCR 출력에만 round(area/2.48) 정책을 적용하며 기록 분류와 네이버에는 적용하지 않는다.

## 설정·자산·진단
exe 옆 SisePicker_config.json. 기본 PPT는 현재 사용자 Documents/생활권 시세따기.pptx. 기본 자동복사=true(OCR만), 감시=false, 자동PPT=false, 결과평형=false, 행수2, 기록=true, 항상위=false. 알 수 없는 설정키 무시, 깨진 JSON은 기본값. 개인 설정을 배포하지 않는다.
logs/SisePicker.log와 last_ocr_original.png, last_ocr_input.png, last_ocr_words.txt, last_ocr_cells.json, last_ocr_full_cells.json을 남긴다. last 파일은 덮어쓰므로 사례별 보관 필요.
4개 웹 JS를 번들에 포함하고 안내 HTML을 생성한다. 즐겨찾기는 URL 인코딩한 javascript 스크립트 링크다. 코드 변경 시 사용자는 즐겨찾기를 다시 등록한다. RapidOCR 기본 모델은 패키지 자산, 선택 한국어 ONNX/문자사전은 별도 확보 자산이다. 원본 모델 라이선스를 유지해야 하며 네이버/시세통 콘텐츠는 앱의 소유물이 아니다. 프로그램 자체의 공개 코드 라이선스는 별도 결정하며 공개 저장소만으로 재사용 권한을 부여하지 않는다.

## 고정 의존성
아래는 확인한 빌드 환경의 핀이다. 새 PC에서 동일 버전 공급 가능 여부와 네이티브 호환성을 확인한다.
```text
# Verified Windows build environment; Python 3.12 x64
altgraph==0.17.5
colorama==0.4.6
flatbuffers==25.12.19
lxml==6.1.2
numpy==2.5.2
onnxruntime==1.29.0
opencv-python==5.0.0.93
packaging==26.3
pefile==2024.8.26
pillow==12.3.0
protobuf==7.36.1
pyclipper==1.4.0
pyinstaller==6.22.2
pyinstaller-hooks-contrib==2026.7
python-pptx==1.0.2
pywin32==312
pywin32-ctypes==0.2.3
PyYAML==6.0.3
rapidocr-onnxruntime==1.4.4
setuptools==84.0.0
shapely==2.1.2
six==1.17.0
tqdm==4.70.0
typing_extensions==4.16.0
winocr==0.0.15
winrt-runtime==3.2.1
winrt-Windows.Foundation==3.2.1
winrt-Windows.Foundation.Collections==3.2.1
winrt-Windows.Globalization==3.2.1
winrt-Windows.Graphics.Imaging==3.2.1
winrt-Windows.Media.Ocr==3.2.1
winrt-Windows.Storage.Streams==3.2.1
xlsxwriter==3.2.9
```

## 처음부터 구현 순서 및 검증
1. 레코드·클립보드 스키마·가격/면적 파서와 경계 테스트 작성.
2. 공통 표·상태·출력 보류, 탭 라우팅 구현.
3. 시세통 DOM 연결, 네이버 타입 연결과 최저가 집계, 모의 DOM 테스트 구현.
4. 네이버 비동기 수집 상태·취소·단지전환·부분수집 구현.
5. PPT/생활권/기록과 사용자 수정 상태 연결.
6. 좌표 OCR과 재검증·진단, 실제 캡처 정답 비교.
7. 설정 저장, 자산 경로, 안내 HTML, 단일 exe 패키징.
8. 아래 명령 및 패키지 자체 검사. 실제 브라우저에서 새 즐겨찾기로 대표 단지 전체 흐름 별도 검증.
```bat
build.bat
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe -m unittest test_sisepicker test_workflow_changes test_naver_import -q
node tests/test_web_extract.cjs
node tests/test_naver_extract.cjs
```
build.bat는 자체 폴더로 이동하고 로컬 venv(system-site-packages)를 생성/재사용, 고정 의존성 설치, Python/JS 테스트, PyInstaller, dist/SisePicker.exe --smoke-test 보고서를 순차 실행한다. 실패하면 비정상 종료한다. windowed 단일 exe와 동적 import/네이티브 라이브러리/모델/JS를 포함한다.
인수 기준: 12.5를125로 임의 확정하지 않음, 행열 누락 위치 보존, 타입76D1/83A-2 처리, 면적/단위별 그룹과 경계 정확성, 단지전환 후 재수집·이전결과 복사차단, 부분수집 검수 필수, 새 기록이 이전 단지를 덮어쓰지 않음, PPT 중앙 삽입, 배포 exe 자체검사 성공. 제한 PATH 통과와 Python 없는 실제 PC 검증은 구분한다.
