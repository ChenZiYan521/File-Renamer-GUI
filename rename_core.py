"""纯逻辑层：映射生成、预览签名、目录快照与差异、冲突检测。

本模块不依赖 tkinter / ttkbootstrap，可脱离界面单独测试。
依赖方向：helpers <- rename_core <- main
"""
import os
from collections import defaultdict

import helpers as H


def build_mappings(files, start_str, inc_str, digits, prefix, ext):
    """按文件顺序生成 [(旧名, 新名), ...]。"""
    mappings = []
    for index, info in enumerate(files):
        serial = H.build_serial(index, start_str, inc_str, digits)
        mappings.append((info['name'], H.build_new_filename(serial, prefix, ext)))
    return mappings


def compute_signature(files, params):
    """预览指纹：文件名 + 纳秒修改时间 + 大小，加参数元组。"""
    file_sig = tuple((f['name'], f['mtime_ns'], f['size']) for f in files)
    return (file_sig, params)


def snapshot_directory(directory):
    """读取目录快照：{文件名: (mtime_ns, 大小)}，只统计普通文件。

    stat 失败的单条目会被跳过（例如读取瞬间被删除），与界面刷新行为一致。
    """
    snapshot = {}
    for item in os.listdir(directory):
        path = os.path.join(directory, item)
        if not os.path.isfile(path):
            continue
        try:
            st = os.stat(path)
        except OSError:
            continue
        snapshot[item] = (st.st_mtime_ns, st.st_size)
    return snapshot


def detect_directory_changes(directory, baseline, raw_filter=None):
    """对比预览时的基线，返回新增/删除/被修改的文件。

    baseline: {文件名: (mtime_ns, 大小)}
    raw_filter: 用户的扩展名过滤串；过滤生效时只看匹配的文件。
    """
    try:
        current = snapshot_directory(directory)
    except Exception as e:
        return {
            'changed': True,
            'added': [], 'removed': [], 'modified': [],
            'error': f'无法重新读取目录：{e}',
        }

    current_names = set(current)
    baseline_names = set(baseline)

    if H.parse_filter(raw_filter) is not None:
        current_names = {n for n in current_names if H.matches_filter(n, raw_filter)}
        baseline_names = {n for n in baseline_names if H.matches_filter(n, raw_filter)}

    added = sorted(current_names - baseline_names)
    removed = sorted(baseline_names - current_names)
    modified = sorted(n for n in current_names & baseline_names
                      if current[n] != baseline[n])

    return {
        'changed': bool(added or removed or modified),
        'added': added, 'removed': removed, 'modified': modified,
        'error': None,
    }


def detect_conflicts(mappings, directory):
    """检测两类冲突：目标名内部重复、目标名与目录中已有条目重名。"""
    conflicts = []

    target_map = defaultdict(lambda: {'display': None, 'sources': []})
    for old, new in mappings:
        if old == new:
            continue
        key = os.path.normcase(new)
        if target_map[key]['display'] is None:
            target_map[key]['display'] = new
        target_map[key]['sources'].append(old)

    for info in target_map.values():
        if len(info['sources']) > 1:
            conflicts.append({
                'type': 'duplicate',
                'target': info['display'],
                'sources': info['sources'],
            })

    try:
        existing = {os.path.normcase(name) for name in os.listdir(directory)}
    except Exception:
        existing = set()

    rename_sources = {os.path.normcase(old) for old, _ in mappings}

    for old, new in mappings:
        if old == new:
            continue
        new_key = os.path.normcase(new)
        old_key = os.path.normcase(old)
        if new_key in existing and new_key != old_key and new_key not in rename_sources:
            conflicts.append({
                'type': 'overwrite',
                'source': old, 'target': new, 'victim': new,
            })

    return conflicts


def count_extension_mismatches(mappings, out_ext):
    """统计「原扩展名与输出扩展名不同」的文件数。"""
    out_ext = (out_ext or '').strip()
    if not out_ext.startswith('.'):
        out_ext = '.' + out_ext
    out_ext = out_ext.lower()

    count = 0
    for old, _new in mappings:
        old_ext = os.path.splitext(old)[1].lower()
        if old_ext and old_ext != out_ext:
            count += 1
    return count