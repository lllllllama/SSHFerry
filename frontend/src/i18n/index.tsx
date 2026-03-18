import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';

import type { AuthMethod, ProtocolOverride, TaskItem, TaskStatus } from '../api/types';
import type { TaskSocketStatus } from '../store/tasks';
import { formatBytes, formatSpeed, formatTimestamp } from '../utils/format';

export type AppLanguage = 'zh' | 'en';

type TranslationParamValue = string | number | boolean | null | undefined;
type TranslationParams = Record<string, TranslationParamValue>;
type MessageValue = string | ((params: TranslationParams) => string);

const LANGUAGE_STORAGE_KEY = 'sshferry.language';

const LANGUAGE_TO_LOCALE: Record<AppLanguage, string> = {
  zh: 'zh-CN',
  en: 'en-US',
};

const messages: Record<AppLanguage, Record<string, MessageValue>> = {
  zh: {
    'app.title': 'SSHFerry',
    'language.label': '语言',
    'language.zh': '中文',
    'language.en': 'EN',
    'brand.frontend': 'SSHFerry Frontend',
    'nav.workspace': '工作区',
    'nav.tasks': '任务',
    'common.add': '新增',
    'common.edit': '编辑',
    'common.remove': '删除',
    'common.check': '检查',
    'common.refresh': '刷新',
    'common.cancel': '取消',
    'common.close': '关闭',
    'common.confirm': '确认',
    'common.processing': '处理中...',
    'common.save': '保存',
    'common.saving': '保存中...',
    'common.parse': '解析',
    'common.delete': '删除',
    'common.rename': '重命名',
    'common.upload': '上传',
    'common.download': '下载',
    'common.dismiss': '收起',
    'common.selectAll': '全选',
    'common.id': 'ID',
    'common.collapse': '收起',
    'common.expand': '展开',
    'common.name': '名称',
    'common.size': '大小',
    'common.modified': '修改时间',
    'common.direction': '方向',
    'common.engine': '引擎',
    'common.status': '状态',
    'common.progress': '进度',
    'common.speed': '速度',
    'common.current': '当前项',
    'common.actions': '操作',
    'common.total': '总数',
    'common.running': '运行中',
    'common.pending': '排队中',
    'common.failed': '失败',
    'common.done': '完成',
    'common.session': '会话',
    'common.ready': '就绪',
    'common.loading': '加载中',
    'common.booting': '启动中',
    'common.ok': '通过',
    'common.fail': '失败',
    'common.loadingDirectory': '正在加载目录...',
    'common.directoryLoadFailed': '目录加载失败',
    'common.viewFailureDetails': '查看失败详情',
    'common.stale': '已失效',
    'endpoint.local': '本地',
    'endpoint.remote': '远端',
    'protocol.auto': '自动',
    'auth.password': '密码',
    'auth.key': '私钥',
    'socket.idle': '空闲',
    'socket.connecting': '连接中',
    'socket.connected': '已连接',
    'socket.reconnecting': '重连中',
    'socket.polling': '轮询中',
    'socket.error': '异常',
    'task.status.pending': '待处理',
    'task.status.running': '进行中',
    'task.status.paused': '已暂停',
    'task.status.done': '已完成',
    'task.status.failed': '失败',
    'task.status.canceled': '已取消',
    'task.status.skipped': '已跳过',
    'task.action.pause': '暂停',
    'task.action.resume': '继续',
    'task.action.cancel': '取消',
    'task.action.restart': '重试',
    'task.progress.folder': ({ done, total, progress, current }) =>
      `${done}/${total} 文件 · ${progress}%${current || ''}`,
    'task.progress.bytes': ({ progress, done, total }) => `${progress}% · ${done}/${total}`,
    'task.progress.percent': ({ progress }) => `${progress}%`,
    'bootstrap.title': '初始化本地工作区',
    'bootstrap.error': '初始化失败',
    'bootstrap.retry': '重试初始化',
    'bootstrap.description': '正在检查本地 FastAPI 后端、申请本地 token，并准备站点、会话与任务通道。',
    'bootstrap.complete': '准备完成',
    'bootstrap.connecting': '连接中...',
    'workspace.waitTitle': '等待后端初始化',
    'workspace.waitDescription': '正在准备站点、会话与任务通道。',
    'workspace.toast.noUploadSelection': '没有可上传的本地选中项',
    'workspace.toast.uploadSubmitted': '上传任务已提交',
    'workspace.toast.downloadSubmitted': '下载任务已提交',
    'workspace.toast.remoteCopySubmitted': '远端互传任务已提交',
    'workspace.toast.queueSummary': ({ successCount, total }) => `${successCount}/${total} 项已进入后端调度。`,
    'workspace.toast.noDownloadTarget': '缺少下载源或本地目标目录',
    'workspace.toast.noRemoteCopySelection': '没有可复制的远端选中项',
    'workspace.toast.sessionClosed': '远端会话已关闭',
    'topbar.tagline': '本地化多会话传输工作台',
    'topbar.backend': '后端',
    'topbar.taskChannel': '任务通道',
    'topbar.protocol': '协议',
    'topbar.language': '语言',
    'siteSidebar.title': '站点 / 会话',
    'siteSidebar.description': '左侧主操作区，保留站点管理与全局控制。',
    'siteSidebar.protocolOverride': '任务协议覆盖',
    'siteSidebar.sites': '站点',
    'siteSidebar.selectedSite': '当前站点',
    'siteSidebar.openSessions': '已打开会话',
    'siteSidebar.connectionResult': '连接结果',
    'siteSidebar.authSummarySavedPassword': '后端已保存密码，可直接开会话。',
    'siteSidebar.authSummaryRuntimePassword': '密码未保存，打开或检查时会要求输入运行时密码。',
    'siteSidebar.authSummaryKey': '使用私钥认证，密钥路径与高级 SSH 选项保存在站点配置中。',
    'siteSidebar.toast.checkComplete': ({ siteName }) => `连接检查完成: ${siteName}`,
    'siteSidebar.toast.sessionOpened': '远端会话已打开',
    'siteSidebar.toast.sessionOpenedMessage': ({ siteName, sessionId }) => `${siteName} · ${sessionId}`,
    'siteSidebar.toast.sessionClosed': '远端会话已关闭',
    'siteSidebar.toast.siteDeleted': ({ siteName }) => `站点 ${siteName} 已删除`,
    'siteSidebar.confirm.closeSessionTitle': '关闭仍有关联任务的会话',
    'siteSidebar.confirm.closeSessionDescription': ({ sessionId }) =>
      `会话 ${sessionId} 仍有关联中的任务。继续关闭会让当前面板失去上下文。`,
    'siteSidebar.confirm.closeSession': '继续关闭',
    'siteSidebar.confirm.deleteSiteTitle': ({ siteName }) => `删除站点 ${siteName}`,
    'siteSidebar.confirm.deleteSiteDescription': ({ siteName, count }) =>
      `将删除站点 ${siteName}，并关闭 ${count} 个引用它的当前会话。`,
    'siteSidebar.confirm.deleteSite': '删除站点',
    'siteSidebar.connectionLine': ({ status, name, message }) => `${status} · ${name} · ${message}`,
    'siteSidebar.loadError': '站点侧栏加载失败',
    'siteSidebar.secretCheckTitle': '运行时凭据: 连接检查',
    'siteSidebar.secretOpenTitle': '运行时凭据: 打开会话',
    'siteSidebar.secretCheckSubmit': '开始检查',
    'siteSidebar.secretOpenSubmit': '打开会话',
    'siteSidebar.closeSession': '关闭会话',
    'siteEditor.newTitle': '新建站点',
    'siteEditor.editTitle': '编辑站点',
    'siteEditor.description': '对齐后端字段与桌面版表单语义。',
    'siteEditor.quickImport': '从 SSH 命令快速导入',
    'siteEditor.siteName': '站点名称',
    'siteEditor.host': '主机',
    'siteEditor.port': '端口',
    'siteEditor.username': '用户名',
    'siteEditor.remoteRoot': '远端根目录',
    'siteEditor.defaultProtocol': '默认协议',
    'siteEditor.authMethod': '认证方式',
    'siteEditor.password': '密码',
    'siteEditor.rememberPassword': '记住密码',
    'siteEditor.keyPath': '私钥路径',
    'siteEditor.keyPassphrase': '私钥口令',
    'siteEditor.advanced': '高级选项',
    'siteEditor.proxyJump': '跳板机',
    'siteEditor.sshConfigPath': 'SSH 配置路径',
    'siteEditor.sshOptions': 'SSH 选项',
    'siteEditor.passwordPlaceholderSaved': '已保存密码，留空则不覆盖',
    'siteEditor.passwordPlaceholderNew': '输入密码',
    'siteEditor.sshOptionsPlaceholder': '每行一个选项，或使用逗号分隔',
    'siteEditor.parseError': '当前只支持基础 SSH 命令格式：ssh [-p PORT] [USER@]HOST',
    'siteEditor.toast.created': '站点已创建',
    'siteEditor.toast.updated': '站点已更新',
    'siteEditor.toast.savedMessage': ({ siteName }) => `${siteName} 已写入站点列表。`,
    'secret.runtimePassword': '运行时密码',
    'secret.keyPassphrase': '私钥口令',
    'secret.runtimePasswordPlaceholder': '输入本次连接使用的密码',
    'secret.keyPassphrasePlaceholder': '如无私钥口令可留空',
    'taskCenter.title': '任务中心',
    'taskCenter.summary': ({ total, running, pending, failed, done }) =>
      `总数 ${total} · 运行中 ${running} · 排队中 ${pending} · 失败 ${failed} · 完成 ${done}`,
    'taskCenter.openPage': '打开任务页',
    'taskCenter.clearFinished': '清理已完成',
    'taskCenter.toast.actionSubmitted': ({ action }) => `${action}请求已提交`,
    'taskCenter.toast.actionAccepted': ({ successCount, total }) => `${successCount}/${total} 项请求已接受。`,
    'taskCenter.toast.clearedFinished': '已清理终态任务',
    'taskCenter.empty': '当前没有任务。',
    'localPanel.title': '本地面板',
    'localPanel.description': '目录浏览、多选上传、接收远端下载。',
    'localPanel.chooseDrive': '选择盘符',
    'localPanel.pathPlaceholder': '输入本地路径',
    'localPanel.empty': '当前目录为空。',
    'localPanel.loadError': '无法读取本地目录',
    'log.title': '日志区域',
    'log.description': '第二阶段接入统一日志流与任务细节排障视图。',
    'log.placeholderTitle': '预留中',
    'log.placeholderBody': '当前保留布局和视觉占位，不在第一阶段提前发明半成品日志系统。',
    'remoteWorkspace.title': '远端工作区',
    'remoteWorkspace.description': '多会话并排工作区。',
    'remoteWorkspace.emptyTitle': '当前没有打开的远端会话',
    'remoteWorkspace.emptyBody': '从左侧选择站点并打开会话，远端面板会按顺序追加到右侧。',
    'remotePane.deleteTitle': '删除远端路径',
    'remotePane.deleteDescription': ({ labels }) => `将删除以下远端对象：\n${labels}`,
    'remotePane.deleteConfirm': '确认删除',
    'remotePane.deleteToast': '远端删除请求已提交',
    'remotePane.closePane': '关闭面板',
    'remotePane.staleTitle': '会话已失效',
    'remotePane.staleBody': '后端已重启或该会话不存在。请从左侧重新打开站点，或直接关闭当前面板。',
    'remotePane.createDirectoryPrompt': '输入新目录名',
    'remotePane.createDirectoryToast': '远端目录已创建',
    'remotePane.pathPlaceholder': '输入远端路径',
    'remotePane.uploadLocalSelection': '上传本地选中项',
    'remotePane.downloadSelection': '下载选中项',
    'remotePane.renamePrompt': '输入新的文件名或目录名',
    'remotePane.renameToast': '远端路径已重命名',
    'remotePane.empty': '当前远端目录为空。',
    'remotePane.loadError': '无法读取远端目录',
    'http.sessionInvalid': '本地后端会话失效，需要重新初始化。',
    'http.backendNotReadyTitle': '后端未就绪',
    'http.backendNotReadyMessage': '服务可达，但依赖未就绪或当前机器缺少必要能力。',
    'http.requestFailed': '请求失败',
    'http.backendStartupIncomplete': '本地后端尚未完成启动。',
    'http.initFailed': '初始化失败',
    'socket.pollFailed': '任务轮询失败',
    'socket.channelErrorTitle': '任务通道返回错误',
    'socket.websocketError': '任务 WebSocket 连接异常',
  },
  en: {
    'app.title': 'SSHFerry',
    'language.label': 'Language',
    'language.zh': '中文',
    'language.en': 'EN',
    'brand.frontend': 'SSHFerry Frontend',
    'nav.workspace': 'Workspace',
    'nav.tasks': 'Tasks',
    'common.add': 'Add',
    'common.edit': 'Edit',
    'common.remove': 'Remove',
    'common.check': 'Check',
    'common.refresh': 'Refresh',
    'common.cancel': 'Cancel',
    'common.close': 'Close',
    'common.confirm': 'Confirm',
    'common.processing': 'Processing...',
    'common.save': 'Save',
    'common.saving': 'Saving...',
    'common.parse': 'Parse',
    'common.delete': 'Delete',
    'common.rename': 'Rename',
    'common.upload': 'Upload',
    'common.download': 'Download',
    'common.dismiss': 'Dismiss',
    'common.selectAll': 'Select All',
    'common.id': 'ID',
    'common.collapse': 'Collapse',
    'common.expand': 'Expand',
    'common.name': 'Name',
    'common.size': 'Size',
    'common.modified': 'Modified',
    'common.direction': 'Direction',
    'common.engine': 'Engine',
    'common.status': 'Status',
    'common.progress': 'Progress',
    'common.speed': 'Speed',
    'common.current': 'Current',
    'common.actions': 'Actions',
    'common.total': 'Total',
    'common.running': 'Running',
    'common.pending': 'Pending',
    'common.failed': 'Failed',
    'common.done': 'Done',
    'common.session': 'Session',
    'common.ready': 'Ready',
    'common.loading': 'Loading',
    'common.booting': 'Booting',
    'common.ok': 'OK',
    'common.fail': 'FAIL',
    'common.loadingDirectory': 'Loading directory...',
    'common.directoryLoadFailed': 'Directory load failed',
    'common.viewFailureDetails': 'View failure details',
    'common.stale': 'stale',
    'endpoint.local': 'Local',
    'endpoint.remote': 'Remote',
    'protocol.auto': 'Auto',
    'auth.password': 'Password',
    'auth.key': 'Key',
    'socket.idle': 'Idle',
    'socket.connecting': 'Connecting',
    'socket.connected': 'Connected',
    'socket.reconnecting': 'Reconnecting',
    'socket.polling': 'Polling',
    'socket.error': 'Error',
    'task.status.pending': 'Pending',
    'task.status.running': 'Running',
    'task.status.paused': 'Paused',
    'task.status.done': 'Done',
    'task.status.failed': 'Failed',
    'task.status.canceled': 'Canceled',
    'task.status.skipped': 'Skipped',
    'task.action.pause': 'Pause',
    'task.action.resume': 'Resume',
    'task.action.cancel': 'Cancel',
    'task.action.restart': 'Restart',
    'task.progress.folder': ({ done, total, progress, current }) =>
      `${done}/${total} files · ${progress}%${current || ''}`,
    'task.progress.bytes': ({ progress, done, total }) => `${progress}% · ${done}/${total}`,
    'task.progress.percent': ({ progress }) => `${progress}%`,
    'bootstrap.title': 'Initialize Local Workspace',
    'bootstrap.error': 'Initialization failed',
    'bootstrap.retry': 'Retry Initialization',
    'bootstrap.description': 'Checking the local FastAPI backend, requesting a local token, and preparing sites, sessions, and the task channel.',
    'bootstrap.complete': 'Ready',
    'bootstrap.connecting': 'Connecting...',
    'workspace.waitTitle': 'Waiting for Backend Initialization',
    'workspace.waitDescription': 'Preparing sites, sessions, and the task channel.',
    'workspace.toast.noUploadSelection': 'No local selection available for upload',
    'workspace.toast.uploadSubmitted': 'Upload tasks submitted',
    'workspace.toast.downloadSubmitted': 'Download tasks submitted',
    'workspace.toast.remoteCopySubmitted': 'Remote copy tasks submitted',
    'workspace.toast.queueSummary': ({ successCount, total }) => `${successCount}/${total} items entered backend scheduling.`,
    'workspace.toast.noDownloadTarget': 'Missing download source or local target directory',
    'workspace.toast.noRemoteCopySelection': 'No remote selection available for copy',
    'workspace.toast.sessionClosed': 'Remote session closed',
    'topbar.tagline': 'Localized multi-session transfer workspace',
    'topbar.backend': 'Backend',
    'topbar.taskChannel': 'Task WS',
    'topbar.protocol': 'Protocol',
    'topbar.language': 'Language',
    'siteSidebar.title': 'Sites / Sessions',
    'siteSidebar.description': 'Primary control area for site management and global actions.',
    'siteSidebar.protocolOverride': 'Task Protocol Override',
    'siteSidebar.sites': 'Sites',
    'siteSidebar.selectedSite': 'Selected Site',
    'siteSidebar.openSessions': 'Open Sessions',
    'siteSidebar.connectionResult': 'Connection Result',
    'siteSidebar.authSummarySavedPassword': 'The backend already stored the password, so you can open a session directly.',
    'siteSidebar.authSummaryRuntimePassword': 'The password is not stored. Opening or checking will prompt for a runtime password.',
    'siteSidebar.authSummaryKey': 'Key-based authentication is enabled. The key path and advanced SSH options are saved in the site configuration.',
    'siteSidebar.toast.checkComplete': ({ siteName }) => `Connection check completed: ${siteName}`,
    'siteSidebar.toast.sessionOpened': 'Remote session opened',
    'siteSidebar.toast.sessionOpenedMessage': ({ siteName, sessionId }) => `${siteName} · ${sessionId}`,
    'siteSidebar.toast.sessionClosed': 'Remote session closed',
    'siteSidebar.toast.siteDeleted': ({ siteName }) => `Site ${siteName} deleted`,
    'siteSidebar.confirm.closeSessionTitle': 'Close a session with related tasks',
    'siteSidebar.confirm.closeSessionDescription': ({ sessionId }) =>
      `Session ${sessionId} still has related tasks. Continuing will remove the current pane context.`,
    'siteSidebar.confirm.closeSession': 'Close Anyway',
    'siteSidebar.confirm.deleteSiteTitle': ({ siteName }) => `Delete site ${siteName}`,
    'siteSidebar.confirm.deleteSiteDescription': ({ siteName, count }) =>
      `This will delete site ${siteName} and close ${count} active sessions that reference it.`,
    'siteSidebar.confirm.deleteSite': 'Delete Site',
    'siteSidebar.connectionLine': ({ status, name, message }) => `${status} · ${name} · ${message}`,
    'siteSidebar.loadError': 'Failed to load the site sidebar',
    'siteSidebar.secretCheckTitle': 'Runtime Credentials: Connection Check',
    'siteSidebar.secretOpenTitle': 'Runtime Credentials: Open Session',
    'siteSidebar.secretCheckSubmit': 'Start Check',
    'siteSidebar.secretOpenSubmit': 'Open Session',
    'siteSidebar.closeSession': 'Close Session',
    'siteEditor.newTitle': 'New Site',
    'siteEditor.editTitle': 'Edit Site',
    'siteEditor.description': 'Aligned with backend fields and desktop form semantics.',
    'siteEditor.quickImport': 'Quick Import from SSH Command',
    'siteEditor.siteName': 'Site Name',
    'siteEditor.host': 'Host',
    'siteEditor.port': 'Port',
    'siteEditor.username': 'Username',
    'siteEditor.remoteRoot': 'Remote Root',
    'siteEditor.defaultProtocol': 'Default Protocol',
    'siteEditor.authMethod': 'Auth Method',
    'siteEditor.password': 'Password',
    'siteEditor.rememberPassword': 'Remember Password',
    'siteEditor.keyPath': 'Key Path',
    'siteEditor.keyPassphrase': 'Key Passphrase',
    'siteEditor.advanced': 'Advanced',
    'siteEditor.proxyJump': 'Proxy Jump',
    'siteEditor.sshConfigPath': 'SSH Config Path',
    'siteEditor.sshOptions': 'SSH Options',
    'siteEditor.passwordPlaceholderSaved': 'Password already stored. Leave blank to keep it unchanged.',
    'siteEditor.passwordPlaceholderNew': 'Enter password',
    'siteEditor.sshOptionsPlaceholder': 'One option per line, or separate them with commas',
    'siteEditor.parseError': 'Only the basic SSH command format is supported: ssh [-p PORT] [USER@]HOST',
    'siteEditor.toast.created': 'Site created',
    'siteEditor.toast.updated': 'Site updated',
    'siteEditor.toast.savedMessage': ({ siteName }) => `${siteName} has been added to the site list.`,
    'secret.runtimePassword': 'Runtime Password',
    'secret.keyPassphrase': 'Key Passphrase',
    'secret.runtimePasswordPlaceholder': 'Enter the password used for this connection',
    'secret.keyPassphrasePlaceholder': 'Leave blank if the key has no passphrase',
    'taskCenter.title': 'Task Center',
    'taskCenter.summary': ({ total, running, pending, failed, done }) =>
      `Total ${total} · Running ${running} · Pending ${pending} · Failed ${failed} · Done ${done}`,
    'taskCenter.openPage': 'Open Tasks Page',
    'taskCenter.clearFinished': 'Clear Finished',
    'taskCenter.toast.actionSubmitted': ({ action }) => `${action} requests submitted`,
    'taskCenter.toast.actionAccepted': ({ successCount, total }) => `${successCount}/${total} requests accepted.`,
    'taskCenter.toast.clearedFinished': 'Finished tasks cleared',
    'taskCenter.empty': 'No tasks right now.',
    'localPanel.title': 'Local Panel',
    'localPanel.description': 'Browse directories, multi-select uploads, and receive remote downloads.',
    'localPanel.chooseDrive': 'Choose Drive',
    'localPanel.pathPlaceholder': 'Enter local path',
    'localPanel.empty': 'This directory is empty.',
    'localPanel.loadError': 'Unable to read the local directory',
    'log.title': 'Log Area',
    'log.description': 'A unified log stream and task troubleshooting view will be integrated in phase two.',
    'log.placeholderTitle': 'Reserved',
    'log.placeholderBody': 'The layout and visual placeholder stay here for now. We are not inventing a half-finished log system in phase one.',
    'remoteWorkspace.title': 'Remote Workspace',
    'remoteWorkspace.description': 'Side-by-side multi-session workspace.',
    'remoteWorkspace.emptyTitle': 'No remote sessions are open',
    'remoteWorkspace.emptyBody': 'Select a site on the left and open a session. Remote panes will be appended on the right in order.',
    'remotePane.deleteTitle': 'Delete Remote Path',
    'remotePane.deleteDescription': ({ labels }) => `The following remote objects will be deleted:\n${labels}`,
    'remotePane.deleteConfirm': 'Confirm Delete',
    'remotePane.deleteToast': 'Remote delete request submitted',
    'remotePane.closePane': 'Close Pane',
    'remotePane.staleTitle': 'Session Expired',
    'remotePane.staleBody': 'The backend restarted or the session no longer exists. Reopen the site from the left, or close this pane directly.',
    'remotePane.createDirectoryPrompt': 'Enter a new directory name',
    'remotePane.createDirectoryToast': 'Remote directory created',
    'remotePane.pathPlaceholder': 'Enter remote path',
    'remotePane.uploadLocalSelection': 'Upload Local Selection',
    'remotePane.downloadSelection': 'Download Selection',
    'remotePane.renamePrompt': 'Enter a new file or directory name',
    'remotePane.renameToast': 'Remote path renamed',
    'remotePane.empty': 'This remote directory is empty.',
    'remotePane.loadError': 'Unable to read the remote directory',
    'http.sessionInvalid': 'The local backend session is invalid. Re-initialization is required.',
    'http.backendNotReadyTitle': 'Backend Not Ready',
    'http.backendNotReadyMessage': 'The service is reachable, but its dependencies are not ready or required capabilities are missing on this machine.',
    'http.requestFailed': 'Request failed',
    'http.backendStartupIncomplete': 'The local backend has not finished starting yet.',
    'http.initFailed': 'Initialization failed',
    'socket.pollFailed': 'Task polling failed',
    'socket.channelErrorTitle': 'Task channel returned an error',
    'socket.websocketError': 'Task WebSocket connection error',
  },
};

