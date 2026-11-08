"""主题与控件样式相关辅助。仅本模块依赖 ttkbootstrap。"""
import tkinter.font as tkfont

import ttkbootstrap as ttkb


# 中文字体优先级：Windows -> macOS -> Linux -> 通用回退
FONT_PRIORITY = (
    "微软雅黑",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
    "DejaVu Sans",
)


def pick_font_family(root):
    """按优先级挑选当前系统可用的字体族，找不到时回退 Tk 默认字体。"""
    try:
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    for name in FONT_PRIORITY:
        if name in available:
            return name
    return "TkDefaultFont"


def all_widgets(parent):
    """递归遍历所有子控件。"""
    result = []
    for child in parent.winfo_children():
        result.append(child)
        result.extend(all_widgets(child))
    return result


def apply_custom_styles(style, fonts):
    style.configure("Title.TLabel", font=fonts['title_font'])
    style.configure("Hint.TLabel", font=fonts['hint_font'], foreground="gray")
    style.configure("Section.TLabelframe", font=fonts['font_bold'], padding=(10, 10))
    style.configure("Section.TLabelframe.Label", font=fonts['font_bold'])
    style.configure("Treeview", font=fonts['font'], rowheight=26)
    style.configure("Treeview.Heading", font=fonts['font_bold'])
    style.configure("ParamHint.TLabel", font=fonts['font'],
                    foreground=style.colors.warning)


def refresh_combobox_style(style, root):
    """修复切换主题后 Combobox 的灰色残留。"""
    colors = style.colors
    field_bg = getattr(colors, "inputbg", colors.bg)
    field_fg = getattr(colors, "inputfg", colors.fg)
    border = getattr(colors, "border", colors.bg)

    try:
        style.configure(
            "TCombobox",
            fieldbackground=field_bg, background=colors.bg,
            foreground=field_fg, arrowcolor=colors.fg,
            bordercolor=border, lightcolor=field_bg, darkcolor=field_bg,
            selectbackground=field_bg, selectforeground=field_fg,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", field_bg), ("focus", field_bg),
                             ("!disabled", field_bg)],
            foreground=[("readonly", field_fg), ("focus", field_fg)],
            selectbackground=[("readonly", field_bg), ("focus", field_bg)],
            selectforeground=[("readonly", field_fg), ("focus", field_fg)],
            background=[("active", colors.bg), ("pressed", colors.bg)],
        )
    except Exception:
        pass

    try:
        root.option_add("*TCombobox*Listbox.background", field_bg)
        root.option_add("*TCombobox*Listbox.foreground", field_fg)
        root.option_add("*TCombobox*Listbox.selectBackground", colors.selectbg)
        root.option_add("*TCombobox*Listbox.selectForeground", colors.selectfg)
    except Exception:
        pass


def force_refresh_comboboxes(root):
    """切换主题后强制重绘所有 Combobox。"""
    root.update_idletasks()
    for w in all_widgets(root):
        if isinstance(w, ttkb.Combobox):
            try:
                if str(w.cget("state")) == "readonly":
                    w.configure(state="normal")
                    w.configure(state="readonly")
                w.update_idletasks()
            except Exception:
                pass