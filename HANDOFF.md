# SisePicker 인수인계

기준일 2026-10-11 · 로컬 배포 v1.0

## 현재 결과
Windows 단일 실행 파일 `dist/SisePicker.exe`. 네이버 부동산(기본) → 시세통 → 이미지 OCR 탭이다. 웹 수집값을 편집 표에서 검수해 생활권 PPT 중앙에 추가한다. 클립보드 복사/단지목록 버튼은 제거했으며 OCR 자동 복사는 유지한다.

네이버는 세대수·승인일, 전용면적(기본)/공급평수별 매매·전세 최저 호가를 가져온다. 출력 헤더는 `단지명 연식' 세대수^`. 시세통/OCR 헤더는 기존 형식이다. 면적 타입 76D1,76D2,83A-2 등은 숫자만 면적 계산에 쓰되 매물 연결용 키는 보존한다. 수집 단계·단지·건수·진행 막대를 표시하고, 재시작 시 현재 단지를 읽는다. 단지 변경 시 이전 결과 복사를 막는다.

생활권 표는 PPT 제목에서 가져와 추가/수정/삭제하고 slide ID로 연결한다. 기록은 원래 전용55~65㎡→24평,80~90㎡→34평만 저장하며 기타 면적은 제외한다. PPT 새 상자는 항상 중앙, 기존 상자는 이동하지 않는다.

## 실행·빌드
- 사용자: `dist/SisePicker.exe` 실행. Python/Node 불필요.
- 개발: `.venv\Scripts\python.exe main.py`
- 배포: `cmd /c build.bat` (Python3.12 x64 및 Node.js 필요). 결과는 반드시 SisePicker.exe 하나로 통일.
- 자체검사: `dist/SisePicker.exe --smoke-test build/packaged-smoke.json`
- Windows에서 실행 중 exe 교체 불가. 잠겨 있으면 편집값 보존 후 사용자가 닫도록 요청.
- 브라우저 수정은 exe만 바꿔서는 적용되지 않는다. `dist/SisePicker-네이버가져오기.html`에서 즐겨찾기를 재등록하고 기존 패널을 닫은 뒤 실행해야 한다.

## 주요 파일과 재구현
[SPEC.md](SPEC.md)가 최종 상태를 기준으로 한 독립 재구현 명세이다. [README.md](README.md)는 사용자 안내다.
입력은 naver_*/web_*/ocr_engine.py·cell_reader.py, 편집은 gui_app.py/result_grid.py, 출력은 pptx_writer.py/record_writer.py, 생활권은 zone_dialog.py, 설정은 config_manager.py, 빌드는 build.bat/SisePicker.spec/smoke_test.py가 담당한다.
별도 `ppt_excel_api/`는 독립 프로젝트이며 해당 폴더 문서를 따른다. 사용자 `강동구/`, `.work-gangdong/`, PPT/XLSX·설정·로그를 소스 배포에 넣지 않는다.

## 검증 증거와 한계
- 마지막 코드 변경(숫자+문자+숫자 면적): Python 92개 통과, 두 Node 테스트 스크립트 통과, build.bat 종료0 및 패키지 자체검사 ok=true.
- 패키지 검사는 Tk/표, PPTX, Pillow, RapidOCR 모델, OpenCV/ONNXRuntime, COM import, 네이버 파서, 양쪽 안내 자산을 확인했다.
- 제한 PATH 검사는 이전 탭/헤더 수정 빌드에서 성공했다. 그 뒤 두 면적 수정 빌드는 일반 패키지 검사를 통과했다. 마지막 exe를 제한 PATH로 재검사한 것으로 혼동하지 말 것.
- Python 미설치 별도 PC/VM 검증은 안 했다. 실제 실행 중 PowerPoint 동작은 모의 COM 테스트와 구분한다.
- 실제 네이버에서 타입83A-2/84A-1을 확인했다. 최근 오류 수정 후 해당 단지 전체 수집→클립보드→앱의 실제 브라우저 종단 검증은 미실시. 모의 DOM에서 완료/부분/전환/중단·복사를 검증했다.
- 작은 OCR 캡처의 소수점/한글/연식은 여전히 취약하다. ?를 없애려 임계값만 낮추지 않는다. AI 초해상도 미구현.
- 네이버는 현재 페이지 필터의 매물만 읽는다. 전체 건수 대조에 실패하면 부분 수집이며 최저가 보장 없음. 사이트 DOM 변경 시 어댑터 업데이트 필요.

현재 exe SHA256: `372a114068d5271cda04eb72b167563104bcab3118232c31bbead1314020e068`

## 다음 작업자를 위한 주의
내부 grid 헤더는 단지명+숫자연식이며 외부 네이버 헤더와 다르다. 기록은 raw grid 및 원래 전용면적을 사용하므로 장식된 헤더를 기록 파서에 넘기지 않는다. 네이버에는 기존 2.48 평형 추정식을 적용하지 않는다. 타입 키를 앞 숫자로만 축약하면 서로 다른 전용면적이 섞일 수 있다.
공통 편집 결과 하나를 공유하므로 탭별 원본 이력을 가정하지 않는다. 웹 입력은 자동 기록/PPT를 보류한다. 부분수집 체크는 재그룹 시 초기화한다. 새 결과 최초 기록과 동일결과 갱신을 구분한다.
새 오류는 원본·정답·로그를 보존하고 파싱/단지 연결/집계/OCR/출력 중 어느 단계인지 재현한다. logs/last_ocr_*는 다음 인식으로 덮어쓴다.

## 게시 상태
공개 저장소: https://github.com/nanjjo/SisePicker (PUBLIC).
릴리스: https://github.com/nanjjo/SisePicker/releases/tag/v1.0 . 소스와 안내/라이선스 ZIP은 게시 완료, 대용량 EXE 업로드는 재시도 중이다. 소스 스냅샷 최초 커밋15cf886, v1.0 표기 커밋fab12ab. 로컬 개발 main은 변경하지 않고 공개용 codex/release-v1.0 브랜치를 원격 main으로 푸시했다. 이후 게시 시 이 차이를 유지하고 로컬 main을 강제로 덮어쓰지 않는다.
개인 PPT/XLSX·설정·전체 캡처 묶음과 별도 API 프로젝트는 제외했다. 회귀 테스트에 필요한 공개 사이트 표본 JSON과 작은 단지 캡처2개만 포함했다.

## 다음 버전 요청
사용자는 v2.0에서 네이버 동작을 확인한 뒤 OCR을 제거하기로 했다. 현재 코드에서 제거하지 않았으며 SPEC.md의 v2.0 확인 기준을 먼저 수행한다.
