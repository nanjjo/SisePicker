"""SisePicker v2.0 웹 가져오기 전용 GUI."""
from __future__ import annotations

import copy
import logging
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional


import pptx_writer
from app_paths import app_dir
from config_manager import Config, load_config, save_config
from record_writer import ZoneRecorder
from result_grid import ResultGrid
from sise_parser import PYEONG_DIVISOR, conversion_info, format_record, lines_to_text

log = logging.getLogger("SisePicker")

APP_TITLE = "SisePicker v2.0 — 네이버 · 시세통 웹 가져오기"
WATCH_INTERVAL_MS = 800


class SisePickerGUI:
    def __init__(
        self,
        root: tk.Tk,
        config: Optional[Config] = None,
        ask_zone_on_start: bool = True,
    ):
        self.root = root
        self.config = config if config is not None else load_config()
        self._busy = False
        self._watch_job = None
        self._last_recorded_text: Optional[str] = None
        self._pending_record = False
        self._nav_record = None
        self._learned = ""
        self.recorder = ZoneRecorder(self._records_dir(self.config), self.config.zone,
                                     self.config.record_separator or " ",
                                     self._record_divisor(self.config))
        if self.config.zone and self.config.zone not in self.config.zone_history:
            self.config.zone_history = [self.config.zone] + list(self.config.zone_history)

        root.title(APP_TITLE)
        # 이전 버전의 짧은 창 크기가 저장돼 있어도 결과 표가 보이도록 높이를 보정한다.
        available_width = max(640, root.winfo_screenwidth() - 60)
        available_height = max(420, root.winfo_screenheight() - 100)
        saved = re.fullmatch(r"(\d+)x(\d+)([+-]\d+[+-]\d+)?", self.config.window_geometry or "")
        width = min(int(saved[1]) if saved else 1100, available_width)
        height = min(max(int(saved[2]) if saved else 820, 820), available_height)
        position = (saved[3] or "") if saved else ""
        try:
            root.geometry(f"{width}x{height}{position}")
        except tk.TclError:
            pass
        root.minsize(640, min(700, available_height))
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_widgets()
        self._config_to_gui()
        self._load_zones()
        self._schedule_watch()
        root.bind_all("<Control-v>", self._paste_shortcut)
        root.bind_all("<Control-V>", self._paste_shortcut)
        if not self.config.zone and ask_zone_on_start:
            root.after(200, self.ask_zone)

    # ------------------------------------------------------------------ UI
    def _build_widgets(self):
        r = self.root
        r.columnconfigure(0, weight=1)
        r.rowconfigure(2, weight=1)

        top = ttk.Frame(r, padding=(8, 8, 8, 0))
        top.grid(row=0, column=0, sticky="ew")
        self.notebook = ttk.Notebook(r)
        self.notebook.grid(row=1, column=0, sticky="ew", padx=8, pady=(8, 0))
        self.web_tab = ttk.Frame(self.notebook, padding=10)
        self.naver_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(self.naver_tab, text="네이버 부동산")
        self.notebook.add(self.web_tab, text="시세통")
        nav_actions=ttk.Frame(self.naver_tab); nav_actions.pack(fill="x")
        tk.Button(nav_actions,text="네이버 값 붙여넣기 (Ctrl+V)",command=self.read_clipboard,
                  background="#FFAA45",font=("맑은 고딕",10,"bold"),padx=12,pady=7,relief="flat").pack(side="left")
        tk.Button(nav_actions,text="처음 사용 · 즐겨찾기 등록 방법 안내",command=self.open_naver_guide,
                  background="#B9E878",font=("맑은 고딕",10,"bold"),padx=12,pady=7,relief="flat").pack(side="left",padx=8)
        ttk.Label(self.naver_tab,text="네이버 단지정보 열기 → 전용 즐겨찾기에서 매매·전세 수집 → 결과 복사 → 붙여넣기\n면적 기준을 선택해 매매·전세 최저 호가를 가져옵니다. 검수 후 PPT에 추가하세요.").pack(anchor="w",pady=(8,0))
        self.notebook.select(self.naver_tab)
        web_actions = ttk.Frame(self.web_tab)
        web_actions.pack(fill="x")
        self.btn_web_clip = tk.Button(web_actions, text="시세통 값 붙여넣기 (Ctrl+V)", command=self.read_clipboard,
                                      background="#FFAA45", foreground="#242424",
                                      activebackground="#F59627", activeforeground="#242424",
                                      font=("맑은 고딕", 10, "bold"), padx=12, pady=7, relief="flat", cursor="hand2")
        self.btn_web_clip.pack(side="left")
        tk.Button(web_actions, text="처음 사용 · 즐겨찾기 등록 방법 안내", command=self.open_web_guide,
                  background="#B9E878", foreground="#242424",
                  activebackground="#A3D65E", activeforeground="#242424",
                  font=("맑은 고딕", 10, "bold"), padx=12, pady=7, relief="flat", cursor="hand2").pack(side="left", padx=8)
        ttk.Label(self.web_tab, text="시세통에서 등록한 즐겨찾기 실행 → 단지 선택·복사 → 여기에 붙여넣기\n가져온 값을 확인한 뒤 PPT 추가를 누르세요.").pack(anchor="w", pady=(8, 0))
        nav_options=ttk.Frame(self.naver_tab);nav_options.pack(fill="x",pady=(6,0))
        self.var_nav_basis=tk.StringVar(value="공급평수 (평)")
        self.var_nav_cutoff=tk.StringVar(value="공급평수")
        for label,var,choices in [("표시·묶음",self.var_nav_basis,("전용면적 (㎡)","공급평수 (평)")),("40평 미만 기준",self.var_nav_cutoff,("공급평수","전용면적"))]:
            ttk.Label(nav_options,text=label).pack(side="left",padx=4)
            ttk.Combobox(nav_options,textvariable=var,values=choices,width=15,state="readonly").pack(side="left")
        ttk.Button(nav_options,text="원본으로 다시 적용",command=self._regroup_naver).pack(side="left",padx=6)
        self.var_watch = tk.BooleanVar()
        ttk.Checkbutton(top, text="클립보드 자동 감시", variable=self.var_watch,
                        command=self._on_watch_toggle).pack(side="left", padx=(14, 0))

        ttk.Label(top, text="생활권").pack(side="left", padx=(20, 4))
        self.var_zone = tk.StringVar()
        self.cmb_zone = ttk.Combobox(top, textvariable=self.var_zone, width=16,
                                     values=list(self.config.zone_history), state="readonly")
        self.cmb_zone.pack(side="left")
        self.cmb_zone.bind("<<ComboboxSelected>>", lambda e: self._apply_zone())
        self.cmb_zone.bind("<Return>", lambda e: self._apply_zone())
        self.cmb_zone.bind("<FocusOut>", lambda e: self._apply_zone())
        ttk.Button(top, text="생활권 관리…", command=self.ask_zone).pack(side="left", padx=(4, 0))
        self.var_topmost = tk.BooleanVar()
        ttk.Checkbutton(top, text="항상 위", variable=self.var_topmost,
                        command=self._on_topmost_toggle).pack(side="right")

        mid = self.mid = ttk.Frame(r, padding=8)
        mid.grid(row=2, column=0, sticky="nsew")
        mid.columnconfigure(0, weight=1)
        mid.rowconfigure(0, weight=1)

        right = ttk.Frame(mid)
        right.grid(row=0, column=0, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=0)
        right.rowconfigure(3, weight=1)

        hdr = ttk.Frame(right)
        hdr.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(hdr, text="결과 (편집 가능)").pack(side="left")
        self.var_conv = tk.StringVar(value="")
        ttk.Label(hdr, textvariable=self.var_conv, foreground="#0a5").pack(side="left", padx=(12, 0))
        self.nav_meta=ttk.Frame(right)
        self.nav_meta.grid(row=5,column=0,sticky="ew",pady=5)
        self.var_households=tk.StringVar(); self.var_approval=tk.StringVar(); self.var_nav_review=tk.BooleanVar()
        for label,var,width in [("세대수",self.var_households,7),("사용승인일",self.var_approval,12)]:
            ttk.Label(self.nav_meta,text=label).pack(side="left",padx=3)
            ttk.Entry(self.nav_meta,textvariable=var,width=width).pack(side="left")
        ttk.Checkbutton(self.nav_meta,text="부분 수집 원본 확인 완료",variable=self.var_nav_review).pack(side="left",padx=8)
        self.nav_meta.grid_remove()
        self.result_grid = ResultGrid(right)
        self.result_grid.grid(row=3, column=0, sticky="nsew")

        act = ttk.Frame(right)
        act.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        act.columnconfigure((0, 1), weight=1)
        self.btn_ppt = ttk.Button(act, text="PPT에 추가", command=self.add_to_ppt)
        self.btn_ppt.grid(row=0, column=1, sticky="ew", padx=(3, 0))
        self.btn_rec = ttk.Button(act, text="기록 폴더 열기", command=self.open_record)
        self.btn_rec.grid(row=0, column=0, sticky="ew", padx=(0, 3), pady=3)
        opt = ttk.LabelFrame(r, text="설정", padding=8)
        opt.grid(row=3, column=0, sticky="ew", padx=8)
        opt.columnconfigure(1, weight=1)
        ttk.Label(opt, text="PPT 파일").grid(row=0, column=0, sticky="w")
        self.var_pptx = tk.StringVar()
        ppt_entry = ttk.Entry(opt, textvariable=self.var_pptx)
        ppt_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ppt_entry.bind("<FocusOut>", lambda e: self._load_zones())
        ttk.Button(opt, text="찾기…", command=self.browse_pptx).grid(row=0, column=2)

        row1 = ttk.Frame(opt)
        row1.grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(row1, text="사용 행 수").pack(side="left", padx=(14, 4))
        self.var_rows = tk.IntVar()
        ttk.Spinbox(row1, from_=1, to=5, width=3, textvariable=self.var_rows,
                    command=self._save_config).pack(side="left")
        self.var_pyeong = tk.BooleanVar()
        ttk.Checkbutton(row1, text="평형으로 출력", variable=self.var_pyeong,
                        command=self._save_config).pack(side="left", padx=(14, 0))
        self.var_confirm = tk.BooleanVar()
        ttk.Checkbutton(row1, text="변환 확인창", variable=self.var_confirm,
                        command=self._save_config).pack(side="left", padx=(10, 0))
        self.var_status = tk.StringVar(value="네이버에서 수집 결과를 복사한 뒤 '네이버 값 붙여넣기'를 누르세요.")
        ttk.Label(r, textvariable=self.var_status, anchor="w", relief="sunken",
                  padding=(6, 2)).grid(row=4, column=0, sticky="ew", padx=8, pady=8)

    def _nav_mode(self):
        return self.notebook.select() == str(self.naver_tab)



    # -------------------------------------------------------------- config
    def _config_to_gui(self):
        c = self.config
        self.var_pptx.set(c.pptx_path)
        self.var_zone.set(c.zone)
        self.var_watch.set(c.watch_clipboard)
        self.var_rows.set(c.rows_to_use)
        self.var_pyeong.set(c.result_in_pyeong)
        self.var_confirm.set(c.show_confirm_dialog)
        self.var_topmost.set(c.always_on_top)
        self._apply_topmost()

    def _gui_to_config(self) -> Config:
        # 새 Config() 를 만들지 않는다 — GUI 에 없는 필드가 기본값으로 리셋되기 때문.
        c = copy.deepcopy(self.config)
        c.pptx_path = self.var_pptx.get().strip()
        c.zone = self.var_zone.get().strip()
        if c.zone and c.zone not in c.zone_history:
            c.zone_history = ([c.zone] + list(c.zone_history))[:20]
        c.watch_clipboard = bool(self.var_watch.get())
        try:
            c.rows_to_use = max(1, int(self.var_rows.get()))
        except (tk.TclError, ValueError):
            pass
        c.result_in_pyeong = bool(self.var_pyeong.get())
        c.always_on_top = bool(self.var_topmost.get())
        c.show_confirm_dialog = bool(self.var_confirm.get())
        try:
            c.window_geometry = self.root.geometry()
        except tk.TclError:
            pass
        return c

    @staticmethod
    def _record_divisor(cfg: Config):
        """결과 텍스트가 이미 평형이면 기록에서 다시 나누지 않는다(None)."""
        return PYEONG_DIVISOR  # 기록은 표시 평형과 무관하게 원본 m² 범위로 분류

    @staticmethod
    def _records_dir(cfg: Config) -> str:
        """기록 폴더: PPT 파일이 있는 폴더의 records\\. config.record_dir 에 절대 경로가 있으면 그곳."""
        if cfg.record_dir and os.path.isabs(cfg.record_dir):
            return cfg.record_dir
        base = os.path.dirname(os.path.abspath(cfg.pptx_path)) if cfg.pptx_path else app_dir()
        return os.path.join(base, "records")


    def _save_config(self):
        self.config = self._gui_to_config()
        self.recorder.directory = self._records_dir(self.config)
        self.recorder.divisor = self._record_divisor(self.config)
        try:
            save_config(self.config)
        except OSError as e:
            log.warning("config 저장 실패: %s", e)

    # -------------------------------------------------------------- actions
    def set_status(self, msg: str):
        self.var_status.set(msg)
        log.info(msg)

    def _paste_shortcut(self, event):
        if isinstance(event.widget, (tk.Entry, ttk.Entry, tk.Text, ttk.Combobox)):
            return
        self.read_clipboard()


    def read_clipboard(self):
        if self._busy:
            return
        if self._nav_mode():
            if not self._read_naver_clipboard():
                self.set_status("네이버 전용 즐겨찾기에서 결과를 복사한 뒤 붙여넣으세요.")
            return
        if not self._read_web_clipboard():
            self.set_status("시세통 전용 즐겨찾기에서 단지를 복사한 뒤 붙여넣으세요.")

    def open_web_guide(self):
        import webbrowser
        from web_import import create_guide
        try:
            path = create_guide(app_dir())
            webbrowser.open(path.as_uri())
        except OSError as exc:
            self.set_status(f"웹 가져오기 안내 열기 실패: {exc}")

    def open_naver_guide(self):
        import webbrowser
        from naver_import import create_guide
        try:
            webbrowser.open(create_guide(app_dir()).as_uri())
        except OSError as e:
            self.set_status(f"네이버 안내 열기 실패: {e}")

    def _read_naver_clipboard(self, watch=False):
        from naver_import import PREFIX,parse_naver_text
        try:
            raw=self.root.clipboard_get()
        except tk.TclError:
            return False
        if not raw.startswith(PREFIX):
            return False
        if watch and raw==getattr(self,"_last_naver_text",None):
            return True
        self._last_naver_text=raw
        try:
            data=parse_naver_text(raw)
        except ValueError as e:
            self.set_status(str(e)); return True
        self._nav_record=data
        self.var_households.set(data['households']); self.var_approval.set(data['approvalDate'])
        self.var_nav_review.set(False); self.nav_meta.grid()
        self._regroup_naver()
        self._pending_record=True; self._last_recorded_text=None
        self.var_conv.set("네이버 · 40평 미만 · 억원 · "+("전체 수집" if data['complete'] else "부분 수집: 원본 확인 필요"))
        self.set_status("네이버 가져오기 완료 — "+" ".join(data.get('warnings',[]))+" 세대수·승인일·가격을 확인한 뒤 PPT에 추가하세요.")
        return True

    def _regroup_naver(self):
        if not self._nav_record:
            return
        from naver_import import group_naver,as_record
        basis='exclusive' if self.var_nav_basis.get().startswith('전용') else 'supply'
        cutoff='exclusive' if self.var_nav_cutoff.get().startswith('전용') else 'supply'
        self.var_nav_review.set(False)
        self._nav_groups=group_naver(self._nav_record,basis,cutoff)
        self.result_grid.set_text(format_record(as_record(self._nav_record,self._nav_groups),2,None),
                                  "전용면적 (㎡)" if basis=='exclusive' else "공급평수 (평)",price_columns=2,year_visible=False)
        self.set_status("네이버 원본으로 다시 묶었습니다. 표시: "+self.var_nav_basis.get()+" / 40평 미만: "+self.var_nav_cutoff.get())

    def _read_web_clipboard(self, watch=False):
        from web_import import parse_web_text, PREFIX
        try:
            raw = self.root.clipboard_get()
        except tk.TclError:
            return False
        if not raw.startswith(PREFIX):
            return False
        if watch and raw == getattr(self, "_last_web_text", None):
            return True
        self._last_web_text = raw
        try:
            rec = parse_web_text(raw)
        except ValueError as exc:
            self.set_status(str(exc))
            return True
        cfg = self._gui_to_config()
        self.config = cfg
        divisor = cfg.pyeong_divisor or PYEONG_DIVISOR
        text = format_record(rec, cfg.rows_to_use, divisor if cfg.result_in_pyeong else None)
        self._handle_result(("web", [raw], text, rec, "웹 텍스트 · " + conversion_info(rec, divisor)))
        return True





    def _handle_result(self, item: tuple):
        self._nav_record = None
        self.nav_meta.grid_remove()
        _, _, text, rec, info = item
        self.result_grid.set_text(format_record(rec, self.config.rows_to_use, None), "면적 (m²)",
                                  price_columns=max(1, self.config.rows_to_use))
        self._pending_record = True
        self._last_recorded_text = None
        self.var_conv.set(info)
        self.set_status("웹 텍스트 가져오기 완료 — 단지명·가격 확인 후 PPT 추가를 누르세요.")

    def result_text(self) -> str:
        text = self.result_grid.get_text()
        if self._nav_record:
            lines=text.splitlines()
            if lines:
                lines[0]=f"{self.result_grid.name.get().strip()} {self.var_approval.get().strip()[2:4]}' {self.var_households.get().strip()}^"
            return "\n".join(lines)
        if self.var_pyeong.get():
            from sise_parser import to_pyeong
            text = re.sub(r"(?m)^(\d+)\)", lambda m: to_pyeong(m[1], self.config.pyeong_divisor or PYEONG_DIVISOR) + ")", text)
        return text

    def _ready_for_output(self):
        if self._nav_record:
            import datetime
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",self.var_approval.get().strip()):
                    raise ValueError()
                datetime.date.fromisoformat(self.var_approval.get().strip())
                if not re.fullmatch(r"[1-9]\d{0,6}",self.var_households.get().strip()):
                    raise ValueError()
            except ValueError:
                self.set_status("세대수와 사용승인일(YYYY-MM-DD)을 확인하세요.");return False
            if not getattr(self,'_nav_groups',[]):
                self.set_status("선택한 40평 미만 기준에 해당하는 면적이 없습니다.");return False
            if not self._nav_record['complete'] and not self.var_nav_review.get():
                self.set_status("부분 수집입니다. 원본에서 최저가와 누락 매물을 확인한 뒤 확인 체크를 선택하세요.");return False
        if self.result_grid.issues():
            self.result_grid.focus_next_issue()
            self.set_status(f"확인 필요 {len(self.result_grid.issues())}칸 — 노란 칸을 수정한 뒤 다시 눌러주세요.")
            return False
        return True

    def _record_edited_result(self, text):
        if self.config.record_enabled and (self._pending_record or self._last_recorded_text is not None):
            pending = self._pending_record
            self._record(text, new_entry=pending)
            if self._last_recorded_text == text:
                self._pending_record = False

    def _record(self, text: str, new_entry: bool):
        """세션 기록 파일에 반영. 편집된 결과는 마지막 항목을 교체한다."""
        try:
            raw_text = self.result_grid.get_text() or text
            if self._nav_record:
                from naver_import import recording_text
                raw_lines=raw_text.splitlines()
                if raw_lines:
                    raw_lines[0]=self.result_grid.name.get().strip()+" "+self.var_approval.get().strip()[2:4]
                raw_text=recording_text(self._nav_groups,"\n".join(raw_lines))
            if new_entry:
                self.recorder.add(raw_text)
            elif text != self._last_recorded_text:
                self.recorder.replace_last(raw_text)
            self._last_recorded_text = text
        except OSError as e:
            log.warning("기록 파일 저장 실패: %s", e)
            self.set_status(f"기록 파일 저장 실패: {e}")



    def open_record(self):
        path = self.recorder.directory
        if not os.path.isdir(path):
            self.set_status(f"아직 기록이 없습니다. (저장 위치: {path})")
            return
        try:
            os.startfile(path)  # Windows: records 폴더 열기
        except (AttributeError, OSError):
            self.set_status(f"기록 폴더: {path}")

    # ------------------------------------------------------------- topmost
    def _apply_topmost(self):
        try:
            self.root.attributes("-topmost", bool(self.var_topmost.get()))
        except tk.TclError:
            pass

    def _on_topmost_toggle(self):
        self._apply_topmost()
        self._save_config()
        self.set_status("항상 위: " + ("켬 — 지도/브라우저 위에 떠 있습니다." if self.var_topmost.get() else "꺼짐"))

    # ---------------------------------------------------------------- zone
    def _zone_key(self):
        return os.path.normcase(os.path.abspath(self.var_pptx.get().strip()))

    def _load_zones(self):
        key = self._zone_key()
        if key not in self.config.zone_catalogs:
            try:
                rows = pptx_writer.read_zone_titles(self.var_pptx.get().strip())
            except Exception as e:
                log.info("생활권 목록 읽기: %s", e)
                rows = [dict(name=n, slide_id=None, page=None) for n in self.config.zone_history]
            if not rows:
                rows = [dict(name=n, slide_id=None, page=None) for n in self.config.zone_history]
            seen = set()
            for row in rows:
                if row["name"] in seen:
                    row["name"] += f" ({row['page']}페이지)"
                seen.add(row["name"])
            self.config.zone_catalogs[key] = rows
        rows = self.config.zone_catalogs[key]
        names = [r["name"] for r in rows]
        self.cmb_zone.configure(values=names)
        if self.var_zone.get() not in names:
            self.var_zone.set(names[0] if names else "")
        self._apply_zone()

    def ask_zone(self):
        from zone_dialog import ZoneDialog
        self._load_zones()
        key = self._zone_key()
        def save(rows, selected):
            self.config.zone_catalogs[key] = rows
            self.var_zone.set(selected or (rows[0]["name"] if rows else ""))
            self._load_zones()
        ZoneDialog(self.root, self.config.zone_catalogs[key],
                   lambda: pptx_writer.read_zone_titles(self.var_pptx.get().strip()), save)

    def _apply_zone(self):
        zone = self.var_zone.get().strip()
        rows = self.config.zone_catalogs.get(self._zone_key(), [])
        selected = next((r for r in rows if r["name"] == zone), {})
        self.config.zone_slide_id = selected.get("slide_id")
        self.recorder.zone = zone
        self._save_config()
        self.set_status(f"생활권: {zone or '(미지정)'} — 기록: 55~65㎡ → 24평, 80~90㎡ → 34평")

    def copy_result(self):
        if not self._ready_for_output():
            return
        text = self.result_text()
        if not text.strip():
            self.set_status("복사할 결과가 없습니다.")
            return
        self._record_edited_result(text)
        self._copy_to_clipboard(text)
        self.set_status("클립보드에 복사됨 — PPT 에서 Ctrl+V" + (f"  ({self._learned})" if self._learned else ""))
        self._learned = ""

    def _copy_to_clipboard(self, text: str):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update_idletasks()
        except tk.TclError as e:  # pragma: no cover
            log.warning("클립보드 복사 실패: %s", e)

    def add_to_ppt(self):
        if not self._ready_for_output():
            return
        text = self.result_text()
        if not text.strip():
            self.set_status("추가할 결과가 없습니다.")
            return
        self._save_config()
        self._apply_zone()
        try:
            slide_no, name = pptx_writer.add_text_to_pptx(text, self.config, zone=self.config.zone)
        except (FileNotFoundError, PermissionError) as e:
            messagebox.showerror("PPT 추가 실패", str(e))
            self.set_status("PPT 추가 실패")
            return
        except Exception as e:
            log.exception("PPT 추가 실패")
            messagebox.showerror("PPT 추가 실패", str(e))
            self.set_status("PPT 추가 실패")
            return
        self._record_edited_result(text)
        zone = self.config.zone or "마지막"
        self.set_status(f"PPT {slide_no}번 슬라이드({zone})에 추가됨 ({name}) — {self.config.pptx_path}")

    def browse_pptx(self):
        init = self.var_pptx.get()
        path = filedialog.askopenfilename(
            title="PPT 파일", initialdir=os.path.dirname(init) if init else None,
            filetypes=[("PowerPoint", "*.pptx"), ("모든 파일", "*.*")])
        if path:
            self.var_pptx.set(path)
            self._load_zones()
            self._save_config()

    # ---------------------------------------------------------- clipboard watch
    def _on_watch_toggle(self):
        self._save_config()
        self.set_status("클립보드 자동 감시 " + ("켜짐 — 선택한 탭의 웹 수집 결과를 가져옵니다." if self.var_watch.get() else "꺼짐"))

    def _schedule_watch(self):
        self._watch_job = self.root.after(WATCH_INTERVAL_MS, self._watch_tick)

    def _watch_tick(self):
        try:
            if self.var_watch.get():
                if self._nav_mode():
                    self._read_naver_clipboard(watch=True)
                else:
                    self._read_web_clipboard(watch=True)
        finally:
            self._schedule_watch()

    def on_close(self):
        self._save_config()
        if self._watch_job is not None:
            self.root.after_cancel(self._watch_job)
            self._watch_job = None
        self.root.destroy()


def run():
    root = tk.Tk()
    SisePickerGUI(root)
    root.mainloop()
