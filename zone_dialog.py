"""PPT 페이지 연결을 보존하는 생활권 목록 편집기."""
import copy
import tkinter as tk
from tkinter import ttk, messagebox


class ZoneDialog(tk.Toplevel):
    def __init__(self, parent, rows, reload_rows, save_rows):
        super().__init__(parent)
        self.title("생활권 관리")
        self.geometry("740x480")
        self.transient(parent)
        self.rows = copy.deepcopy(rows)
        self.reload_rows, self.save_rows = reload_rows, save_rows
        ttk.Label(self, text="PPT 생활권 페이지를 선택하거나 목록을 편집하세요. 이름 수정·삭제는 이 앱의 목록에만 적용됩니다.", wraplength=700).pack(padx=12, pady=12)
        self.tree = ttk.Treeview(self, columns=("name", "page", "title"), show="headings", selectmode="browse")
        for key, label, width in (("name", "생활권 이름", 220), ("page", "PPT 페이지", 80), ("title", "원래 PPT 제목", 300)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.pack(fill="both", expand=True, padx=12)
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        self.tree.bind("<Double-1>", lambda e: self.entry.focus_set())
        editor = ttk.Frame(self); editor.pack(fill="x", padx=12, pady=8)
        self.name = tk.StringVar()
        self.entry = ttk.Entry(editor, textvariable=self.name)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda e: self.modify())
        for text, command in (("추가", self.add), ("수정", self.modify), ("삭제", self.remove)):
            ttk.Button(editor, text=text, command=command).pack(side="left", padx=3)
        bar = ttk.Frame(self); bar.pack(fill="x", padx=12, pady=(0,12))
        ttk.Button(bar, text="PPT 다시 가져오기", command=self.reload).pack(side="left")
        ttk.Button(bar, text="저장·선택", command=self.save).pack(side="right")
        ttk.Button(bar, text="취소", command=self.destroy).pack(side="right", padx=4)
        self.render()
        self.grab_set()

    def render(self, index=None):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(self.rows):
            self.tree.insert("", "end", iid=str(i), values=(row["name"], row.get("page") or "새 페이지", row.get("title", "PPT 추가 시 생성")))
        if index is not None and index < len(self.rows):
            self.tree.selection_set(str(index))

    def selected(self, event=None):
        if self.tree.selection():
            self.name.set(self.rows[int(self.tree.selection()[0])]["name"])

    def valid_name(self, index=None):
        name = self.name.get().strip()
        if not name or any(c in name for c in "\r\n\t"):
            messagebox.showerror("생활권", "생활권 이름을 한 줄로 입력하세요.", parent=self)
            return None
        if any(row["name"] == name for i, row in enumerate(self.rows) if i != index):
            messagebox.showerror("생활권", "같은 이름이 있습니다. 다른 이름을 입력하세요.", parent=self)
            return None
        return name

    def add(self):
        name = self.valid_name()
        if name:
            self.rows.append(dict(name=name, slide_id=None, page=None))
            self.render(len(self.rows)-1)

    def modify(self):
        if not self.tree.selection():
            return
        i = int(self.tree.selection()[0]); name = self.valid_name(i)
        if name:
            self.rows[i]["name"] = name
            self.render(i)

    def remove(self):
        if self.tree.selection():
            self.rows.pop(int(self.tree.selection()[0]))
            self.name.set(""); self.render()

    def reload(self):
        try:
            fresh = self.reload_rows()
        except Exception as e:
            messagebox.showerror("PPT 읽기 실패", str(e), parent=self)
            return
        known = {r.get("slide_id"): r for r in self.rows if r.get("slide_id") is not None}
        for row in fresh:
            if row["slide_id"] in known:
                row["name"] = known[row["slide_id"]]["name"]
        rows = fresh + [r for r in self.rows if r.get("slide_id") is None]
        names = set()
        for row in rows:
            if row["name"] in names:
                row["name"] += f" ({row.get('page', '새')}페이지)"
            names.add(row["name"])
        self.rows = rows
        self.render()

    def save(self):
        selection = self.tree.selection()
        selected = self.rows[int(selection[0])]["name"] if selection else ""
        self.save_rows(self.rows, selected)
        self.destroy()
