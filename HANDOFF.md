# SisePicker v2.0 인수인계

기준: 2026-10-15. Windows x64 웹 가져오기 전용 데스크톱 앱. HTTP API가 아니다.

## 현재 결과
- 네이버 부동산(기본), 시세통 두 탭. OCR 엔진·입력 UI·모델 번들 제거. 기존 설정의 OCR 필드는 호환용으로만 남긴다.
- 공급평수(평) 표시·묶음 및 공급 기준40평 미만이 기본이며 전용면적 선택 가능.
- 네이버 단지명은 `이름 연식' 세대수^`. 타입76D1/83A-2의 숫자 부분과 타입 키를 구분한다.
- 확인된 매물 없음은 `-`, 전체 확인이 안 된 값은 `?`. 부분 수집은 검수 후 출력한다.
- 필터 목표 상태를50ms 간격 확인,100ms 안정, 최대8초. 실패 시 필터 이름 표시. 매물 증가 후200ms 안정되면 다음 단계로 진행한다. 진전 없으면1100ms 대기와5회 정체 제한, 최대100회 유지.
- 시작 클릭이 필터를 다시 닫는 충돌은 이벤트 전파 차단 및 setTimeout(0) 후 첫 필터 조작으로 방지한다. 새 네이버 즐겨찾기 등록 필수.
- 생활권 표 편집, PPT 중앙 삽입, 원래 전용55~65㎡→24평/80~90㎡→34평 기록 유지. 기존 PPT 객체와 개인 데이터는 보존한다.

## 실행·빌드·배포
- 실행: dist/SisePicker.exe. 별도 Python/Node 불필요. 실행 중 PowerPoint 제어에는 설치된 PowerPoint 필요.
- 개발: Python3.12 x64, Node.js. `cmd /c build.bat` 실행. 의존성 핀은 requirements-build.txt.
- EXE: 26,606,806bytes. SHA256 `fa2e4eeadcf2ed2dde555749efe9c18f34aff12e4d08a218a59c96e2063aa4a6`.
- ZIP: dist/SisePicker-v2.0-win-x64.zip. 해시: dist/SHA256SUMS-v2.0.txt.
- 새 PC에는 네이버 즐겨찾기를 별도 등록하고 결과 복사 후 앱의 주황색 붙여넣기를 사용한다. 자동 감시 기본값은 꺼짐이다. EXE 교체만으로 브라우저 즐겨찾기는 갱신되지 않는다.

## 검증 근거와 한계
- 최종 코드 Python48개, 두 JavaScript 테스트 통과. 클릭 버블링 재현은 수정 전 실패/후 성공. 느린 필터 응답, 취소, 단지 전환, 미완료를 포함한다.
- 최종 EXE smoke 통과: Tk/편집표, PPTX, Pillow, COM import, 네이버 파서, 두 즐겨찾기 및 OCR 모듈 부재 검사. build/packaged-smoke.json 참조.
- test.pptx 문제는 테스트 템플릿 미생성 오류를 수정했고 실제 임시 PPT 저장·재열기를 검증했다. 사용자 PPT는 테스트하지 않았다.
- 2026-10-15 고덕그라시움 실제 화면: 매매1,014+전세73=1,087건 로딩 및 건수 일치. 조작50회 시간 합계12.315초, 전체 읽기 왕복 중앙값33ms. 도구 사이 대기 제외, 즐겨찾기 자체 완료 시간 아님. [측정 보고서](docs/PERFORMANCE-2026-10-15.md).
- 즐겨찾기 실행→복사→앱 붙여넣기 전체 과정 및 Python 미설치 별도 PC 검증은 미수행. 제한PATH 보고서는 이전 v2 빌드로 최종 EXE 검증과 혼동하지 말 것.

## 주요 파일·다음 작업
- gui_app.py/result_grid.py: 공통 결과와 검수. naver_extract.js/naver_picker.js/naver_import.py: DOM 읽기·수집·입력 계약. web_*: 시세통. pptx_writer.py/zone_dialog.py/record_writer.py: 출력과 기록.
- [SPEC.md](SPEC.md)는 소스 없이 재구현하기 위한 UI/계약/알고리즘/의존성/구현 순서다.
- 개선 후보: 목록 안정 판정의 전체 DOM 반복 읽기 축소,100회 제한을 대규모 단지와 느린 응답에 맞게 검토. 아직 구현하지 않았다.
- 외부 페이지 구조·추가 검색필터에 따라 부분 수집 가능. 자동화로 없음을 추정하지 말고 전체 건수 근거를 유지한다.
- 로컬 main은 과거 개발 이력이다. 공개 origin/main과 이력이 다르므로 reset 또는 강제push 금지. 공개 이력을 부모로 별도 인덱스에서 승인된 소스만 반영한다. 개인 PPT/XLSX, settings/logs/records/models/별도 ppt_excel_api는 공개 대상 아님.

## 공개 상태
공개 저장소: https://github.com/nanjjo/SisePicker (PUBLIC).
v2.0 게시 완료: https://github.com/nanjjo/SisePicker/releases/tag/v2.0 (정식 릴리스, draft=false).
태그/소스 커밋: 8fbe9309216a7af9a797d39eb057b0132e936493. v1.0 보존.
업로드 EXE SHA256은 위 로컬 해시와 일치. ZIP SHA256 `850fba70543cc34c5783acb94df4de0f9de05c84a5338a7cded157b4c1a899a9`도 일치. EXE/ZIP/체크섬3개 자산 확인.
릴리스 ZIP의 인수인계는 게시 전 스냅샷이다. 이 공개 상태 확인 기록은 후속 문서 커밋으로 추가하며 EXE/ZIP은 변경하지 않는다.
