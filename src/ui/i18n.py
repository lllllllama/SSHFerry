"""Lightweight translation layer for the PySide6 desktop UI.

The desktop app ships Simplified Chinese as the default language and keeps an
English map for parity. Strings are keyed by stable identifiers (for example
``"site.add"`` or ``"dialog.delete.title"``); call sites use :func:`tr` which
formats templates with ``str.format`` when keyword arguments are supplied.

Default-language resolution order at import time:

1. ``SSHFERRY_LANG`` environment variable (``zh`` / ``en``).
2. A persisted preference file written by the in-app language menu.
3. The product default, ``zh`` (the OS locale is consulted but Chinese remains
   the default either way).
"""

from __future__ import annotations

import os

SUPPORTED_LANGUAGES = ("zh", "en")
DEFAULT_LANGUAGE = "zh"

_LANG_PREF_FILENAME = "ui_lang"


ZH: dict[str, str] = {
    # Shared actions
    "action.refresh": "刷新",
    "action.close": "关闭",
    "action.clear": "清除",
    "action.rename": "重命名",
    "action.delete": "删除",
    "action.download": "下载",
    "action.new_folder": "新建文件夹",
    "action.browse": "浏览...",
    "action.pause": "暂停",
    "action.resume": "继续",
    "action.cancel": "取消",
    "action.restart": "重试",
    # Navigation
    "nav.up.tooltip": "返回上级目录",
    # Site list (main window)
    "site.section.title": "站点",
    "site.add": "新建站点",
    "site.edit": "编辑站点",
    "site.check": "检测连接",
    "site.remove": "删除站点",
    # Sessions
    "session.connect": "连接",
    "session.disconnect": "断开",
    "session.select.tooltip": "选中该会话以便批量断开",
    "session.status.disconnected": "未连接",
    "session.status.connected": "已连接: {name}",
    "session.status.refreshing": "正在刷新: {name}",
    # Protocol override
    "protocol.override.title": "任务传输协议覆盖",
    "protocol.auto": "自动 (站点默认)",
    # Log panel
    "log.title": "日志",
    "log.hint": "最近运行输出",
    # Top bar summary
    "topbar.sites": "站点: {count}",
    "topbar.sessions": "会话: {count}",
    "topbar.tasks": "活动任务: {count}",
    # Remote empty state
    "remote.empty.title": "暂无打开的远程会话",
    "remote.empty.body": "在左侧选择一个站点, 然后连接以打开远程工作区。",
    "remote.empty.button": "快速连接",
    # Menu bar
    "menu.file": "文件(&F)",
    "menu.new_window": "新建窗口(&N)",
    "menu.open_session": "打开会话",
    "menu.close_window": "关闭窗口(&C)",
    "menu.language": "Language / 语言",
    "menu.language.zh": "中文 (Chinese)",
    "menu.language.en": "English",
    "dialog.language.title": "语言",
    "dialog.language.restart": "语言已切换。请重启应用以完整生效。",
    # Main window dialogs
    "dialog.no_site.title": "未选择站点",
    "dialog.no_site.edit_body": "请选择要编辑的站点。",
    "dialog.no_site.remove_body": "请选择要删除的站点。",
    "dialog.no_site.select_body": "请先选择一个站点。",
    "dialog.remove_site.title": "删除站点",
    "dialog.remove_site.body": "确定删除站点 '{name}' 吗?\n\n这将同时关闭所有正在使用该站点的会话。",
    "dialog.check.title": "连接检测",
    "check.ok": "通过",
    "check.fail": "失败",
    "dialog.password.title": "需要密码",
    "dialog.password.body": "{user}@{host} 的密码:",
    "dialog.error.title": "错误",
    "dialog.delete_remote.title": "删除远程文件",
    "dialog.delete_remote.body": "确定从 {name} 删除 {label} 吗?{detail}",
    "delete.recursive.detail": " (文件夹将被递归删除)",
    "dialog.no_session.title": "无远程会话",
    "dialog.no_session.body": "请先打开或选择一个远程会话。",
    "dialog.open_file_error.title": "打开文件出错",
    "dialog.op_error.title": "{op} 出错",
    "dialog.transfers_active.title": "传输进行中",
    "dialog.transfers_active.body": "仍有 {count} 个传输任务在进行中。仍要关闭吗?",
    # Operation labels
    "op.mkdir": "新建文件夹",
    "op.delete": "删除",
    "op.rename": "重命名",
    # Generic labels
    "label.items": "{count} 项",
    "label.delete_many": "删除 {count} 项",
    # Main window log lines
    "log.checking": "正在检测 {name}...",
    "log.session.opened": "已为 {name} 打开会话",
    "log.stale_list": "[{name}] 已忽略 {path} 的过期列表结果",
    "log.refresh_after_disconnect": "断开连接后正在刷新 {name} ({path})",
    "log.list_failed": "列目录失败 ({path}): {msg}",
    "log.activated": "[{name}] 已打开: {path}",
    "log.open_file_failed": "打开本地文件失败: {error}",
    "log.op_failed": "{op} 失败: {msg}",
    # Task scan / current file text
    "task.scanning.local": "正在扫描本地目录...",
    "task.scanning.remote": "正在扫描远程目录...",
    "task.scan.local_failed": "本地扫描失败 ({path}): {msg}",
    "task.scan.download_failed": "下载扫描失败 ({path}): {msg}",
    "task.scan.remote_failed": "远程传输扫描失败 ({path}): {msg}",
    # Local panel
    "local.title": "本地工作区",
    "local.drive.tooltip": "选择驱动器",
    "local.search.label": "查找",
    "local.search.placeholder": "*.log, .py, 报告, 文件夹名",
    "local.search.tooltip": "按名称、扩展名、通配符或路径片段搜索",
    "local.search.ready": "就绪",
    "local.search.status": "显示 {count} 项 / {query}",
    "menu.open": "打开",
    "menu.upload_active": "上传到当前远程会话",
    "dialog.rename.title": "重命名",
    "dialog.rename.prompt": "新名称:",
    "dialog.rename_error.title": "重命名出错",
    "dialog.delete.title": "删除",
    "dialog.delete.body": "确定删除 {label} 吗?",
    "dialog.delete.in_progress": "已有删除操作正在进行中。",
    "dialog.delete_error.title": "删除出错",
    "dialog.new_folder.title": "新建文件夹",
    "dialog.new_folder.prompt": "文件夹名称:",
    "dialog.create_folder_error.title": "新建文件夹出错",
    # Remote panel
    "remote.path.label": "远程: {path}",
    "col.name": "名称",
    "col.type": "类型",
    "col.size": "大小",
    "col.modified": "修改时间",
    "tree.loading": "加载中...",
    "tree.empty": "(空)",
    "tree.type.dir": "目录",
    "tree.type.file": "文件",
    "menu.upload_here": "上传到此处...",
    "menu.download_folder": "下载文件夹",
    # Task center
    "task.center.title": "任务中心",
    "task.col.id": "ID",
    "task.col.kind": "类型",
    "task.col.status": "状态",
    "task.col.progress": "进度",
    "task.col.speed": "速度",
    "task.col.source": "来源",
    "task.col.destination": "目标",
    "task.select_all": "全选",
    "task.clear_finished": "清除已完成",
    "task.none": "暂无任务",
    "task.summary": "显示 {visible} / {total} 个任务",
    "task.summary.hidden": " (隐藏 {count} 个)",
    "task.progress.files": "{done}/{total} 个文件 ({percent:.1f}%)",
    "task.status.pending": "等待中",
    "task.status.running": "运行中",
    "task.status.paused": "已暂停",
    "task.status.done": "已完成",
    "task.status.failed": "失败",
    "task.status.canceled": "已取消",
    "task.status.skipped": "已跳过",
    "task.kind.file_transfer": "文件传输",
    "task.kind.folder_transfer": "文件夹传输",
    "task.kind.mkdir": "新建目录",
    "task.kind.delete": "删除",
    # Site editor dialog
    "dialog.site.edit_title": "编辑站点",
    "dialog.site.new_title": "新建站点",
    "site.group.import": "从 SSH 命令快速导入",
    "site.ssh.placeholder": "在此粘贴 SSH 命令, 例如:\nssh -p 16921 root@connect.westb.seetacloud.com",
    "site.parse_button": "解析 SSH 命令",
    "site.group.basic": "基本配置",
    "site.field.name": "站点名称:",
    "site.field.host": "主机:",
    "site.field.port": "端口:",
    "site.field.username": "用户名:",
    "site.field.remote_root": "远程根目录 (沙箱):",
    "site.field.protocol": "默认传输协议:",
    "site.group.auth": "认证",
    "site.field.method": "认证方式:",
    "site.password.placeholder": "请输入密码",
    "site.field.password": "密码:",
    "site.remember_password": "将密码保存到 sites.json",
    "site.remember_password.tooltip": "默认关闭。仅在受信任的设备上启用。",
    "site.field.key_path": "密钥路径:",
    "site.key_passphrase.placeholder": "密钥口令 (如需要)",
    "site.field.key_passphrase": "密钥口令:",
    "site.group.advanced": "高级",
    "site.jump.placeholder": "[user@]跳板机[:port] (可选)",
    "site.jump.tooltip": "通过跳板机连接 (ProxyJump)。跳板机会复用该站点的密钥/代理凭据。",
    "site.field.jump_host": "跳板机:",
    "dialog.select_key.title": "选择 SSH 私钥",
    "dialog.select_key.filter": "所有文件 (*)",
    "site.name": "站点名称",
    "site.host": "主机",
    "site.username": "用户名",
    "dialog.missing.title": "缺少必填字段",
    "dialog.missing.body": "请填写以下字段:\n- {fields}",
}