const socketStatusKeys: Record<TaskSocketStatus, string> = {
  idle: 'socket.idle',
  connecting: 'socket.connecting',
  connected: 'socket.connected',
  reconnecting: 'socket.reconnecting',
  polling: 'socket.polling',
  error: 'socket.error',
};

const taskStatusKeys: Record<TaskStatus, string> = {
  pending: 'task.status.pending',
  running: 'task.status.running',
  paused: 'task.status.paused',
  done: 'task.status.done',
  failed: 'task.status.failed',
  canceled: 'task.status.canceled',
  skipped: 'task.status.skipped',
};

const authMethodKeys: Record<AuthMethod, string> = {
  password: 'auth.password',
  key: 'auth.key',
};

const endpointTypeKeys: Record<string, string> = {
  local: 'endpoint.local',
  remote: 'endpoint.remote',
};

function isAppLanguage(value: string | null | undefined): value is AppLanguage {
  return value === 'zh' || value === 'en';
}

function detectInitialLanguage(): AppLanguage {
  if (typeof window !== 'undefined') {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (isAppLanguage(stored)) {
      return stored;
    }
  }

  if (typeof navigator !== 'undefined') {
    return navigator.language.toLowerCase().startsWith('zh') ? 'zh' : 'en';
  }

  return 'en';
}

