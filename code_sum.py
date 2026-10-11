import os
import re
import sys
import uuid
import queue
import threading
import traceback
from collections import defaultdict
from datetime import datetime

# 控制闪屏时长
try:
    import pyi_splash

    pyi_splash.close()
except ImportError:
    pass

import tkinter as tk
from tkinter import filedialog
from pathlib import Path

import ttkbootstrap as ttkb
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox


class FileRenamerApp:
    # 状态栏语义常量
    STATUS_IDLE = "secondary"
    STATUS_INFO = "info"
    STATUS_SUCCESS = "success"
    STATUS_WARNING = "warning"
    STATUS_ERROR = "danger"

    # ★ 快捷键定义：集中管理，方便帮助对话框复用
    SHORTCUTS = [
        ("Ctrl+O", "打开目录"),
        ("F5", "刷新文件列表"),
        ("Ctrl+R", "预览重命名"),
        ("Ctrl+Enter", "执行重命名"),
        ("Ctrl+S", "应用排序"),
        ("Ctrl+1", "排序依据 → 名称"),
        ("Ctrl+2", "排序依据 → 修改时间"),
        ("Ctrl+3", "排序依据 → 大小"),
        ("Ctrl+4", "排序依据 → 类型"),
        ("Ctrl+D", "切换排序方向（升序 / 降序）"),
        ("F1", "显示快捷键帮助"),
        ("Ctrl+Q", "退出程序"),
    ]

    def __init__(self, root):
        self.root = root
        self.style = ttkb.Style()

        self.preview_data = None
        self.preview_signature = None
        self._param_check_after_id = None
        self._suggested_digits = None
        self._filter_check_after_id = None

        self._cancel_event = threading.Event()
        self._worker_thread = None
        self._progress_window = None
        self._progress_bar = None
        self._progress_label = None
        self._cancel_btn = None
        self._progress_queue = None
        self._poll_after_id = None

        self._log_path = os.path.join(
            os.path.expanduser("~"), "rename_debug.log"
        )
        self._log("=" * 60)
        self._log(f"程序启动，日志文件：{self._log_path}")

        # ------------------------------------------------------------------
        # 主题初始化
        # ------------------------------------------------------------------
        all_themes = self.style.theme_names()
        exclude = {'default', 'classic', 'vista', 'xpnative', 'winnative', 'clam', 'alt'}
        self.available_themes = [t for t in all_themes if t not in exclude]
        if not self.available_themes:
            self.available_themes = ['bootstrap-light']

        base_names_cn = {
            'bootstrap': '引导', 'pydata': '派数据', 'nord': '北欧',
            'solarized': '日光', 'catppuccin': '卡布奇诺', 'gruvbox': '格鲁夫',
            'dracula': '德古拉', 'tokyo-night': '东京夜', 'one': '一',
            'everforest': '常绿森林', 'vapor': '蒸汽', 'minty': '薄荷',
            'pulse': '脉冲', 'united': '联合', 'sandstone': '砂岩',
            'litera': '文学', 'morph': '形态', 'journal': '日志',
            'darkly': '暗黑', 'superhero': '超级英雄', 'cyborg': '赛博格',
            'flatly': '扁平', 'simplex': '简约', 'cerculean': '蔚蓝',
            'cosmo': '宇宙', 'lumen': '流明', 'yeti': '雪人',
        }

        self.theme_name_map = {}
        for theme in self.available_themes:
            if theme.endswith('-light'):
                base, suffix = theme[:-6], '亮色'
            elif theme.endswith('-dark'):
                base, suffix = theme[:-5], '暗色'
            else:
                base, suffix = theme, ''
            base_cn = base_names_cn.get(base, base.capitalize())
            display_name = f"{base_cn}{suffix}" if suffix else base_cn
            self.theme_name_map[theme] = display_name

        self.theme_display_list = [self.theme_name_map[t] for t in self.available_themes]

        self.current_theme = tk.StringVar(value=self.available_themes[0])
        self.style.theme_use(self.current_theme.get())

        self.theme_display_var = tk.StringVar(
            value=self.theme_name_map[self.current_theme.get()]
        )

        # ------------------------------------------------------------------
        # 窗口基础属性
        # ------------------------------------------------------------------
        self.root.title("批量重命名工具")

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_w = min(1180, int(screen_w * 0.85))
        win_h = min(1000, int(screen_h * 0.9))
        self.root.geometry(f"{win_w}x{win_h}")
        self.root.minsize(1020, 820)

        self.font = ("微软雅黑", 10)
        self.font_bold = ("微软雅黑", 11, "bold")
        self.title_font = ("微软雅黑", 15, "bold")
        self.hint_font = ("微软雅黑", 9)

        self._apply_custom_styles()

        # ------------------------------------------------------------------
        # 主框架
        # ------------------------------------------------------------------
        main_frame = ttkb.Frame(root, padding=8)
        main_frame.pack(fill=BOTH, expand=True)
        main_frame.columnconfigure(1, weight=1)

        main_frame.rowconfigure(0, weight=0)
        main_frame.rowconfigure(1, weight=0)
        main_frame.rowconfigure(2, weight=0)
        main_frame.rowconfigure(3, weight=0)
        main_frame.rowconfigure(4, weight=1)
        main_frame.rowconfigure(5, weight=0)
        main_frame.rowconfigure(6, weight=0)

        # ---- 标题行 + 主题选择 ----
        title_row = ttkb.Frame(main_frame)
        title_row.grid(row=0, column=0, columnspan=3, sticky='ew', pady=(0, 8))

        ttkb.Label(title_row, text="批量重命名工具", style="Title.TLabel").pack(side=LEFT)

        # ★ 帮助按钮 + 主题选择
        theme_frame = ttkb.Frame(title_row)
        theme_frame.pack(side=RIGHT)

        ttkb.Button(
            theme_frame, text="快捷键 (F1)",
            command=self._shortcut_show_help,
            bootstyle="secondary-link",  # ★ 修复：去掉非法的 -outline-link
            width=12,
        ).pack(side=LEFT, padx=(0, 15))

        ttkb.Label(theme_frame, text="主题：", font=self.font).pack(side=LEFT, padx=(0, 5))
        self.theme_combo = ttkb.Combobox(
            theme_frame,
            textvariable=self.theme_display_var,
            values=self.theme_display_list,
            state='readonly',
            width=12,
            font=self.font,
        )
        self.theme_combo.pack(side=LEFT)
        self.theme_combo.bind('<<ComboboxSelected>>', self._on_theme_change)

        # ---- 目录选择 ----
        ttkb.Label(main_frame, text="目录路径:", font=self.font).grid(
            row=1, column=0, sticky='w', pady=4)
        self.dir_path = tk.StringVar()
        ttkb.Entry(main_frame, textvariable=self.dir_path, font=self.font).grid(
            row=1, column=1, sticky='ew', pady=4, padx=5)
        self.browse_btn = ttkb.Button(main_frame, text="浏览 (Ctrl+O)",
                                      command=self.browse_directory,
                                      bootstyle="secondary-outline")
        self.browse_btn.grid(row=1, column=2, padx=5, pady=4)

        # ---- 参数输入 ----
        params_frame = ttkb.Labelframe(main_frame, text="重命名参数", padding=10,
                                       style="Section.TLabelframe")
        params_frame.grid(row=2, column=0, columnspan=3, sticky='ew', pady=6)
        params_frame.columnconfigure(1, weight=1)

        ttkb.Label(params_frame, text="文件名前缀:", font=self.font).grid(
            row=0, column=0, sticky='w', pady=4)
        self.file_prefix = tk.StringVar(value=" ")
        ttkb.Entry(params_frame, textvariable=self.file_prefix, font=self.font).grid(
            row=0, column=1, sticky='ew', pady=4, padx=5)

        ttkb.Label(params_frame, text="文件扩展名:", font=self.font).grid(
            row=0, column=2, sticky='w', pady=4)
        self.file_extension = tk.StringVar(value="png")
        ttkb.Entry(params_frame, textvariable=self.file_extension, width=10, font=self.font).grid(
            row=0, column=3, sticky='w', pady=4, padx=5)

        ttkb.Label(params_frame, text="起始序号:", font=self.font).grid(
            row=1, column=0, sticky='w', pady=4)
        self.start_number = tk.StringVar(value="1")
        ttkb.Entry(params_frame, textvariable=self.start_number, width=10, font=self.font).grid(
            row=1, column=1, sticky='w', pady=4, padx=5)

        ttkb.Label(params_frame, text="序号位数:", font=self.font).grid(
            row=1, column=2, sticky='w', pady=4)
        self.digits = tk.StringVar(value="1")
        ttkb.Entry(params_frame, textvariable=self.digits, width=10, font=self.font).grid(
            row=1, column=3, sticky='w', pady=4, padx=5)

        ttkb.Label(params_frame, text="每次增加:", font=self.font).grid(
            row=2, column=0, sticky='w', pady=4)
        self.increment = tk.StringVar(value="1")
        ttkb.Entry(params_frame, textvariable=self.increment, width=10, font=self.font).grid(
            row=2, column=1, sticky='w', pady=4, padx=5)

        ttkb.Label(
            params_frame,
            text="整数模式：序号位数=补零位数；小数模式：序号位数=小数位数。\n"
                 "前缀留空（或全为空格）时不会自动补“_”。",
            style="Hint.TLabel",
            wraplength=520,
            justify=LEFT,
        ).grid(row=2, column=2, columnspan=2, sticky='w', pady=4, padx=5)

        # ---- 文件过滤 ----
        ttkb.Label(params_frame, text="过滤扩展名:", font=self.font).grid(
            row=3, column=0, sticky='w', pady=4)
        self.filter_ext_var = tk.StringVar(value="")
        ttkb.Entry(params_frame, textvariable=self.filter_ext_var, font=self.font).grid(
            row=3, column=1, sticky='ew', pady=4, padx=5)

        self.filter_count_var = tk.StringVar(value="")
        ttkb.Label(params_frame, textvariable=self.filter_count_var,
                   style="Hint.TLabel").grid(
            row=3, column=2, columnspan=2, sticky='w', pady=4, padx=5)

        ttkb.Label(
            params_frame,
            text="提示：只处理指定扩展名的文件，多个用逗号分隔（如 png, jpg）。"
                 "留空则处理目录下所有文件。",
            style="Hint.TLabel",
            wraplength=800,
            justify=LEFT,
        ).grid(row=4, column=0, columnspan=4, sticky='w', pady=(2, 0), padx=5)

        # ---- 参数实时提示行 ----
        self.param_hint_var = tk.StringVar(value="")
        self.param_hint_label = ttkb.Label(
            params_frame,
            textvariable=self.param_hint_var,
            style="ParamHint.TLabel",
            wraplength=800,
            justify=LEFT,
            anchor='w',
        )
        self.param_hint_label.grid(row=5, column=0, columnspan=3,
                                   sticky='ew', pady=(6, 0), padx=5)

        self.apply_digits_btn = ttkb.Button(
            params_frame,
            text="应用建议位数",
            command=self._apply_suggested_digits,
            bootstyle="warning-outline",
            state='disabled',
            width=14,
        )
        self.apply_digits_btn.grid(row=5, column=3, sticky='e',
                                   pady=(6, 0), padx=5)

        for var in (self.start_number, self.increment, self.digits):
            var.trace_add('write', self._schedule_param_check)

        self.file_prefix.trace_add('write', self._schedule_param_check)
        self.file_extension.trace_add('write', self._schedule_param_check)

        self.filter_ext_var.trace_add('write', self._schedule_filter_refresh)

        # ---- 排序设置 ----
        sort_frame = ttkb.Labelframe(main_frame, text="排序方式", padding=10,
                                     style="Section.TLabelframe")
        sort_frame.grid(row=3, column=0, columnspan=3, sticky='ew', pady=6)

        ttkb.Label(sort_frame, text="排序依据:", font=self.font).pack(side=LEFT, padx=5)
        self.sort_by = tk.StringVar(value="名称")
        sort_by_combo = ttkb.Combobox(
            sort_frame, textvariable=self.sort_by,
            values=["名称", "修改时间", "大小", "类型"],
            state="readonly", width=10, font=self.font,
        )
        sort_by_combo.pack(side=LEFT, padx=5)
        sort_by_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_sort(silent=True))

        ttkb.Label(sort_frame, text="排序方向:", font=self.font).pack(side=LEFT, padx=5)
        self.sort_order = tk.StringVar(value="升序")
        sort_order_combo = ttkb.Combobox(
            sort_frame, textvariable=self.sort_order,
            values=["升序", "降序"],
            state="readonly", width=8, font=self.font,
        )
        sort_order_combo.pack(side=LEFT, padx=5)
        sort_order_combo.bind("<<ComboboxSelected>>", lambda e: self.apply_sort(silent=True))

        self.apply_sort_btn = ttkb.Button(sort_frame, text="应用排序 (Ctrl+S)",
                                          command=self.on_apply_sort_clicked,
                                          bootstyle="info-outline")
        self.apply_sort_btn.pack(side=LEFT, padx=10)

        ttkb.Label(sort_frame, text="（排序结果决定重命名时的编号顺序）",
                   style="Hint.TLabel").pack(side=LEFT, padx=5)

        # ---- 文件列表 ----
        list_frame = ttkb.Labelframe(main_frame, text="目录文件列表", padding=8,
                                     style="Section.TLabelframe")
        list_frame.grid(row=4, column=0, columnspan=3, sticky='nsew', pady=6)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ("name", "size", "type", "modified")
        self.tree = ttkb.Treeview(list_frame, columns=columns, show="headings",
                                  bootstyle="primary", height=22)

        self.tree.heading("name", text="文件名")
        self.tree.heading("size", text="大小")
        self.tree.heading("type", text="类型")
        self.tree.heading("modified", text="修改时间")

        self.tree.column("name", width=430)
        self.tree.column("size", width=110)
        self.tree.column("type", width=110)
        self.tree.column("modified", width=170)

        self.tree.tag_configure('conflict', foreground='#dc3545')

        scrollbar = ttkb.Scrollbar(list_frame, orient=VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        # ---- 操作按钮 ----
        button_frame = ttkb.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=8)

        self.refresh_btn = ttkb.Button(button_frame, text="刷新文件列表 (F5)",
                                       command=self.refresh_file_list,
                                       bootstyle="secondary")
        self.refresh_btn.pack(side=LEFT, padx=5)

        self.preview_btn = ttkb.Button(button_frame, text="预览重命名 (Ctrl+R)",
                                       command=self.preview_rename,
                                       bootstyle="primary")
        self.preview_btn.pack(side=LEFT, padx=5)

        self.execute_btn = ttkb.Button(button_frame, text="执行重命名 (Ctrl+Enter)",
                                       command=self.execute_rename,
                                       bootstyle="success")
        self.execute_btn.pack(side=LEFT, padx=5)

        # ---- 状态栏 ----
        self.status_var = tk.StringVar(value="就绪  ·  按 F1 查看快捷键")
        self.status_label = ttkb.Label(
            main_frame,
            textvariable=self.status_var,
            anchor=W, padding=(8, 4),
            font=self.font,
            bootstyle=self.STATUS_IDLE,
        )
        self.status_label.grid(row=6, column=0, columnspan=3, sticky='ew', pady=(4, 0))

        self.dir_path.trace("w", self.on_directory_changed)

        self.files = []
        self.all_files_count = 0

        self._center_window(win_w, win_h)

        # ★ 绑定快捷键（必须在 UI 全部构建完成后）
        self._bind_shortcuts()

    # ------------------------------------------------------------------
    # ★ 快捷键系统
    # ------------------------------------------------------------------
    def _bind_shortcuts(self):
        """绑定所有键盘快捷键"""
        self._log("绑定快捷键")

        mappings = [
            # 文件操作
            ("<Control-o>", self._sc_browse),
            ("<Control-O>", self._sc_browse),
            ("<F5>", self._sc_refresh),

            # 重命名
            ("<Control-r>", self._sc_preview),
            ("<Control-R>", self._sc_preview),
            ("<Control-Return>", self._sc_execute),

            # 排序
            ("<Control-s>", self._sc_apply_sort),
            ("<Control-S>", self._sc_apply_sort),
            ("<Control-Key-1>", lambda: self._sc_sort_by("名称")),
            ("<Control-Key-2>", lambda: self._sc_sort_by("修改时间")),
            ("<Control-Key-3>", lambda: self._sc_sort_by("大小")),
            ("<Control-Key-4>", lambda: self._sc_sort_by("类型")),
            ("<Control-d>", self._sc_toggle_order),
            ("<Control-D>", self._sc_toggle_order),

            # 帮助 / 退出
            ("<F1>", self._shortcut_show_help),
            ("<Control-q>", self._sc_quit),
            ("<Control-Q>", self._sc_quit),
        ]

        for seq, handler in mappings:
            wrapper = self._make_safe_handler(handler)
            try:
                self.root.bind_all(seq, wrapper)
            except Exception as e:
                self._log(f"绑定快捷键失败 {seq}: {e}")

    def _make_safe_handler(self, handler):
        """生成一个安全的快捷键处理函数：检查模态窗口、捕获异常"""

        def wrapper(event=None):
            # 模态窗口打开时，快捷键失效（避免在对话框里意外触发主窗口操作）
            if self._progress_window is not None:
                return
            try:
                current_grab = self.root.grab_current()
                if current_grab is not None and current_grab != self.root:
                    return
            except Exception:
                pass

            try:
                handler()
            except Exception as e:
                self._log(f"快捷键处理异常：{e}\n{traceback.format_exc()}")

        return wrapper

    # ---- 各快捷键处理函数 ----

    def _sc_browse(self):
        self._log("快捷键：Ctrl+O 打开目录")
        self.browse_directory()

    def _sc_refresh(self):
        self._log("快捷键：F5 刷新")
        if not self.dir_path.get():
            self.set_status("请先选择目录（Ctrl+O）", kind=self.STATUS_WARNING)
            return
        self.refresh_file_list()

    def _sc_preview(self):
        self._log("快捷键：Ctrl+R 预览")
        self.preview_rename()

    def _sc_execute(self):
        self._log("快捷键：Ctrl+Enter 执行")
        self.execute_rename()

    def _sc_apply_sort(self):
        self._log("快捷键：Ctrl+S 应用排序")
        self.on_apply_sort_clicked()

    def _sc_sort_by(self, by):
        self._log(f"快捷键：排序依据 → {by}")
        if not self.files:
            self.set_status("目录中没有文件", kind=self.STATUS_WARNING)
            return
        self.sort_by.set(by)
        self.apply_sort(silent=True)

    def _sc_toggle_order(self):
        self._log("快捷键：Ctrl+D 切换排序方向")
        if not self.files:
            self.set_status("目录中没有文件", kind=self.STATUS_WARNING)
            return
        current = self.sort_order.get()
        self.sort_order.set("降序" if current == "升序" else "升序")
        self.apply_sort(silent=True)

    def _sc_quit(self):
        self._log("快捷键：Ctrl+Q 退出")
        if self._ask_yes_no("确定要退出程序吗？", "退出确认"):
            self.root.quit()

    def _shortcut_show_help(self):
        self._log("快捷键：F1 帮助")
        self._show_shortcuts_help()

    # ---- 帮助对话框 ----

    def _show_shortcuts_help(self):
        """显示快捷键帮助对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("键盘快捷键")
        dialog.resizable(False, False)
        dialog.transient(self.root)

        # 顶部标题
        header = ttkb.Frame(dialog, padding=(20, 15, 20, 5))
        header.pack(fill=X)

        ttkb.Label(
            header, text="键盘快捷键",
            font=("微软雅黑", 14, "bold"),
        ).pack(anchor=W)

        ttkb.Label(
            header, text="使用以下快捷键可以更快速操作",
            font=self.hint_font, foreground="gray",
        ).pack(anchor=W, pady=(2, 0))

        # 分隔线
        ttkb.Separator(dialog, orient=HORIZONTAL).pack(fill=X, padx=20, pady=5)

        # 快捷键列表
        body = ttkb.Frame(dialog, padding=(20, 5, 20, 10))
        body.pack(fill=BOTH, expand=True)

        for i, (seq, desc) in enumerate(self.SHORTCUTS):
            row = ttkb.Frame(body)
            row.pack(fill=X, pady=3)

            # 快捷键徽章
            ttkb.Label(
                row, text=f" {seq} ",
                font=("Consolas", 10, "bold"),
                bootstyle="primary-inverse",
                padding=(6, 2),
            ).pack(side=LEFT)

            ttkb.Label(
                row, text=desc,
                font=self.font,
                padding=(15, 0, 0, 0),
            ).pack(side=LEFT)

        # 底部按钮
        btn_frame = ttkb.Frame(dialog, padding=(20, 10, 20, 20))
        btn_frame.pack(side=BOTTOM, fill=X)

        ttkb.Button(
            btn_frame, text="关闭", command=dialog.destroy,
            bootstyle="primary", width=10,
        ).pack(side=RIGHT)

        # 尺寸自适应
        dialog.update_idletasks()
        w = max(480, dialog.winfo_reqwidth())
        h = dialog.winfo_reqheight()

        rx = self.root.winfo_x() + max(0, (self.root.winfo_width() - w) // 2)
        ry = self.root.winfo_y() + max(0, (self.root.winfo_height() - h) // 2)
        dialog.geometry(f"{w}x{h}+{rx}+{ry}")

        try:
            dialog.grab_set()
        except tk.TclError:
            pass

        # Esc 关闭
        dialog.bind("<Escape>", lambda e: dialog.destroy())

        # 焦点放在关闭按钮上
        dialog.focus_force()

        self.root.wait_window(dialog)

    # ------------------------------------------------------------------
    # 调试日志
    # ------------------------------------------------------------------
    def _log(self, msg):
        try:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 确认对话框
    # ------------------------------------------------------------------
    def _ask_yes_no(self, message, title="确认"):
        self._log(f"_ask_yes_no 弹出对话框：{title}")

        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        result = {'value': False}

        def on_yes():
            result['value'] = True
            dialog.destroy()

        def on_no():
            result['value'] = False
            dialog.destroy()

        # 按钮区先 pack 到 BOTTOM
        btn_frame = ttkb.Frame(dialog, padding=(20, 10, 20, 20))
        btn_frame.pack(side=BOTTOM, fill=X)

        yes_btn = ttkb.Button(
            btn_frame, text="是", command=on_yes,
            bootstyle="success", width=10,
        )
        yes_btn.pack(side=RIGHT, padx=(5, 0))

        no_btn = ttkb.Button(
            btn_frame, text="否", command=on_no,
            bootstyle="secondary", width=10,
        )
        no_btn.pack(side=RIGHT, padx=(0, 5))

        # 消息区放在 TOP
        msg_frame = ttkb.Frame(dialog, padding=(20, 20, 20, 0))
        msg_frame.pack(side=TOP, fill=BOTH, expand=True)

        estimated_lines = 0
        for line in message.split('\n'):
            estimated_lines += max(1, len(line) // 60 + 1)

        use_scroll = estimated_lines > 14

        if use_scroll:
            text_wrap = ttkb.Frame(msg_frame)
            text_wrap.pack(fill=BOTH, expand=True)

            text_widget = tk.Text(
                text_wrap, wrap='word', font=self.font,
                relief='flat', borderwidth=0,
                highlightthickness=0,
                height=14, width=60,
                background=dialog.cget("background") or "#ffffff",
            )
            text_widget.insert('1.0', message)
            text_widget.configure(state='disabled')

            sb = ttkb.Scrollbar(text_wrap, orient=VERTICAL, command=text_widget.yview)
            text_widget.configure(yscrollcommand=sb.set)

            text_widget.pack(side=LEFT, fill=BOTH, expand=True)
            sb.pack(side=RIGHT, fill=Y)
        else:
            ttkb.Label(
                msg_frame, text=message, font=self.font,
                wraplength=520, justify=LEFT, anchor='w',
            ).pack(fill=X)

        dialog.protocol("WM_DELETE_WINDOW", on_no)

        dialog.update_idletasks()
        w = max(560, dialog.winfo_reqwidth())
        h = dialog.winfo_reqheight()

        screen_h = dialog.winfo_screenheight()
        max_h = int(screen_h * 0.8)
        if h > max_h:
            h = max_h

        rx = self.root.winfo_x() + max(0, (self.root.winfo_width() - w) // 2)
        ry = self.root.winfo_y() + max(0, (self.root.winfo_height() - h) // 2)
        dialog.geometry(f"{w}x{h}+{rx}+{ry}")

        try:
            dialog.grab_set()
        except tk.TclError as e:
            self._log(f"dialog.grab_set 失败（忽略）：{e}")

        no_btn.focus_force()

        # Esc = 否
        dialog.bind("<Escape>", lambda e: on_no())
        # Enter = 否（安全默认）
        dialog.bind("<Return>", lambda e: on_no())

        self.root.wait_window(dialog)
        self._log(f"_ask_yes_no 结果：{result['value']}")
        return result['value']

    # ------------------------------------------------------------------
    # 进度对话框
    # ------------------------------------------------------------------
    def _open_progress_window(self, total):
        try:
            win = tk.Toplevel(self.root)
            win.title("正在重命名")
            win.resizable(False, False)
            win.transient(self.root)

            self.root.update_idletasks()
            win_w = 580
            win_h = 200
            rx = self.root.winfo_x() + (self.root.winfo_width() - win_w) // 2
            ry = self.root.winfo_y() + (self.root.winfo_height() - win_h) // 2
            win.geometry(f"{win_w}x{win_h}+{rx}+{ry}")

            frame = ttkb.Frame(win, padding=20)
            frame.pack(fill=BOTH, expand=True)

            ttkb.Label(frame, text="正在处理文件...", font=self.font_bold,
                       anchor=W).pack(fill=X, pady=(0, 8))

            self._progress_label = ttkb.Label(
                frame,
                text=f"准备中...  0 / {total}",
                font=self.font,
                anchor=W,
                justify=LEFT,
                wraplength=520,
            )
            self._progress_label.pack(fill=X, pady=(0, 10))

            self._progress_bar = ttkb.Progressbar(
                frame, maximum=total, value=0,
                bootstyle="success",
                mode='determinate',
            )
            self._progress_bar.pack(fill=X, pady=(0, 15))

            btn_frame = ttkb.Frame(frame)
            btn_frame.pack(fill=X)
            self._cancel_btn = ttkb.Button(
                btn_frame, text="取消",
                command=self._on_cancel_clicked,
                bootstyle="danger-outline",
                width=12,
            )
            self._cancel_btn.pack(side=RIGHT)

            self._progress_window = win
            win.protocol("WM_DELETE_WINDOW", self._on_cancel_clicked)

            try:
                win.grab_set()
            except tk.TclError as e:
                self._log(f"进度窗口 grab_set 失败（忽略）：{e}")

            win.focus_force()
            self._log(f"进度窗口已打开，total={total}")
            return True

        except Exception as e:
            self._log(f"打开进度窗口失败：{e}\n{traceback.format_exc()}")
            self._progress_window = None
            self._progress_bar = None
            self._progress_label = None
            self._cancel_btn = None
            return False

    def _close_progress_window(self):
        if self._progress_window is None:
            return
        try:
            self._progress_window.grab_release()
        except Exception:
            pass
        try:
            self._progress_window.destroy()
        except Exception:
            pass
        self._progress_window = None
        self._progress_bar = None
        self._progress_label = None
        self._cancel_btn = None

    def _update_progress_ui(self, stage, current, total, old, new):
        if self._progress_bar is None or self._progress_label is None:
            return
        try:
            stage_name = "准备阶段" if stage == 1 else "完成阶段"
            text = f"{stage_name}：{current} / {total}\n{old}  →  {new}"
            self._progress_label.configure(text=text)
            self._progress_bar.configure(value=current)
        except Exception as e:
            self._log(f"更新进度 UI 失败：{e}")

    def _on_cancel_clicked(self):
        if self._cancel_event.is_set():
            return
        self._cancel_event.set()
        self._log("用户点击了取消按钮")
        try:
            self._cancel_btn.configure(state='disabled', text="正在取消...")
            self._progress_label.configure(text="正在取消，请稍候...")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 工作线程
    # ------------------------------------------------------------------
    def _rename_worker(self, directory, mappings):
        self._log(f"工作线程启动：{len(mappings)} 个文件")

        def progress_callback(stage, current, total, old, new):
            self._progress_queue.put(('progress', stage, current, total, old, new))

        def cancel_check():
            return self._cancel_event.is_set()

        try:
            result = self._two_phase_rename(
                directory, mappings,
                progress_callback=progress_callback,
                cancel_check=cancel_check,
            )
            self._log(f"工作线程完成：success={result['success']}, "
                      f"renamed={result['renamed']}")
        except Exception as e:
            self._log(f"工作线程异常：{e}\n{traceback.format_exc()}")
            result = {
                'success': False,
                'renamed': 0,
                'errors': [f"未预期的内部错误：{e}"],
                'rollback_errors': [],
                'cancelled': False,
            }

        self._progress_queue.put(('done', result))

    def _poll_worker_queue(self):
        self._poll_after_id = None
        if self._progress_queue is None:
            return

        done = False
        try:
            while True:
                msg = self._progress_queue.get_nowait()
                if msg[0] == 'progress':
                    _, stage, current, total, old, new = msg
                    self._update_progress_ui(stage, current, total, old, new)
                elif msg[0] == 'done':
                    _, result = msg
                    self._on_rename_complete(result)
                    done = True
                    break
        except queue.Empty:
            pass

        if not done:
            self._poll_after_id = self.root.after(100, self._poll_worker_queue)

    def _on_rename_complete(self, result):
        self._log(f"_on_rename_complete：{result}")
        self._close_progress_window()

        was_cancelled = result.get('cancelled', False)

        if result['success']:
            Messagebox.show_info(
                f"重命名完成！\n成功：{result['renamed']} 个文件",
                "完成", parent=self.root)
            self.set_status(
                f"✓ 重命名完成，成功 {result['renamed']} 个文件",
                kind=self.STATUS_SUCCESS)
        elif was_cancelled:
            if result['rollback_errors']:
                msg = "已取消重命名，但部分文件未能自动回滚。\n\n"
                msg += f"【未回滚的文件】（共 {len(result['rollback_errors'])} 个，需手动处理）\n"
                for e in result['rollback_errors'][:10]:
                    msg += f"  · {e}\n"
                if len(result['rollback_errors']) > 10:
                    msg += f"  ……（还有 {len(result['rollback_errors']) - 10} 个未列出）\n"
                msg += "\n请根据上述「当前实际名称」在文件管理器中手动恢复。"
                Messagebox.show_error(msg, "已取消（部分未回滚）", parent=self.root)
                self.set_status("✗ 已取消，但有文件未回滚", kind=self.STATUS_ERROR)
            else:
                Messagebox.show_info(
                    "已取消重命名，所有文件已恢复到初始状态。",
                    "已取消", parent=self.root)
                self.set_status("已取消，所有文件已回滚到初始状态",
                                kind=self.STATUS_WARNING)
        else:
            msg = self._format_failure_message(result)
            if result['rollback_errors']:
                Messagebox.show_error(msg, "失败（部分未回滚）", parent=self.root)
                self.set_status(
                    f"✗ 重命名失败，{len(result['rollback_errors'])} 个文件未回滚",
                    kind=self.STATUS_ERROR)
            else:
                Messagebox.show_error(msg, "失败（已回滚）", parent=self.root)
                self.set_status("✗ 重命名失败，所有文件已回滚到初始状态",
                                kind=self.STATUS_ERROR)

        self.preview_data = None
        self.preview_signature = None
        self._set_buttons_state('normal')
        self.refresh_file_list()

    def _set_buttons_state(self, state):
        for btn in (self.execute_btn, self.preview_btn,
                    self.refresh_btn, self.browse_btn):
            try:
                btn.configure(state=state)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 窗口居中
    # ------------------------------------------------------------------
    def _center_window(self, win_w, win_h):
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - win_w) // 2)
        y = max(0, (screen_h - win_h) // 2 - 20)
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")

    # ------------------------------------------------------------------
    # 主题与样式
    # ------------------------------------------------------------------
    def _apply_custom_styles(self):
        self.style.configure("Title.TLabel", font=self.title_font)
        self.style.configure("Hint.TLabel", font=self.hint_font, foreground="gray")
        self.style.configure("Section.TLabelframe", font=self.font_bold, padding=(10, 10))
        self.style.configure("Section.TLabelframe.Label", font=self.font_bold)
        self.style.configure("Treeview", font=self.font, rowheight=26)
        self.style.configure("Treeview.Heading", font=self.font_bold)
        self.style.configure(
            "ParamHint.TLabel",
            font=self.font,
            foreground=self.style.colors.warning,
        )
        self._refresh_combobox_style()

    def _refresh_combobox_style(self):
        colors = self.style.colors
        field_bg = getattr(colors, "inputbg", colors.bg)
        field_fg = getattr(colors, "inputfg", colors.fg)
        border = getattr(colors, "border", colors.bg)

        try:
            self.style.configure(
                "TCombobox",
                fieldbackground=field_bg, background=colors.bg,
                foreground=field_fg, arrowcolor=colors.fg,
                bordercolor=border, lightcolor=field_bg, darkcolor=field_bg,
                selectbackground=field_bg, selectforeground=field_fg,
            )
            self.style.map(
                "TCombobox",
                fieldbackground=[("readonly", field_bg), ("focus", field_bg), ("!disabled", field_bg)],
                foreground=[("readonly", field_fg), ("focus", field_fg)],
                selectbackground=[("readonly", field_bg), ("focus", field_bg)],
                selectforeground=[("readonly", field_fg), ("focus", field_fg)],
                background=[("active", colors.bg), ("pressed", colors.bg)],
            )
        except Exception:
            pass

        try:
            self.root.option_add("*TCombobox*Listbox.background", field_bg)
            self.root.option_add("*TCombobox*Listbox.foreground", field_fg)
            self.root.option_add("*TCombobox*Listbox.selectBackground", colors.selectbg)
            self.root.option_add("*TCombobox*Listbox.selectForeground", colors.selectfg)
        except Exception:
            pass

    def _on_theme_change(self, event=None):
        selected_display = self.theme_display_var.get()
        english_name = None
        for eng, chn in self.theme_name_map.items():
            if chn == selected_display:
                english_name = eng
                break
        if english_name is None:
            english_name = selected_display

        self.current_theme.set(english_name)
        self.style.theme_use(english_name)
        self._apply_custom_styles()

        self.root.update_idletasks()
        for w in self._all_widgets(self.root):
            if isinstance(w, ttkb.Combobox):
                try:
                    if str(w.cget("state")) == "readonly":
                        w.configure(state="normal")
                        w.configure(state="readonly")
                    w.update_idletasks()
                except Exception:
                    pass

    def _all_widgets(self, parent):
        result = []
        for child in parent.winfo_children():
            result.append(child)
            result.extend(self._all_widgets(child))
        return result

    # ------------------------------------------------------------------
    # 文件过滤
    # ------------------------------------------------------------------
    def _parse_filter(self):
        raw = self.filter_ext_var.get().strip()
        if not raw:
            return None
        exts = set()
        for part in re.split(r'[,;\s]+', raw):
            part = part.strip().lower()
            if not part:
                continue
            if not part.startswith('.'):
                part = '.' + part
            exts.add(part)
        return exts or None

    def _matches_filter(self, name):
        exts = self._parse_filter()
        if exts is None:
            return True
        suffix = Path(name).suffix.lower()
        return suffix in exts

    def _schedule_filter_refresh(self, *args):
        if self._filter_check_after_id is not None:
            try:
                self.root.after_cancel(self._filter_check_after_id)
            except Exception:
                pass
        self._filter_check_after_id = self.root.after(300, self._do_filter_refresh)

    def _do_filter_refresh(self):
        self._filter_check_after_id = None
        directory = self.dir_path.get()
        if directory and os.path.exists(directory):
            self.refresh_file_list()

    # ------------------------------------------------------------------
    # 参数实时检查
    # ------------------------------------------------------------------
    def _schedule_param_check(self, *args):
        if self._param_check_after_id is not None:
            try:
                self.root.after_cancel(self._param_check_after_id)
            except Exception:
                pass
        self._param_check_after_id = self.root.after(300, self._check_params_and_hint)

    def _find_min_decimal_digits(self, start_str, inc_str, count):
        start_str = start_str.strip()
        inc_str = inc_str.strip()

        is_decimal = ('.' in start_str) or ('.' in inc_str)
        if not is_decimal:
            return None
        if count <= 1:
            return 0

        try:
            start = float(start_str)
            inc = float(inc_str)
        except ValueError:
            return None

        for d in range(0, 11):
            seen = set()
            ok = True
            for k in range(count):
                s = f"{start + inc * k:.{d}f}"
                if s in seen:
                    ok = False
                    break
                seen.add(s)
            if ok:
                return d
        return 10

    def _check_params_and_hint(self):
        self._param_check_after_id = None
        self._suggested_digits = None

        try:
            self.apply_digits_btn.configure(state='disabled')
        except Exception:
            pass

        prefix = self.file_prefix.get()
        ext = self.file_extension.get()

        ok, err = self._validate_component(prefix, "文件名前缀")
        if not ok:
            self.param_hint_var.set("⚠ " + err)
            return

        ok, err = self._validate_component(ext, "文件扩展名")
        if not ok:
            self.param_hint_var.set("⚠ " + err)
            return

        ext_stripped = ext.lstrip('.')
        if '.' in ext_stripped:
            self.param_hint_var.set("⚠ 「文件扩展名」中只能有一个点号（如 png 或 .png）")
            return

        start_str = self.start_number.get().strip()
        inc_str = self.increment.get().strip()
        digits_str = self.digits.get().strip()

        if not start_str or not inc_str or not digits_str:
            self.param_hint_var.set("")
            return

        try:
            cur_digits = int(digits_str)
            if cur_digits <= 0:
                self.param_hint_var.set("")
                return
        except ValueError:
            self.param_hint_var.set("")
            return

        count = max(len(self.files), 1)
        min_d = self._find_min_decimal_digits(start_str, inc_str, count)

        if min_d is None:
            self.param_hint_var.set("")
            return

        if min_d > cur_digits:
            self._suggested_digits = min_d
            self.param_hint_var.set(
                f"⚠ 当前「序号位数」为 {cur_digits}，按此设置将产生重复文件名"
                f"（共 {count} 个文件）。建议改为 {min_d}。"
            )
            try:
                self.apply_digits_btn.configure(state='normal')
            except Exception:
                pass
        else:
            self.param_hint_var.set("")

    def _apply_suggested_digits(self):
        if self._suggested_digits is None:
            return
        self.digits.set(str(self._suggested_digits))

    # ------------------------------------------------------------------
    # 排序应用入口
    # ------------------------------------------------------------------
    def on_apply_sort_clicked(self):
        applied = self.apply_sort(silent=False)
        if not applied:
            return
        Messagebox.show_info(
            message=f"已按【{self.sort_by.get()} · {self.sort_order.get()}】排序，"
                    f"共 {len(self.files)} 个文件。\n\n"
                    f"预览和执行重命名时将按此顺序编号。",
            title="排序已应用",
            parent=self.root,
        )

    # ------------------------------------------------------------------
    # 目录 / 文件列表
    # ------------------------------------------------------------------
    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dir_path.set(directory)
            self.refresh_file_list()

    def on_directory_changed(self, *args):
        if os.path.exists(self.dir_path.get()):
            self.refresh_file_list()

    def refresh_file_list(self):
        directory = self.dir_path.get()
        if not directory or not os.path.exists(directory):
            return

        all_files = []
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    stat = os.stat(item_path)
                    all_files.append({
                        'name': item,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime,
                        'type': Path(item).suffix or "文件",
                    })
        except Exception as e:
            Messagebox.show_error(f"无法读取目录: {str(e)}", "错误", parent=self.root)
            return

        self.all_files_count = len(all_files)
        self.files = [f for f in all_files if self._matches_filter(f['name'])]

        self._update_filter_count_label()
        self.apply_sort(silent=True, show_status=False)

        self.preview_data = None
        self.preview_signature = None

        if self._parse_filter() is None:
            self.set_status(f"已加载 {len(self.files)} 个文件",
                            kind=self.STATUS_INFO)
        else:
            self.set_status(
                f"已加载 {len(self.files)} 个文件（过滤 {self.all_files_count - len(self.files)} 个）",
                kind=self.STATUS_INFO)

        self._check_params_and_hint()

    def _update_filter_count_label(self):
        total = self.all_files_count
        matched = len(self.files)
        exts = self._parse_filter()
        if exts is None:
            if total > 0:
                self.filter_count_var.set(f"共 {total} 个文件（未过滤）")
            else:
                self.filter_count_var.set("")
        else:
            if total > 0:
                self.filter_count_var.set(f"匹配 {matched} / 共 {total} 个文件")
            else:
                self.filter_count_var.set("")

    # ------------------------------------------------------------------
    # 排序
    # ------------------------------------------------------------------
    @staticmethod
    def natural_sort_key(s):
        return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

    def apply_sort(self, silent=False, show_status=True):
        if not self.files:
            self.tree.delete(*self.tree.get_children())
            if show_status:
                self.set_status("目录中没有文件，未执行排序",
                                kind=self.STATUS_WARNING)
            return False

        sort_by = self.sort_by.get()
        reverse = (self.sort_order.get() == "降序")

        if sort_by == "修改时间":
            key = lambda f: f['mtime']
        elif sort_by == "大小":
            key = lambda f: f['size']
        elif sort_by == "类型":
            key = lambda f: (f['type'], self.natural_sort_key(f['name']))
        else:
            key = lambda f: self.natural_sort_key(f['name'])

        self.files.sort(key=key, reverse=reverse)
        self.populate_tree()

        self.preview_data = None
        self.preview_signature = None

        if show_status:
            self.set_status(
                f"✓ 已按【{sort_by} · {self.sort_order.get()}】排序，共 {len(self.files)} 个文件",
                kind=self.STATUS_SUCCESS)
        return True

    def populate_tree(self):
        self.tree.delete(*self.tree.get_children())
        for f in self.files:
            self.tree.insert("", END, values=(
                f['name'],
                self.format_file_size(f['size']),
                f['type'],
                self.format_time(f['mtime']),
            ))

    def set_status(self, text, kind=None):
        self.status_var.set(text)
        self.status_label.configure(bootstyle=kind or self.STATUS_IDLE)

    def format_file_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        size_names = ["B", "KB", "MB", "GB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        return f"{size_bytes:.1f} {size_names[i]}"

    def format_time(self, timestamp):
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # 序号 / 文件名生成
    # ------------------------------------------------------------------
    def is_decimal_mode(self):
        return ('.' in self.start_number.get().strip()) or ('.' in self.increment.get().strip())

    def build_serial(self, index):
        start_str = self.start_number.get().strip()
        inc_str = self.increment.get().strip()
        digits = int(self.digits.get())
        if self.is_decimal_mode():
            start = float(start_str);
            inc = float(inc_str)
            return f"{start + index * inc:.{digits}f}"
        else:
            start = int(start_str);
            inc = int(inc_str)
            return f"{start + index * inc:0{digits}d}"

    def build_new_filename(self, serial):
        raw_prefix = self.file_prefix.get()
        prefix = raw_prefix.strip()
        file_extension = self.file_extension.get()
        if not file_extension.startswith('.'):
            file_extension = '.' + file_extension
        if prefix == "":
            return f"{serial}{file_extension}"
        return f"{raw_prefix}_{serial}{file_extension}"

    # ------------------------------------------------------------------
    # 预览签名
    # ------------------------------------------------------------------
    def _compute_signature(self):
        file_sig = tuple((f['name'], f['mtime']) for f in self.files)
        param_sig = (
            self.file_prefix.get(),
            self.file_extension.get(),
            self.start_number.get(),
            self.digits.get(),
            self.increment.get(),
            self.filter_ext_var.get(),
        )
        return (file_sig, param_sig)

    # ------------------------------------------------------------------
    # TOCTOU 检测
    # ------------------------------------------------------------------
    def _detect_directory_changes(self):
        directory = self.dir_path.get()
        current = {}
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if os.path.isfile(item_path):
                    try:
                        st = os.stat(item_path)
                        current[item] = st.st_mtime
                    except OSError:
                        pass
        except Exception as e:
            return {
                'changed': True,
                'added': [], 'removed': [], 'modified': [],
                'error': f'无法重新读取目录：{e}',
            }

        snapshot = {f['name']: f['mtime'] for f in self.files}
        current_names = set(current.keys())
        snapshot_names = set(snapshot.keys())

        exts = self._parse_filter()
        if exts is not None:
            current_names = {n for n in current_names if self._matches_filter(n)}
            snapshot_names = {n for n in snapshot_names if self._matches_filter(n)}

        added = sorted(current_names - snapshot_names)
        removed = sorted(snapshot_names - current_names)

        modified = []
        for name in current_names & snapshot_names:
            if abs(current[name] - snapshot[name]) > 1.0:
                modified.append(name)
        modified.sort()

        return {
            'changed': bool(added or removed or modified),
            'added': added,
            'removed': removed,
            'modified': modified,
            'error': None,
        }

    def _show_directory_changed_warning(self, changes):
        lines = []

        if changes.get('error'):
            lines.append(changes['error'])
            lines.append("")
        else:
            lines.append("预览之后，目录内容发生了变化。")
            lines.append("")

        if changes['added']:
            lines.append(f"【新增文件】（{len(changes['added'])} 个）")
            for n in changes['added'][:8]:
                lines.append(f"  · {n}")
            if len(changes['added']) > 8:
                lines.append(f"  ……（还有 {len(changes['added']) - 8} 个）")
            lines.append("")

        if changes['removed']:
            lines.append(f"【被删除的文件】（{len(changes['removed'])} 个）")
            for n in changes['removed'][:8]:
                lines.append(f"  · {n}")
            if len(changes['removed']) > 8:
                lines.append(f"  ……（还有 {len(changes['removed']) - 8} 个）")
            lines.append("")

        if changes['modified']:
            lines.append(f"【被修改的文件】（{len(changes['modified'])} 个）")
            for n in changes['modified'][:8]:
                lines.append(f"  · {n}")
            if len(changes['modified']) > 8:
                lines.append(f"  ……（还有 {len(changes['modified']) - 8} 个）")
            lines.append("")

        lines.append("为避免冲突或数据丢失，请点击「刷新文件列表」，")
        lines.append("再点击「预览重命名」重新确认。")

        Messagebox.show_warning("\n".join(lines), "目录已变化", parent=self.root)

    # ------------------------------------------------------------------
    # 冲突检测
    # ------------------------------------------------------------------
    @staticmethod
    def _norm(name):
        return os.path.normcase(name)

    def _detect_conflicts(self, mappings):
        conflicts = []

        target_map = defaultdict(lambda: {'display': None, 'sources': []})
        for old, new in mappings:
            if old == new:
                continue
            key = self._norm(new)
            if target_map[key]['display'] is None:
                target_map[key]['display'] = new
            target_map[key]['sources'].append(old)

        for key, info in target_map.items():
            if len(info['sources']) > 1:
                conflicts.append({
                    'type': 'duplicate',
                    'target': info['display'],
                    'sources': info['sources'],
                })

        directory = self.dir_path.get()
        try:
            existing = {self._norm(f) for f in os.listdir(directory)}
        except Exception:
            existing = set()

        rename_sources = {self._norm(old) for old, _ in mappings}

        for old, new in mappings:
            if old == new:
                continue
            new_key = self._norm(new)
            old_key = self._norm(old)
            if new_key in existing and new_key != old_key and new_key not in rename_sources:
                conflicts.append({
                    'type': 'overwrite',
                    'source': old,
                    'target': new,
                    'victim': new,
                })

        return conflicts

    def _show_conflict_warning(self, conflicts):
        dup = [c for c in conflicts if c['type'] == 'duplicate']
        over = [c for c in conflicts if c['type'] == 'overwrite']

        lines = []
        lines.append("检测到命名冲突，已禁止执行重命名。\n")

        if dup:
            lines.append(f"【一】目标文件名重复（{len(dup)} 组）：")
            for i, c in enumerate(dup[:5], 1):
                lines.append(f"  {i}. 目标名「{c['target']}」将被以下 "
                             f"{len(c['sources'])} 个文件同时占用：")
                for s in c['sources'][:8]:
                    lines.append(f"        · {s}")
                if len(c['sources']) > 8:
                    lines.append(f"        ……（还有 {len(c['sources']) - 8} 个）")
            if len(dup) > 5:
                lines.append(f"  ……（还有 {len(dup) - 5} 组未列出）")
            lines.append("")

        if over:
            lines.append(f"【二】目标名与现有文件重名（{len(over)} 处）：")
            for c in over[:5]:
                lines.append(f"  · {c['source']}  →  {c['target']}（会覆盖现有文件）")
            if len(over) > 5:
                lines.append(f"  ……（还有 {len(over) - 5} 处未列出）")
            lines.append("")

        lines.append("建议：")
        if dup and self.is_decimal_mode():
            try:
                cur_d = int(self.digits.get())
            except ValueError:
                cur_d = 0
            min_d = self._find_min_decimal_digits(
                self.start_number.get().strip(),
                self.increment.get().strip(),
                len(self.files),
            )
            if min_d is not None and min_d > cur_d:
                lines.append(f"  · 将「序号位数」从 {cur_d} 改为 {min_d}，即可避免重复")
            else:
                lines.append("  · 增大「序号位数」，避免小数精度不足导致重名")
        else:
            lines.append("  · 增大「序号位数」，避免小数精度不足导致重名")
        lines.append("  · 修改「文件名前缀」或「扩展名」")
        lines.append("  · 调整「排序方式」，让编号分配更合理")

        Messagebox.show_error("\n".join(lines), "命名冲突", parent=self.root)

    # ------------------------------------------------------------------
    # 预览
    # ------------------------------------------------------------------
    def preview_rename(self):
        if not self.validate_inputs():
            return

        ok, errs = self._validate_filenames_for_preview()
        if not ok:
            self.preview_data = None
            self.preview_signature = None
            self.set_status("⚠ 检测到非法文件名，已禁止执行",
                            kind=self.STATUS_ERROR)

            msg = "检测到非法文件名，已禁止执行重命名。\n\n"
            for e in errs[:10]:
                msg += f"  · {e}\n"
            if len(errs) > 10:
                msg += f"  ……（共 {len(errs)} 条）\n"
            msg += "\n请修改「文件名前缀」或「文件扩展名」后重试。"

            Messagebox.show_error(msg, "非法文件名", parent=self.root)
            return

        directory = self.dir_path.get()
        if not directory or not os.path.exists(directory):
            Messagebox.show_error("请选择有效的目录", "错误", parent=self.root)
            return
        if not self.files:
            if self.all_files_count > 0:
                Messagebox.show_warning(
                    f"当前过滤条件下没有匹配的文件。\n\n"
                    f"目录中共有 {self.all_files_count} 个文件，但都被"
                    f"「过滤扩展名」条件排除了。\n"
                    f"请调整过滤条件，或留空以处理所有文件。",
                    "无匹配文件", parent=self.root)
            else:
                Messagebox.show_warning("目录中没有文件", "警告", parent=self.root)
            return

        mappings = []
        for index, file_info in enumerate(self.files):
            old = file_info['name']
            serial = self.build_serial(index)
            new = self.build_new_filename(serial)
            mappings.append((old, new))

        conflicts = self._detect_conflicts(mappings)
        conflict_targets = {self._norm(c['target']) for c in conflicts}

        self.tree.delete(*self.tree.get_children())
        for (old, new), file_info in zip(mappings, self.files):
            tags = ('conflict',) if self._norm(new) in conflict_targets else ()
            self.tree.insert("", END, values=(
                f"{old} -> {new}",
                self.format_file_size(file_info['size']),
                file_info['type'],
                self.format_time(file_info['mtime']),
            ), tags=tags)

        if conflicts:
            self.preview_data = None
            self.preview_signature = None
            self.set_status(
                f"⚠ 检测到 {len(conflicts)} 处命名冲突，已禁止执行",
                kind=self.STATUS_ERROR,
            )
            self._show_conflict_warning(conflicts)
            return

        self.preview_data = mappings
        self.preview_signature = self._compute_signature()

        mismatched_count = self._count_extension_mismatches(mappings)

        if mismatched_count > 0:
            self.set_status(
                f"⚠ 预览完成：共 {len(mappings)} 个文件，"
                f"但 {mismatched_count} 个文件的扩展名将改变，请确认",
                kind=self.STATUS_WARNING,
            )
        else:
            self.set_status(
                f"✓ 预览完成：共 {len(mappings)} 个文件，无冲突，可执行重命名 (Ctrl+Enter)",
                kind=self.STATUS_SUCCESS,
            )

    def _count_extension_mismatches(self, mappings):
        out_ext = self.file_extension.get()
        if not out_ext.startswith('.'):
            out_ext = '.' + out_ext
        out_ext = out_ext.lower()

        count = 0
        for old, new in mappings:
            old_ext = Path(old).suffix.lower()
            if old_ext and old_ext != out_ext:
                count += 1
        return count

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------
    def execute_rename(self):
        try:
            self._execute_rename_impl()
        except Exception as e:
            self._log(f"execute_rename 异常：{e}\n{traceback.format_exc()}")
            Messagebox.show_error(
                f"执行重命名时发生异常：\n\n{e}",
                "异常", parent=self.root)

    def _execute_rename_impl(self):
        self._log("execute_rename 被调用")

        if not self.preview_data:
            Messagebox.show_warning(
                "请先点击「预览重命名」，确认无冲突后再执行。\n\n快捷键：Ctrl+R",
                "请先预览", parent=self.root)
            return

        if self._compute_signature() != self.preview_signature:
            self.preview_data = None
            self.preview_signature = None
            Messagebox.show_warning(
                "文件列表或参数已发生变化，请重新预览。",
                "预览已失效", parent=self.root)
            return

        ok, errs = self._validate_filenames_for_preview(self.preview_data)
        if not ok:
            self.preview_data = None
            self.preview_signature = None
            self.set_status("⚠ 检测到非法文件名，已禁止执行",
                            kind=self.STATUS_ERROR)
            msg = "检测到非法文件名，已禁止执行重命名。\n\n"
            for e in errs[:10]:
                msg += f"  · {e}\n"
            if len(errs) > 10:
                msg += f"  ……（共 {len(errs)} 条）\n"
            Messagebox.show_error(msg, "非法文件名", parent=self.root)
            return

        changes = self._detect_directory_changes()
        if changes['changed']:
            self.preview_data = None
            self.preview_signature = None
            self.set_status("⚠ 目录已变化，请重新预览",
                            kind=self.STATUS_WARNING)
            self._show_directory_changed_warning(changes)
            return

        conflicts = self._detect_conflicts(self.preview_data)
        if conflicts:
            self.preview_data = None
            self.preview_signature = None
            self._show_conflict_warning(conflicts)
            return

        mismatched_count = self._count_extension_mismatches(self.preview_data)
        confirm_msg = (
            f"即将重命名 {len(self.preview_data)} 个文件，操作不可撤销。\n\n"
        )
        if mismatched_count > 0:
            out_ext = self.file_extension.get()
            if not out_ext.startswith('.'):
                out_ext = '.' + out_ext
            confirm_msg += (
                f"⚠ 注意：{mismatched_count} 个文件的扩展名将被改为 {out_ext}，"
                f"但文件内容不会转换。\n"
                f"例如 .txt 文件被改成 .png 后，双击可能无法正常打开。\n\n"
            )
        confirm_msg += "是否继续？"

        if not self._ask_yes_no(confirm_msg, "确认重命名"):
            self._log("用户取消了确认，不执行重命名")
            return

        self._log("用户确认，开始重命名")

        self._progress_queue = queue.Queue()
        directory = self.dir_path.get()
        mappings = list(self.preview_data)
        total = len(mappings)

        self._open_progress_window(total)
        self._set_buttons_state('disabled')
        self._cancel_event.clear()

        self.set_status(f"正在重命名 {total} 个文件...",
                        kind=self.STATUS_INFO)

        self._worker_thread = threading.Thread(
            target=self._rename_worker,
            args=(directory, mappings),
            daemon=True,
        )
        self._worker_thread.start()
        self._log("工作线程已启动")

        self._poll_worker_queue()

    # ------------------------------------------------------------------
    # 工作线程核心
    # ------------------------------------------------------------------
    def _two_phase_rename(self, directory, mappings,
                          progress_callback=None, cancel_check=None):
        actual = [(old, new) for old, new in mappings if old != new]
        if not actual:
            return {'success': True, 'renamed': 0,
                    'errors': [], 'rollback_errors': [], 'cancelled': False}

        total = len(actual)

        tmp_prefix = None
        for _ in range(10):
            candidate = f".__rn_tmp_{uuid.uuid4().hex[:8]}__"
            clash = False
            for i in range(total):
                if os.path.exists(os.path.join(directory, f"{candidate}{i:05d}")):
                    clash = True
                    break
            if not clash:
                tmp_prefix = candidate
                break

        if tmp_prefix is None:
            return {
                'success': False, 'renamed': 0,
                'errors': ["无法生成唯一的临时文件名前缀，请检查目录权限或重试"],
                'rollback_errors': [], 'cancelled': False,
            }

        stage1_done = []
        stage1_errors = []

        for i, (old, new) in enumerate(actual):
            if cancel_check and cancel_check():
                stage1_errors.append("用户取消操作")
                break

            src = os.path.join(directory, old)
            temp_name = f"{tmp_prefix}{i:05d}"
            temp_path = os.path.join(directory, temp_name)

            if not os.path.exists(src):
                stage1_errors.append(f"源文件不存在：「{old}」")
                break
            try:
                os.rename(src, temp_path)
                stage1_done.append((old, temp_name, new))
                if progress_callback:
                    progress_callback(1, i + 1, total, old, temp_name)
            except Exception as e:
                stage1_errors.append(f"「{old}」改临时名失败：{e}")
                break

        if stage1_errors:
            _, rb_fail = self._rollback(directory, stage1_done)
            cancelled = any("取消" in e for e in stage1_errors)
            return {
                'success': False, 'renamed': 0,
                'errors': stage1_errors,
                'rollback_errors': rb_fail,
                'cancelled': cancelled,
            }

        stage2_done = []
        stage2_errors = []

        for i, (old, temp_name, new) in enumerate(stage1_done):
            if cancel_check and cancel_check():
                stage2_errors.append("用户取消操作")
                break

            temp_path = os.path.join(directory, temp_name)
            final_path = os.path.join(directory, new)

            if os.path.exists(final_path) and \
                    os.path.abspath(final_path) != os.path.abspath(temp_path):
                stage2_errors.append(f"「{old} → {new}」目标名已被其他文件占用")
                break
            try:
                os.rename(temp_path, final_path)
                stage2_done.append((old, temp_name, new))
                if progress_callback:
                    progress_callback(2, i + 1, total, old, new)
            except Exception as e:
                stage2_errors.append(f"「{old} → {new}」失败：{e}")
                break

        if stage2_errors:
            _, rb_fail = self._rollback(directory, stage1_done)
            cancelled = any("取消" in e for e in stage2_errors)
            return {
                'success': False, 'renamed': 0,
                'errors': stage2_errors,
                'rollback_errors': rb_fail,
                'cancelled': cancelled,
            }

        return {
            'success': True,
            'renamed': len(stage2_done),
            'errors': [],
            'rollback_errors': [],
            'cancelled': False,
        }

    def _rollback(self, directory, stage1_done):
        success = 0
        failures = []

        for old, temp_name, new_name in stage1_done:
            src = os.path.join(directory, old)
            temp_path = os.path.join(directory, temp_name)
            final_path = os.path.join(directory, new_name)

            if os.path.exists(temp_path):
                current_path = temp_path
            elif os.path.exists(final_path):
                current_path = final_path
            elif os.path.exists(src):
                success += 1
                continue
            else:
                failures.append(
                    f"「{old}」：文件已不在预期位置（可能被外部程序移动或删除）"
                )
                continue

            try:
                os.rename(current_path, src)
                success += 1
            except Exception as e:
                current_basename = os.path.basename(current_path)
                failures.append(
                    f"「{old}」：当前实际名称为「{current_basename}」，改回原名失败：{e}"
                )

        return success, failures

    def _format_failure_message(self, result):
        lines = []

        if result['rollback_errors']:
            lines.append("重命名失败，且有部分文件未能自动回滚。\n")
            lines.append("【失败原因】")
            for e in result['errors'][:3]:
                lines.append(f"  · {e}")
            if len(result['errors']) > 3:
                lines.append(f"  ……（共 {len(result['errors'])} 条）")
            lines.append("")
            lines.append(f"【未回滚的文件】（共 {len(result['rollback_errors'])} 个，需手动处理）")
            for e in result['rollback_errors'][:10]:
                lines.append(f"  · {e}")
            if len(result['rollback_errors']) > 10:
                lines.append(f"  ……（还有 {len(result['rollback_errors']) - 10} 个未列出）")
            lines.append("")
            lines.append("请根据上述「当前实际名称」在文件管理器中手动恢复。")
        else:
            lines.append("重命名失败，所有文件已回滚到初始状态。\n")
            lines.append("【失败原因】")
            for e in result['errors'][:5]:
                lines.append(f"  · {e}")
            if len(result['errors']) > 5:
                lines.append(f"  ……（共 {len(result['errors'])} 条）")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # 文件名合法性校验
    # ------------------------------------------------------------------
    INVALID_CHARS = '<>:"/\\|?*'
    RESERVED_NAMES = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
    }
    MAX_NAME_BYTES = 255

    def _validate_component(self, s, name="字段"):
        if s is None or s == "":
            return True, ""

        for ch in s:
            if ch in self.INVALID_CHARS:
                return False, f"「{name}」包含非法字符「{ch}」"
            if ord(ch) < 32:
                return False, f"「{name}」包含控制字符（ASCII {ord(ch)}）"

        return True, ""

    def _validate_output_name(self, filename):
        if not filename:
            return False, "文件名为空"

        for ch in filename:
            if ch in self.INVALID_CHARS:
                return False, f"包含非法字符「{ch}」"
            if ord(ch) < 32:
                return False, f"包含控制字符（ASCII {ord(ch)}）"

        byte_len = len(filename.encode('utf-8'))
        if byte_len > self.MAX_NAME_BYTES:
            return False, (
                f"文件名过长（{byte_len} 字节，超过 {self.MAX_NAME_BYTES} 字节上限）"
            )

        if filename.endswith(' ') or filename.endswith('.'):
            return False, "文件名不能以空格或点号结尾"

        stem = Path(filename).stem.upper()
        if stem in self.RESERVED_NAMES:
            return False, f"使用了系统保留名称「{stem}」"

        return True, ""

    def _validate_filenames_for_preview(self, mappings=None):
        errors = []

        prefix = self.file_prefix.get()
        ok, err = self._validate_component(prefix, "文件名前缀")
        if not ok:
            errors.append(err)

        ext = self.file_extension.get()
        ok, err = self._validate_component(ext, "文件扩展名")
        if not ok:
            errors.append(err)

        ext_stripped = ext.lstrip('.')
        if '.' in ext_stripped:
            errors.append(
                "「文件扩展名」中只能有一个点号（如 png 或 .png，不能是 a.b）"
            )

        if errors:
            return False, errors

        if mappings is None:
            mappings = []
            for index, file_info in enumerate(self.files):
                old = file_info['name']
                try:
                    serial = self.build_serial(index)
                    new = self.build_new_filename(serial)
                    mappings.append((old, new))
                except Exception:
                    continue

        seen_err = set()
        for old, new in mappings:
            ok, err = self._validate_output_name(new)
            if not ok:
                key = err.split('（')[0]
                if key not in seen_err:
                    errors.append(f"目标名「{new}」：{err}")
                    seen_err.add(key)

        return (len(errors) == 0), errors

    # ------------------------------------------------------------------
    # 校验
    # ------------------------------------------------------------------
    def validate_inputs(self):
        directory = self.dir_path.get()
        if not directory or not os.path.exists(directory):
            Messagebox.show_error("请选择有效的目录", "错误", parent=self.root)
            return False
        if not self.file_extension.get():
            Messagebox.show_error("请输入文件扩展名", "错误", parent=self.root)
            return False

        start_str = self.start_number.get().strip()
        try:
            start = float(start_str) if '.' in start_str else int(start_str)
            if start < 0:
                raise ValueError
        except ValueError:
            Messagebox.show_error("起始序号必须是有效的数字（如 1 或 1.1）", "错误", parent=self.root)
            return False

        inc_str = self.increment.get().strip()
        try:
            inc = float(inc_str) if '.' in inc_str else int(inc_str)
            if inc <= 0:
                raise ValueError
        except ValueError:
            Messagebox.show_error("每次增加必须是有效的正数（如 1 或 0.1）", "错误", parent=self.root)
            return False

        try:
            digits = int(self.digits.get())
            if digits <= 0:
                raise ValueError
        except ValueError:
            Messagebox.show_error("序号位数必须是有效的正整数", "错误", parent=self.root)
            return False
        return True


if __name__ == "__main__":
    root = ttkb.Window(title="批量重命名工具", themename="bootstrap-light")
    app = FileRenamerApp(root)
    root.mainloop()