EN: dict[str, str] = {
    # Shared actions
    "action.refresh": "Refresh",
    "action.close": "Close",
    "action.clear": "Clear",
    "action.rename": "Rename",
    "action.delete": "Delete",
    "action.download": "Download",
    "action.new_folder": "New Folder",
    "action.browse": "Browse...",
    "action.pause": "Pause",
    "action.resume": "Resume",
    "action.cancel": "Cancel",
    "action.restart": "Restart",
    # Navigation
    "nav.up.tooltip": "Go to parent directory",
    # Site list (main window)
    "site.section.title": "Sites",
    "site.add": "Add Site",
    "site.edit": "Edit Site",
    "site.check": "Check Connection",
    "site.remove": "Remove Site",
    # Sessions
    "session.connect": "Connect",
    "session.disconnect": "Disconnect",
    "session.select.tooltip": "Select this session for batch disconnect",
    "session.status.disconnected": "Disconnected",
    "session.status.connected": "Connected: {name}",
    "session.status.refreshing": "Refreshing: {name}",
    # Protocol override
    "protocol.override.title": "Task Protocol Override",
    "protocol.auto": "Auto (Site Default)",
    # Log panel
    "log.title": "Log",
    "log.hint": "Recent runtime output",
    # Top bar summary
    "topbar.sites": "Sites: {count}",
    "topbar.sessions": "Sessions: {count}",
    "topbar.tasks": "Active Tasks: {count}",
    # Remote empty state
    "remote.empty.title": "No remote sessions open",
    "remote.empty.body": "Select a site on the left, then connect to open a remote workspace.",
    "remote.empty.button": "Quick Connect",
    # Menu bar
    "menu.file": "&File",
    "menu.new_window": "&New Window",
    "menu.open_session": "Open Session",
    "menu.close_window": "&Close Window",
    "menu.language": "Language / 语言",
    "menu.language.zh": "中文 (Chinese)",
    "menu.language.en": "English",
    "dialog.language.title": "Language",
    "dialog.language.restart": "Language changed. Restart the app for full effect.",
    # Main window dialogs
    "dialog.no_site.title": "No Site Selected",
    "dialog.no_site.edit_body": "Please select a site to edit.",
    "dialog.no_site.remove_body": "Please select a site to remove.",
    "dialog.no_site.select_body": "Select a site first.",
    "dialog.remove_site.title": "Remove Site",
    "dialog.remove_site.body": "Remove site '{name}'?\n\nThis will also close any open sessions using it.",
    "dialog.check.title": "Connection Check",
    "check.ok": "OK",
    "check.fail": "FAIL",
    "dialog.password.title": "Password Required",
    "dialog.password.body": "Password for {user}@{host}:",
    "dialog.error.title": "Error",
    "dialog.delete_remote.title": "Delete Remote",
    "dialog.delete_remote.body": "Delete {label} from {name}?{detail}",
    "delete.recursive.detail": " (folders are removed recursively)",
    "dialog.no_session.title": "No Remote Session",
    "dialog.no_session.body": "Open or select a remote session first.",
    "dialog.open_file_error.title": "Open File Error",
    "dialog.op_error.title": "{op} Error",
    "dialog.transfers_active.title": "Transfers In Progress",
    "dialog.transfers_active.body": "{count} transfer(s) are still active. Close anyway?",
    # Operation labels (English keeps the raw operation token)
    "op.mkdir": "mkdir",
    "op.delete": "delete",
    "op.rename": "rename",
    # Generic labels
    "label.items": "{count} items",
    "label.delete_many": "Delete {count} items",
    # Main window log lines
    "log.checking": "Checking {name}...",
    "log.session.opened": "Opened session for {name}",
    "log.stale_list": "[{name}] Ignored stale list result for {path}",
    "log.refresh_after_disconnect": "Refreshing {name} after disconnect on {path}",
    "log.list_failed": "List failed ({path}): {msg}",
    "log.activated": "[{name}] Activated: {path}",
    "log.open_file_failed": "open local file failed: {error}",
    "log.op_failed": "{op} failed: {msg}",
    # Task scan / current file text
    "task.scanning.local": "Scanning local directory...",
    "task.scanning.remote": "Scanning remote directory...",
    "task.scan.local_failed": "Local scan failed ({path}): {msg}",
    "task.scan.download_failed": "Download scan failed ({path}): {msg}",
    "task.scan.remote_failed": "Remote transfer scan failed ({path}): {msg}",
    # Local panel
    "local.title": "Local Workspace",
    "local.drive.tooltip": "Select drive",
    "local.search.label": "Find",
    "local.search.placeholder": "*.log, .py, report, folder name",
    "local.search.tooltip": "Search by name, extension, wildcard, or path fragment",
    "local.search.ready": "Ready",
    "local.search.status": "{count} visible / {query}",
    "menu.open": "Open",
    "menu.upload_active": "Upload to Active Remote",
    "dialog.rename.title": "Rename",
    "dialog.rename.prompt": "New name:",
    "dialog.rename_error.title": "Rename Error",
    "dialog.delete.title": "Delete",
    "dialog.delete.body": "Delete {label}?",
    "dialog.delete.in_progress": "A delete operation is already in progress.",
    "dialog.delete_error.title": "Delete Error",
    "dialog.new_folder.title": "New Folder",
    "dialog.new_folder.prompt": "Folder name:",
    "dialog.create_folder_error.title": "Create Folder Error",
    # Remote panel
    "remote.path.label": "Remote: {path}",
    "col.name": "Name",
    "col.type": "Type",
    "col.size": "Size",
    "col.modified": "Modified",
    "tree.loading": "Loading...",
    "tree.empty": "(empty)",
    "tree.type.dir": "DIR",
    "tree.type.file": "FILE",
    "menu.upload_here": "Upload here...",
    "menu.download_folder": "Download folder",
    # Task center
    "task.center.title": "Task Center",
    "task.col.id": "ID",
    "task.col.kind": "Kind",
    "task.col.status": "Status",
    "task.col.progress": "Progress",
    "task.col.speed": "Speed",
    "task.col.source": "Source",
    "task.col.destination": "Destination",
    "task.select_all": "Select All",
    "task.clear_finished": "Clear Finished",
    "task.none": "No tasks",
    "task.summary": "Showing {visible} / {total} tasks",
    "task.summary.hidden": " ({count} hidden)",
    "task.progress.files": "{done}/{total} files ({percent:.1f}%)",
    "task.status.pending": "PENDING",
    "task.status.running": "RUNNING",
    "task.status.paused": "PAUSED",
    "task.status.done": "DONE",
    "task.status.failed": "FAILED",
    "task.status.canceled": "CANCELED",
    "task.status.skipped": "SKIPPED",
    "task.kind.file_transfer": "FILE_TRANSFER",
    "task.kind.folder_transfer": "FOLDER_TRANSFER",
    "task.kind.mkdir": "MKDIR",
    "task.kind.delete": "DELETE",
    # Site editor dialog
    "dialog.site.edit_title": "Edit Site",
    "dialog.site.new_title": "New Site",
    "site.group.import": "Quick Import from SSH Command",
    "site.ssh.placeholder": "Paste SSH command here, e.g.:\nssh -p 16921 root@connect.westb.seetacloud.com",
    "site.parse_button": "Parse SSH Command",
    "site.group.basic": "Basic Configuration",
    "site.field.name": "Site Name:",
    "site.field.host": "Host:",
    "site.field.port": "Port:",
    "site.field.username": "Username:",
    "site.field.remote_root": "Remote Root (Sandbox):",
    "site.field.protocol": "Default Transfer Protocol:",
    "site.group.auth": "Authentication",
    "site.field.method": "Method:",
    "site.password.placeholder": "Enter password",
    "site.field.password": "Password:",
    "site.remember_password": "Save password to sites.json",
    "site.remember_password.tooltip": "Disabled by default. Enable only on trusted devices.",
    "site.field.key_path": "Key Path:",
    "site.key_passphrase.placeholder": "Key passphrase (if required)",
    "site.field.key_passphrase": "Key Passphrase:",
    "site.group.advanced": "Advanced",
    "site.jump.placeholder": "[user@]jump-host[:port] (optional)",
    "site.jump.tooltip": (
        "Connect through a jump host (ProxyJump). The jump host reuses this "
        "site's key/agent credentials."
    ),
    "site.field.jump_host": "Jump Host:",
    "dialog.select_key.title": "Select SSH Private Key",
    "dialog.select_key.filter": "All Files (*)",
    "site.name": "Site Name",
    "site.host": "Host",
    "site.username": "Username",
    "dialog.missing.title": "Missing Required Fields",
    "dialog.missing.body": "Please fill in the following fields:\n- {fields}",
}