let currentLanguage: AppLanguage = detectInitialLanguage();

function replaceTemplate(message: string, params: TranslationParams): string {
  return message.replace(/\{(\w+)\}/g, (_, token: string) => String(params[token] ?? ''));
}

export function resolveLocale(language: AppLanguage = currentLanguage): string {
  return LANGUAGE_TO_LOCALE[language];
}

export function setCurrentLanguage(language: AppLanguage): void {
  currentLanguage = language;

  if (typeof window !== 'undefined') {
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  }
  if (typeof document !== 'undefined') {
    document.documentElement.lang = resolveLocale(language);
    document.title = translate('app.title', {}, language);
  }
}

export function translate(key: string, params: TranslationParams = {}, language: AppLanguage = currentLanguage): string {
  const message = messages[language][key] ?? messages.en[key] ?? key;
  if (typeof message === 'function') {
    return message(params);
  }
  return replaceTemplate(message, params);
}

export function formatSocketStatusLabel(status: TaskSocketStatus, language: AppLanguage = currentLanguage): string {
  return translate(socketStatusKeys[status] ?? status, {}, language);
}

export function formatTaskStatusLabel(status: TaskStatus, language: AppLanguage = currentLanguage): string {
  return translate(taskStatusKeys[status] ?? status, {}, language);
}

