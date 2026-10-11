"""셀별 확인 상태를 표시하는 편집 가능한 시세 결과 표."""
import re
import tkinter as tk
from tkinter import ttk


class ResultGrid(ttk.Frame):
    NORMAL = "#ffffff"
    REVIEW = "#fff0c2"
    EDITED = "#e0f2e5"

    def __init__(self, parent):
        super().__init__(parent)
        self.cells = []
        self.rows = []
        self.loaded = False
        self._last_issue_entry = None
        self.summary = tk.StringVar(value="인식 결과가 여기에 표시됩니다.")
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(3, 5))
        ttk.Label(bar, textvariable=self.summary).pack(side="left")
        ttk.Button(bar, text="다음 확인 칸", command=self.focus_next_issue).pack(side="right")
        ttk.Label(self, text="노랑: 확인 필요  ·  초록: 수정됨  ·  클릭하여 입력, Tab/Enter로 이동",
                  foreground="#555555").pack(anchor="w", pady=(0, 4))
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(container, height=150, highlightthickness=0, background="#f5f6f8")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(container, orient="horizontal", command=self.canvas.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.body = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

    @staticmethod
    def valid(value, kind):
        value = value.strip()
        if kind == "name":
            return bool(value) and "?" not in value
        if kind == "year":
            return bool(re.fullmatch(r"\d{2}", value))
        if kind == "area":
            return bool(re.fullmatch(r"[1-9]\d*", value))
        return bool(re.fullmatch(r"-?\d+(?:\.\d+)?|-", value))

    def _entry(self, parent, row, col, value, kind, width=11):
        var = tk.StringVar(value=value)
        entry = tk.Entry(parent, textvariable=var, width=width, font=("맑은 고딕", 11),
                         relief="solid", borderwidth=1, justify="left" if kind == "name" else "center")
        entry.grid(row=row, column=col, sticky="nsew", padx=1, pady=1, ipady=5)
        cell = {"var": var, "entry": entry, "original": value, "kind": kind}
        self.cells.append(cell)
        var.trace_add("write", lambda *args: self._refresh())
        entry.bind("<Return>", lambda event: self._next_cell(entry))
        entry.bind("<FocusIn>", lambda event: self._reveal(entry))
        return var

    def _next_cell(self, entry):
        entries = [c["entry"] for c in self.cells]
        target = entries[(entries.index(entry) + 1) % len(entries)]
        target.focus_set()
        target.selection_range(0, "end")
        return "break"

    def _reveal(self, entry):
        if any(c["entry"] == entry for c in self.issues()):
            self._last_issue_entry = entry
        self.update_idletasks()
        x = entry.winfo_rootx() - self.body.winfo_rootx()
        y = entry.winfo_rooty() - self.body.winfo_rooty()
        if x < self.canvas.canvasx(0) or x + entry.winfo_width() > self.canvas.canvasx(self.canvas.winfo_width()):
            self.canvas.xview_moveto(max(0, x / max(1, self.body.winfo_width())))
        if y < self.canvas.canvasy(0) or y + entry.winfo_height() > self.canvas.canvasy(self.canvas.winfo_height()):
            self.canvas.yview_moveto(max(0, y / max(1, self.body.winfo_height())))

    def set_text(self, text, area_label="면적 (m²)", price_columns=2, year_visible=True):
        for child in self.body.winfo_children():
            child.destroy()
        self.cells, self.rows = [], []
        self._last_issue_entry = None
        self.loaded = bool(text.strip())
        lines = text.strip().splitlines()
        header = lines.pop(0) if lines and not re.match(r"^\s*(?:\d+|\?)\)", lines[0]) else ""
        match = re.fullmatch(r"(.*?)\s+(\d{2}|\?)", header)
        name, year = match.groups() if match else (header, "")
        head = ttk.Frame(self.body)
        head.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 8))
        ttk.Label(head, text="단지명").grid(row=0, column=0, padx=4)
        self.name = self._entry(head, 0, 1, name, "name", 22)
        year_label=ttk.Label(head, text="연식")
        year_label.grid(row=0, column=2, padx=4)
        self.year = self._entry(head, 0, 3, year, "year", 5)
        if not year_visible:
            year_label.grid_remove()
            self.cells[-1]["entry"].grid_remove()
        data = []
        for line in lines:
            area, separator, values = line.partition(")")
            if separator:
                data.append((area.strip(), [v.strip() or "?" for v in values.split("/")]))
        count = max(price_columns, max((len(values) for _, values in data), default=0))
        labels = [area_label] + ["매매", "전세"][:count] + [f"값 {i + 1}" for i in range(2, count)] + ["상태"]
        for col, label in enumerate(labels):
            tk.Label(self.body, text=label, background="#e7ecf2", padx=10, pady=6).grid(row=1, column=col, sticky="nsew", padx=1)
        for row, (area, values) in enumerate(data, 2):
            variables = [self._entry(self.body, row, 0, area, "area")]
            for col in range(count):
                variables.append(self._entry(self.body, row, col + 1, values[col] if col < len(values) else "?", "price"))
            status = ttk.Label(self.body, width=13, anchor="center")
            status.grid(row=row, column=count + 1, padx=5)
            self.rows.append((variables, status))
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._refresh()

    def issues(self):
        return [c for c in self.cells if not self.valid(c["var"].get(), c["kind"])] if self.loaded else []

    def _refresh(self):
        for cell in self.cells:
            value = cell["var"].get().strip()
            color = self.REVIEW if not self.valid(value, cell["kind"]) else self.EDITED if value != cell["original"] else self.NORMAL
            cell["entry"].configure(background=color)
        for variables, status in self.rows:
            issues = sum(not self.valid(v.get(), "area" if i == 0 else "price") for i, v in enumerate(variables))
            status.configure(text=f"! 확인 {issues}칸" if issues else "✓ 입력 완료", foreground="#925500" if issues else "#21643b")
        count = len(self.issues())
        self.summary.set(f"확인 필요 {count}칸 — 노란 칸을 수정하세요." if count else "입력 완료 — 값 확인 후 PPT에 추가하세요." if self.loaded else "인식 결과가 여기에 표시됩니다.")

    def focus_next_issue(self):
        cells = self.issues()
        if not cells:
            return
        entries = [c["entry"] for c in cells]
        focus = self.focus_get()
        if focus not in entries and self._last_issue_entry in entries:
            focus = self._last_issue_entry
        target = entries[(entries.index(focus) + 1) % len(entries)] if focus in entries else entries[0]
        self._last_issue_entry = target
        target.focus_set()
        target.selection_range(0, "end")
        self._reveal(target)

    def get_text(self):
        if not self.loaded:
            return ""
        header = " ".join(v.get().strip() for v in (self.name, self.year) if v.get().strip())
        lines = [header] if header else []
        for variables, _ in self.rows:
            lines.append(f"{variables[0].get().strip()}) " + "/".join(v.get().strip() for v in variables[1:]))
        return "\n".join(lines)