_TABLES: dict[str, dict[str, str]] = {"zh": ZH, "en": EN}


def _normalize_language(value: str | None) -> str | None:
    if not value:
        return None
    lang = value.strip().lower()
    if lang in SUPPORTED_LANGUAGES:
        return lang
    if lang.startswith("zh"):
        return "zh"
    if lang.startswith("en"):
        return "en"
    return None


def _pref_file_path():
    from src.shared.runtime_paths import app_data_dir

    return app_data_dir() / _LANG_PREF_FILENAME


def _read_saved_language() -> str | None:
    try:
        path = _pref_file_path()
        if path.is_file():
            return _normalize_language(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return None


def _write_saved_language(lang: str) -> None:
    try:
        _pref_file_path().write_text(lang, encoding="utf-8")
    except Exception:
        pass


def _resolve_default_language() -> str:
    env_lang = _normalize_language(os.getenv("SSHFERRY_LANG"))
    if env_lang:
        return env_lang
    saved_lang = _read_saved_language()
    if saved_lang:
        return saved_lang
    # Consult the OS locale as a fallback: a Chinese locale keeps zh, and any
    # other locale still falls through to the product default (also zh).
    try:
        import locale

        if _normalize_language(locale.getlocale()[0]) == "zh":
            return "zh"
    except Exception:
        pass
    return DEFAULT_LANGUAGE


_current_language: str = _resolve_default_language()


def get_language() -> str:
    """Return the currently active UI language code."""
    return _current_language


def set_language(lang: str, persist: bool = False) -> None:
    """Set the active UI language.

    Unknown values fall back to the product default. When ``persist`` is true
    the choice is written to a small preference file so it survives a restart.
    """
    global _current_language
    _current_language = _normalize_language(lang) or DEFAULT_LANGUAGE
    if persist:
        _write_saved_language(_current_language)


def tr(key: str, **kwargs: object) -> str:
    """Return the translated string for ``key`` in the active language.

    Falls back to the English map, then to the key itself, when a translation
    is missing. When keyword arguments are supplied the result is formatted with
    :meth:`str.format`.
    """
    table = _TABLES.get(_current_language, EN)
    template = table.get(key)
    if template is None:
        template = EN.get(key, key)
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template