export function formatProtocolLabel(
  protocol: ProtocolOverride | string,
  language: AppLanguage = currentLanguage,
): string {
  return protocol === 'auto' ? translate('protocol.auto', {}, language) : protocol.toUpperCase();
}

export function formatAuthMethodLabel(method: AuthMethod, language: AppLanguage = currentLanguage): string {
  return translate(authMethodKeys[method], {}, language);
}

export function formatEndpointTypeLabel(endpointType: string, language: AppLanguage = currentLanguage): string {
  const key = endpointTypeKeys[endpointType];
  return key ? translate(key, {}, language) : endpointType;
}

export function formatDirectionLabel(
  sourceType: string,
  targetType: string,
  language: AppLanguage = currentLanguage,
): string {
  return `${formatEndpointTypeLabel(sourceType, language)} -> ${formatEndpointTypeLabel(targetType, language)}`;
}

export function formatDateTimeLabel(
  value: number | null,
  language: AppLanguage = currentLanguage,
): string {
  return formatTimestamp(value, resolveLocale(language));
}

export function formatTaskProgressLabel(
  task: TaskItem,
  language: AppLanguage = currentLanguage,
): string {
  if (task.kind === 'folder_transfer' && task.subtask_count > 0) {
    const current = task.current_file ? ` · ${task.current_file}` : '';
    return translate(
      'task.progress.folder',
      {
        done: task.subtask_done,
        total: task.subtask_count,
        progress: task.progress_percent.toFixed(1),
        current,
      },
      language,
    );
  }

  if (!task.bytes_total) {
    return translate('task.progress.percent', { progress: task.progress_percent.toFixed(1) }, language);
  }

  return translate(
    'task.progress.bytes',
    {
      progress: task.progress_percent.toFixed(1),
      done: formatBytes(task.bytes_done),
      total: formatBytes(task.bytes_total),
    },
    language,
  );
}

interface I18nContextValue {
  language: AppLanguage;
  locale: string;
  setLanguage: (language: AppLanguage) => void;
  t: (key: string, params?: TranslationParams) => string;
  formatDateTime: (value: number | null) => string;
  formatTaskProgress: (task: TaskItem) => string;
  formatTaskStatus: (status: TaskStatus) => string;
  formatSocketStatus: (status: TaskSocketStatus) => string;
  formatProtocol: (protocol: ProtocolOverride | string) => string;
  formatAuthMethod: (method: AuthMethod) => string;
  formatDirection: (sourceType: string, targetType: string) => string;
  formatEndpointType: (endpointType: string) => string;
  formatTransferSpeed: (value: number) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<AppLanguage>(() => detectInitialLanguage());

  useEffect(() => {
    setCurrentLanguage(language);
  }, [language]);

  return (
    <I18nContext.Provider
      value={{
        language,
        locale: resolveLocale(language),
        setLanguage,
        t: (key, params) => translate(key, params, language),
        formatDateTime: (value) => formatDateTimeLabel(value, language),
        formatTaskProgress: (task) => formatTaskProgressLabel(task, language),
        formatTaskStatus: (status) => formatTaskStatusLabel(status, language),
        formatSocketStatus: (status) => formatSocketStatusLabel(status, language),
        formatProtocol: (protocol) => formatProtocolLabel(protocol, language),
        formatAuthMethod: (method) => formatAuthMethodLabel(method, language),
        formatDirection: (sourceType, targetType) => formatDirectionLabel(sourceType, targetType, language),
        formatEndpointType: (endpointType) => formatEndpointTypeLabel(endpointType, language),
        formatTransferSpeed: (value) => formatSpeed(value),
      }}
    >
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return context;
}

