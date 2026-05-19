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
    'language.label': '\u8bed\u8a00',
    'language.zh': '\u4e2d\u6587',
    'language.en': 'EN',
    'brand.frontend': 'SSHFerry \u524d\u7aef',
    'nav.workspace': '\u5de5\u4f5c\u533a',
    'nav.tasks': '\u4efb\u52a1',
    'nav.activity': '\u6d3b\u52a8',
    'nav.debugLogs': '\u8c03\u8bd5\u65e5\u5fd7',
    'nav.logs': '\u65e5\u5fd7',
    'common.add': '\u65b0\u589e',
    'common.edit': '\u7f16\u8f91',
    'common.remove': '\u5220\u9664',
    'common.check': '\u68c0\u6d4b',
    'common.refresh': '\u5237\u65b0',
    'common.cancel': '\u53d6\u6d88',
    'common.clear': '\u6e05\u9664',
    'common.close': '\u5173\u95ed',
    'common.confirm': '\u786e\u8ba4',
    'common.processing': '\u5904\u7406\u4e2d...',
    'common.save': '\u4fdd\u5b58',
    'common.saving': '\u4fdd\u5b58\u4e2d...',
    'common.parse': '\u89e3\u6790',
    'common.delete': '\u5220\u9664',
    'common.rename': '\u91cd\u547d\u540d',
    'common.dismiss': 'Dismiss',
    'common.selectAll': '\u5168\u9009',
    'common.id': 'ID',
    'common.name': '\u540d\u79f0',
    'common.size': 'Size',
    'common.modified': '\u4fee\u6539\u65f6\u95f4',
    'common.direction': '\u65b9\u5411',
    'common.engine': '\u5f15\u64ce',
    'common.status': '\u72b6\u6001',
    'common.progress': '\u8fdb\u5ea6',
    'common.speed': '\u901f\u5ea6',
    'common.current': '\u5f53\u524d',
    'common.actions': '\u64cd\u4f5c',
    'common.session': '\u4f1a\u8bdd',
    'common.ready': '\u5c31\u7eea',
    'common.loading': '\u52a0\u8f7d\u4e2d',
    'common.booting': '\u542f\u52a8\u4e2d',
    'common.ok': 'OK',
    'common.fail': 'Fail',
    'common.loadingDirectory': 'Loading directory...',
    'common.directoryLoadFailed': 'Directory load failed',
    'common.viewFailureDetails': '\u67e5\u770b\u5931\u8d25\u8be6\u60c5',
    'common.stale': '\u5931\u6548',
    'endpoint.local': '\u672c\u5730',
    'endpoint.remote': '\u8fdc\u7aef',
    'endpoint.workspace': '\u5de5\u4f5c\u533a',
    'protocol.auto': '\u81ea\u52a8',
    'auth.password': '\u5bc6\u7801',
    'auth.key': '\u5bc6\u94a5',
    'auth.loginRequired': '\u5f53\u524d\u90e8\u7f72\u73af\u5883\u8fdb\u5165\u5de5\u4f5c\u533a\u524d\u9700\u8981\u5148\u767b\u5f55\u3002',
    'auth.logout': '\u9000\u51fa\u767b\u5f55',
    'auth.loggedOut': '\u5df2\u9000\u51fa\u767b\u5f55\u3002',
    'auth.loginFailed': '\u767b\u5f55\u5931\u8d25',
    'socket.idle': '\u7a7a\u95f2',
    'socket.connecting': '\u8fde\u63a5\u4e2d',
    'socket.connected': '\u5df2\u8fde\u63a5',
    'socket.reconnecting': '\u91cd\u8fde\u4e2d',
    'socket.polling': '\u8f6e\u8be2\u4e2d',
    'socket.error': '\u9519\u8bef',
    'socket.pollFailed': 'Task polling failed',
    'socket.channelErrorTitle': 'Task channel returned an error',
    'socket.websocketError': 'Task WebSocket connection error',
    'socket.logPollFailed': 'Log polling failed',
    'socket.logChannelErrorTitle': 'Log channel returned an error',
    'socket.logWebsocketError': 'Log WebSocket connection error',
    'task.status.pending': 'Pending',
    'task.status.running': 'Running',
    'task.status.paused': 'Paused',
    'task.status.done': 'Done',
    'task.status.failed': 'Failed',
    'task.status.canceled': 'Canceled',
    'task.status.skipped': 'Skipped',
    'task.action.pause': '\u6682\u505c',
    'task.action.resume': '\u7ee7\u7eed',
    'task.action.cancel': '\u53d6\u6d88',
    'task.action.restart': '\u91cd\u8bd5',
    'task.progress.folder': ({ done, total, progress, current }) =>
      `${done}/${total} \u4e2a\u6587\u4ef6 / ${progress}%${current || ''}`,
    'task.progress.bytes': ({ progress, done, total }) => `${progress}% / ${done}/${total}`,
    'task.progress.percent': ({ progress }) => `${progress}%`,
    'bootstrap.title': '\u6b63\u5728\u51c6\u5907 SSHFerry \u5de5\u4f5c\u533a',
    'bootstrap.error': '\u521d\u59cb\u5316\u5931\u8d25',
    'bootstrap.retry': '\u91cd\u8bd5\u521d\u59cb\u5316',
    'bootstrap.description': '\u6b63\u5728\u68c0\u67e5\u540e\u7aef\u5065\u5eb7\u72b6\u6001\u3001\u6062\u590d\u767b\u5f55\u4f1a\u8bdd\uff0c\u5e76\u51c6\u5907\u7ad9\u70b9\u3001\u4f1a\u8bdd\u548c\u4efb\u52a1\u901a\u9053\u3002',
    'bootstrap.complete': '\u5c31\u7eea',
    'bootstrap.connecting': '\u8fde\u63a5\u4e2d...',
    'workspace.waitTitle': '\u7b49\u5f85\u540e\u7aef\u521d\u59cb\u5316',
    'workspace.waitDescription': '\u6b63\u5728\u51c6\u5907\u767b\u5f55\u72b6\u6001\u3001\u7ad9\u70b9\u3001\u4f1a\u8bdd\u548c\u4efb\u52a1\u901a\u9053\u3002',
    'workspace.toast.noUploadSelection': 'No workspace selection available for upload',
    'workspace.toast.uploadSubmitted': 'Upload tasks submitted',
    'workspace.toast.downloadSubmitted': 'Download tasks submitted',
    'workspace.toast.remoteCopySubmitted': 'Remote copy tasks submitted',
    'workspace.toast.queueSummary': ({ successCount, total }) => `${successCount}/${total} items entered backend scheduling.`,
    'workspace.toast.noDownloadTarget': 'Missing download source or workspace target directory',
    'workspace.toast.noRemoteCopySelection': 'No remote selection available for copy',
    'workspace.toast.sessionClosed': 'Remote session closed',
    'workspace.middlePanelMode': '\u4e2d\u95f4\u9762\u677f',
    'workspace.middlePanelDescription': '\u5728\u4e0a\u4f20\u5de5\u4f5c\u533a\u548c\u5df2\u6253\u5f00\u7684\u8fdc\u7aef\u4f1a\u8bdd\u4e4b\u95f4\u5207\u6362\u3002',
    'workspace.middleSession': '\u5f53\u524d\u663e\u793a\u4f1a\u8bdd',
    'workspace.middleRemoteEmptyTitle': '\u8fd9\u91cc\u8fd8\u6ca1\u6709\u8fdc\u7aef\u4f1a\u8bdd',
    'workspace.middleRemoteEmptyBody': '\u8bf7\u5148\u5728\u5de6\u4fa7\u6253\u5f00\u81f3\u5c11\u4e00\u4e2a\u8fdc\u7aef\u4f1a\u8bdd\uff0c\u6216\u8005\u5207\u56de\u5de5\u4f5c\u533a\u9762\u677f\u3002',
    'workspace.secondaryRemoteEmptyTitle': '\u6ca1\u6709\u989d\u5916\u7684\u8fdc\u7aef\u4f1a\u8bdd',
    'workspace.secondaryRemoteEmptyBody': '\u4e2d\u95f4\u9762\u677f\u5df2\u7ecf\u56fa\u5b9a\u4e86\u4e00\u4e2a\u8fdc\u7aef\u4f1a\u8bdd\u3002\u518d\u6253\u5f00\u4e00\u4e2a\u4f1a\u8bdd\u540e\u4f1a\u663e\u793a\u5728\u53f3\u4fa7\u3002',
    'topbar.tagline': '\u591a\u4f1a\u8bdd\u6587\u4ef6\u4f20\u8f93\u5de5\u4f5c\u533a',
    'topbar.backend': '\u540e\u7aef',
    'topbar.activityChannel': '\u6d3b\u52a8\u901a\u9053',
    'topbar.protocol': '\u534f\u8bae',
    'topbar.language': '\u8bed\u8a00',
    'topbar.user': '\u7528\u6237',
    'login.title': '\u767b\u5f55 SSHFerry',
    'login.description': '\u4f7f\u7528\u4f60\u7684 SSHFerry \u8d26\u53f7\u767b\u5f55\uff0c\u6216\u8005\u76f4\u63a5\u521b\u5efa\u65b0\u8d26\u53f7\u8fdb\u5165\u90e8\u7f72\u5de5\u4f5c\u533a\u3002',
    'login.switchPrompt': '\u8fd8\u6ca1\u6709\u8d26\u53f7\uff1f',
    'login.switchAction': '\u53bb\u6ce8\u518c',
    'login.username': '\u7528\u6237\u540d',
    'login.password': '\u5bc6\u7801',
    'auth.captcha': '\u56fe\u5f62\u9a8c\u8bc1\u7801',
    'auth.captchaPlaceholder': '\u8f93\u5165\u9a8c\u8bc1\u7801',
    'auth.refreshCaptcha': '\u6362\u4e00\u5f20',
    'login.usernamePlaceholder': '\u8f93\u5165\u7528\u6237\u540d',
    'login.passwordPlaceholder': '\u8f93\u5165\u5bc6\u7801',
    'login.submit': '\u767b\u5f55',
    'login.submitting': '\u767b\u5f55\u4e2d...',
    'signup.title': '\u6ce8\u518c SSHFerry',
    'signup.description': '\u521b\u5efa\u4e00\u4e2a\u65b0\u8d26\u53f7\uff0c\u6ce8\u518c\u6210\u529f\u540e\u4f1a\u76f4\u63a5\u8fdb\u5165\u5de5\u4f5c\u533a\u3002',
    'signup.username': '\u7528\u6237\u540d',
    'signup.usernamePlaceholder': '\u4f8b\u5982 alice',
    'signup.displayName': '\u663e\u793a\u540d\u79f0',
    'signup.displayNamePlaceholder': '\u9009\u586b\uff0c\u9ed8\u8ba4\u4e3a\u7528\u6237\u540d',
    'signup.password': '\u5bc6\u7801',
    'signup.passwordPlaceholder': '\u81f3\u5c11 8 \u4f4d',
    'signup.confirmPassword': '\u786e\u8ba4\u5bc6\u7801',
    'signup.confirmPasswordPlaceholder': '\u518d\u8f93\u5165\u4e00\u6b21\u5bc6\u7801',
    'signup.submit': '\u521b\u5efa\u8d26\u53f7',
    'signup.submitting': '\u6ce8\u518c\u4e2d...',
    'signup.failed': '\u6ce8\u518c\u5931\u8d25',
    'signup.passwordMismatch': '\u4e24\u6b21\u8f93\u5165\u7684\u5bc6\u7801\u4e0d\u4e00\u81f4\u3002',
    'signup.switchPrompt': '\u5df2\u7ecf\u6709\u8d26\u53f7\uff1f',
    'signup.switchAction': '\u53bb\u767b\u5f55',
    'siteSidebar.title': '\u7ad9\u70b9 / \u4f1a\u8bdd',
    'siteSidebar.description': '\u7ad9\u70b9\u7ba1\u7406\u548c\u5168\u5c40\u64cd\u4f5c\u7684\u4e3b\u63a7\u533a\u57df\u3002',
    'siteSidebar.protocolOverride': '\u4efb\u52a1\u534f\u8bae\u8986\u76d6',
    'siteSidebar.sites': '\u7ad9\u70b9',
    'siteSidebar.selectedSite': '\u5f53\u524d\u9009\u4e2d\u7ad9\u70b9',
    'siteSidebar.openSessions': '\u5df2\u6253\u5f00\u4f1a\u8bdd',
    'siteSidebar.connectionResult': '\u8fde\u63a5\u7ed3\u679c',
    'siteSidebar.authSummarySavedPassword': '\u540e\u7aef\u5df2\u7ecf\u4fdd\u5b58\u4e86\u5bc6\u7801\uff0c\u53ef\u4ee5\u76f4\u63a5\u6253\u5f00\u4f1a\u8bdd\u3002',
    'siteSidebar.authSummaryRuntimePassword': '\u5f53\u524d\u6ca1\u6709\u4fdd\u5b58\u5bc6\u7801\u3002\u68c0\u6d4b\u8fde\u63a5\u6216\u6253\u5f00\u4f1a\u8bdd\u65f6\u4f1a\u63d0\u793a\u8f93\u5165\u8fd0\u884c\u65f6\u5bc6\u7801\u3002',
    'siteSidebar.authSummaryKey': '\u5f53\u524d\u4f7f\u7528\u5bc6\u94a5\u8ba4\u8bc1\u3002\u5bc6\u94a5\u8def\u5f84\u548c\u9ad8\u7ea7 SSH \u9009\u9879\u5df2\u4fdd\u5b58\u5728\u7ad9\u70b9\u914d\u7f6e\u4e2d\u3002',
    'siteSidebar.toast.checkComplete': ({ siteName }) => `Connection check completed: ${siteName}`,
    'siteSidebar.toast.sessionOpened': 'Remote session opened',
    'siteSidebar.toast.sessionOpenedMessage': ({ siteName, sessionId }) => `${siteName} / ${sessionId}`,
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
    'siteSidebar.connectionLine': ({ status, name, message }) => `${status} / ${name} / ${message}`,
    'siteSidebar.loadError': '\u52a0\u8f7d\u7ad9\u70b9\u4fa7\u680f\u5931\u8d25',
    'siteSidebar.secretCheckTitle': '\u8fd0\u884c\u65f6\u51ed\u636e\uff1a\u8fde\u63a5\u68c0\u6d4b',
    'siteSidebar.secretOpenTitle': '\u8fd0\u884c\u65f6\u51ed\u636e\uff1a\u6253\u5f00\u4f1a\u8bdd',
    'siteSidebar.secretCheckSubmit': '\u5f00\u59cb\u68c0\u6d4b',
    'siteSidebar.secretOpenSubmit': '\u6253\u5f00\u4f1a\u8bdd',
    'siteSidebar.closeSession': '\u5173\u95ed\u4f1a\u8bdd',
    'siteEditor.newTitle': '\u65b0\u5efa\u7ad9\u70b9',
    'siteEditor.editTitle': '\u7f16\u8f91\u7ad9\u70b9',
    'siteEditor.description': '\u4e0e\u540e\u7aef\u5b57\u6bb5\u548c\u8868\u5355\u8bed\u4e49\u4fdd\u6301\u4e00\u81f4\u3002',
    'siteEditor.quickImport': '\u4ece SSH \u547d\u4ee4\u5feb\u901f\u5bfc\u5165',
    'siteEditor.siteName': '\u7ad9\u70b9\u540d\u79f0',
    'siteEditor.host': '\u4e3b\u673a',
    'siteEditor.port': '\u7aef\u53e3',
    'siteEditor.username': '\u7528\u6237\u540d',
    'siteEditor.remoteRoot': '\u8fdc\u7aef\u6839\u76ee\u5f55',
    'siteEditor.defaultProtocol': '\u9ed8\u8ba4\u534f\u8bae',
    'siteEditor.authMethod': '\u8ba4\u8bc1\u65b9\u5f0f',
    'siteEditor.password': '\u5bc6\u7801',
    'siteEditor.rememberPassword': '\u8bb0\u4f4f\u5bc6\u7801',
    'siteEditor.keyPath': '\u5bc6\u94a5\u8def\u5f84',
    'siteEditor.keyPassphrase': '\u5bc6\u94a5\u53e3\u4ee4',
    'siteEditor.advanced': '\u9ad8\u7ea7\u9009\u9879',
    'siteEditor.proxyJump': '\u4ee3\u7406\u8df3\u677f',
    'siteEditor.sshConfigPath': 'SSH \u914d\u7f6e\u8def\u5f84',
    'siteEditor.sshOptions': 'SSH \u9009\u9879',
    'siteEditor.passwordPlaceholderSaved': '\u5bc6\u7801\u5df2\u4fdd\u5b58\u3002\u4fdd\u6301\u4e3a\u7a7a\u5373\u53ef\u6cbf\u7528\u539f\u503c\u3002',
    'siteEditor.passwordPlaceholderNew': '\u8f93\u5165\u5bc6\u7801',
    'siteEditor.keyPassphrasePlaceholderSaved': '\u5bc6\u94a5\u53e3\u4ee4\u5df2\u4fdd\u5b58\u3002\u4fdd\u6301\u4e3a\u7a7a\u5373\u53ef\u6cbf\u7528\u539f\u503c\u3002',
    'siteEditor.keyPassphrasePlaceholderNew': '\u5982\u6709\u9700\u8981\uff0c\u8bf7\u8f93\u5165\u5bc6\u94a5\u53e3\u4ee4',
    'siteEditor.sshOptionsPlaceholder': '\u6bcf\u884c\u4e00\u9879\uff0c\u4e5f\u53ef\u4ee5\u7528\u9017\u53f7\u5206\u9694',
    'siteEditor.parseError': '\u53ea\u652f\u6301\u57fa\u672c SSH \u547d\u4ee4\u683c\u5f0f\uff1assh [-p \u7aef\u53e3] [\u7528\u6237@]\u4e3b\u673a',
    'siteEditor.toast.created': '\u7ad9\u70b9\u5df2\u521b\u5efa',
    'siteEditor.toast.updated': '\u7ad9\u70b9\u5df2\u66f4\u65b0',
    'siteEditor.toast.savedMessage': ({ siteName }) => `\u7ad9\u70b9 ${siteName} \u5df2\u52a0\u5165\u7ad9\u70b9\u5217\u8868\u3002`,
    'secret.runtimePassword': '\u8fd0\u884c\u65f6\u5bc6\u7801',
    'secret.keyPassphrase': '\u5bc6\u94a5\u53e3\u4ee4',
    'secret.runtimePasswordPlaceholder': '\u8f93\u5165\u672c\u6b21\u8fde\u63a5\u4f7f\u7528\u7684\u5bc6\u7801',
    'secret.keyPassphrasePlaceholder': '\u82e5\u5bc6\u94a5\u6ca1\u6709\u53e3\u4ee4\uff0c\u8bf7\u4fdd\u6301\u4e3a\u7a7a',
    'taskCenter.title': '\u4efb\u52a1\u4e2d\u5fc3',
    'taskCenter.summary': ({ total, running, pending, failed, done }) =>
      `\u603b\u8ba1 ${total} / \u8fd0\u884c\u4e2d ${running} / \u6392\u961f\u4e2d ${pending} / \u5931\u8d25 ${failed} / \u5b8c\u6210 ${done}`,
    'taskCenter.clearFinished': '\u6e05\u7406\u5df2\u5b8c\u6210',
    'taskCenter.toast.actionSubmitted': ({ action }) => `${action} \u8bf7\u6c42\u5df2\u63d0\u4ea4`,
    'taskCenter.toast.actionAccepted': ({ successCount, total }) => `\u5df2\u53d7\u7406 ${successCount}/${total} \u9879\u8bf7\u6c42\u3002`,
    'taskCenter.toast.clearedFinished': '\u5df2\u6e05\u7406\u5b8c\u6210\u4efb\u52a1',
    'taskCenter.empty': '\u5f53\u524d\u6ca1\u6709\u4efb\u52a1\u3002',
    'localPanel.title': '\u4e0a\u4f20\u5de5\u4f5c\u533a',
    'localPanel.description': '\u7ba1\u7406\u90e8\u7f72\u7528\u6237\u7684\u5de5\u4f5c\u533a\uff0c\u4e0a\u4f20\u6587\u4ef6\u548c\u6587\u4ef6\u5939\uff0c\u5e76\u63a5\u6536\u8fdc\u7aef\u4e0b\u8f7d\u3002',
    'localPanel.localModeTitle': '\u672c\u5730\u6587\u4ef6',
    'localPanel.localModeDescription': '\u76f4\u63a5\u67e5\u770b\u5f53\u524d\u673a\u5668\u7684\u672c\u5730\u6587\u4ef6\uff0c\u65e0\u9700\u5148\u4e0a\u4f20\u5230\u4e2d\u95f4\u5de5\u4f5c\u533a\u3002',
    'localPanel.summary': ({ files, dirs, size }) => `${files} \u4e2a\u6587\u4ef6 / ${dirs} \u4e2a\u76ee\u5f55 / ${size}`,
    'localPanel.pathPlaceholder': '\u8f93\u5165\u5de5\u4f5c\u533a\u8def\u5f84\uff0c\u4f8b\u5982 /releases',
    'localPanel.localModePathPlaceholder': '\u8f93\u5165\u672c\u5730\u8def\u5f84\uff0c\u4f8b\u5982 E:\\\\Projects',
    'localPanel.localModeDrivePlaceholder': '\u9009\u62e9\u76d8\u7b26',
    'localPanel.searchLabel': '\u641c\u7d22\u672c\u5730\u6587\u4ef6',
    'localPanel.searchPlaceholder': '\u641c\u7d22\u5f53\u524d\u6587\u4ef6\u5939\uff0c\u4f8b\u5982 *.log \u6216 report',
    'localPanel.searchSummary': ({ total, scanned, truncated }) =>
      `\u627e\u5230 ${total} \u9879 / \u5df2\u626b\u63cf ${scanned} \u9879${truncated ? ' / \u4ec5\u663e\u793a\u524d\u9762\u7ed3\u679c' : ''}`,
    'localPanel.searchEmpty': '\u672a\u627e\u5230\u5339\u914d\u7684\u672c\u5730\u6587\u4ef6\u3002',
    'localPanel.searchError': '\u672c\u5730\u641c\u7d22\u5931\u8d25',
    'localPanel.empty': '\u5f53\u524d\u76ee\u5f55\u4e3a\u7a7a\u3002',
    'localPanel.localModeEmpty': '\u5f53\u524d\u672c\u5730\u76ee\u5f55\u4e3a\u7a7a\u3002',
    'localPanel.loadError': '\u65e0\u6cd5\u8bfb\u53d6\u5de5\u4f5c\u533a\u76ee\u5f55',
    'localPanel.uploadAction': '\u4e0a\u4f20\u6587\u4ef6/\u6587\u4ef6\u5939',
    'localPanel.uploadFiles': '\u4e0a\u4f20\u6587\u4ef6',
    'localPanel.uploadFolder': '\u4e0a\u4f20\u6587\u4ef6\u5939',
    'localPanel.deleteSelected': '\u5220\u9664\u9009\u4e2d\u9879',
    'localPanel.deleteTitle': '\u5220\u9664\u5de5\u4f5c\u533a\u9879\u76ee',
    'localPanel.deleteDescription': '\u5c06\u5220\u9664\u4ee5\u4e0b\u5de5\u4f5c\u533a\u9879\u76ee\uff1a\n{labels}',
    'localPanel.deleteConfirm': '\u786e\u8ba4\u5220\u9664',
    'localPanel.uploaded': '\u5de5\u4f5c\u533a\u4e0a\u4f20\u5b8c\u6210',
    'localPanel.uploadedSummary': '\u5df2\u5c06 {total} \u4e2a\u6587\u4ef6\u4e0a\u4f20\u5230\u5de5\u4f5c\u533a\u3002',
    'localPanel.uploadFailed': '\u5de5\u4f5c\u533a\u4e0a\u4f20\u5931\u8d25',
    'localPanel.uploadCanceled': '\u5de5\u4f5c\u533a\u4e0a\u4f20\u5df2\u53d6\u6d88',
    'localPanel.deleted': '\u5de5\u4f5c\u533a\u9879\u76ee\u5df2\u5220\u9664',
    'localPanel.resetAction': '\u4e00\u952e\u6e05\u7a7a',
    'localPanel.resetTitle': '\u4e00\u952e\u6e05\u7a7a\u5f53\u524d\u7528\u6237\u6570\u636e',
    'localPanel.resetDescription': '\u8fd9\u4f1a\u5220\u9664\u5f53\u524d\u7528\u6237\u4fdd\u5b58\u7684\u670d\u52a1\u5668\u7ad9\u70b9/\u5bc6\u94a5\u4fe1\u606f\uff0c\u5173\u95ed\u5f53\u524d\u7528\u6237\u8fdc\u7aef\u4f1a\u8bdd\uff0c\u6e05\u7406\u5f53\u524d\u7528\u6237\u4efb\u52a1\u8bb0\u5f55\uff0c\u5e76\u6e05\u7a7a\u5de5\u4f5c\u533a\u4e2d\u7684\u5168\u90e8\u4e0a\u4f20\u6587\u4ef6\u3002\n\u8be5\u64cd\u4f5c\u4e0d\u53ef\u6062\u590d\u3002',
    'localPanel.resetConfirm': '\u786e\u8ba4\u4e00\u952e\u6e05\u7a7a',
    'localPanel.resetDone': '\u5f53\u524d\u7528\u6237\u6570\u636e\u5df2\u6e05\u7a7a',
    'localPanel.resetSummary': ({ sites, sessions, tasks, files, dirs }) => `\u5df2\u5220\u9664 ${sites} \u4e2a\u7ad9\u70b9\uff0c\u5173\u95ed ${sessions} \u4e2a\u4f1a\u8bdd\uff0c\u6e05\u7406 ${tasks} \u6761\u4efb\u52a1\u8bb0\u5f55\uff0c\u6e05\u7a7a\u5de5\u4f5c\u533a ${files} \u4e2a\u6587\u4ef6 / ${dirs} \u4e2a\u76ee\u5f55\u3002`,
    'localPanel.resetFailed': '\u4e00\u952e\u6e05\u7a7a\u5931\u8d25',
    'localPanel.resetBackendRestartRequired': '\u5f53\u524d\u540e\u7aef\u8fd8\u6ca1\u6709\u66b4\u9732\u4e00\u952e\u6e05\u7a7a\u63a5\u53e3\u3002\u8bf7\u91cd\u542f\u540e\u7aef\u540e\u518d\u8bd5\u3002',
    'log.title': '\u539f\u59cb\u65e5\u5fd7',
    'log.summary': ({ total }) => `Buffer ${total}`,
    'log.clear': '\u6e05\u7a7a\u65e5\u5fd7',
    'log.cleared': '\u65e5\u5fd7\u5df2\u6e05\u7a7a',
    'log.autoScroll': '\u81ea\u52a8\u6eda\u52a8',
    'log.emptyTitle': '\u8fd8\u6ca1\u6709\u65e5\u5fd7',
    'log.emptyBody': '\u7b49\u5f85\u540e\u7aef\u4e8b\u4ef6\u3001\u4efb\u52a1\u8c03\u5ea6\u6216\u8fde\u63a5\u6d3b\u52a8\u751f\u6210\u65b0\u7684\u65e5\u5fd7\u3002',
    'log.backendRestartRequired': 'The current backend does not expose the deployed log channel yet, or the log capability is not wired in.',
    'remoteWorkspace.title': '\u8fdc\u7aef\u5de5\u4f5c\u533a',
    'remoteWorkspace.description': '\u5e76\u6392\u663e\u793a\u7684\u591a\u4f1a\u8bdd\u5de5\u4f5c\u533a\u3002',
    'remoteWorkspace.emptyTitle': '\u5f53\u524d\u6ca1\u6709\u6253\u5f00\u8fdc\u7aef\u4f1a\u8bdd',
    'remoteWorkspace.emptyBody': '\u8bf7\u5728\u5de6\u4fa7\u9009\u62e9\u7ad9\u70b9\u5e76\u6253\u5f00\u4f1a\u8bdd\u3002\u8fdc\u7aef\u9762\u677f\u4f1a\u6309\u987a\u5e8f\u8ffd\u52a0\u5230\u53f3\u4fa7\u3002',
    'remotePane.deleteTitle': '\u5220\u9664\u8fdc\u7aef\u8def\u5f84',
    'remotePane.deleteDescription': '\u5c06\u5220\u9664\u4ee5\u4e0b\u8fdc\u7aef\u5bf9\u8c61\uff1a\n{labels}',
    'remotePane.deleteConfirm': '\u786e\u8ba4\u5220\u9664',
    'remotePane.deleteToast': '\u8fdc\u7aef\u5220\u9664\u8bf7\u6c42\u5df2\u63d0\u4ea4',
    'remotePane.closePane': '\u5173\u95ed\u9762\u677f',
    'remotePane.staleTitle': '\u4f1a\u8bdd\u5df2\u5931\u6548',
    'remotePane.staleBody': '\u540e\u7aef\u5df2\u91cd\u542f\uff0c\u6216\u8be5\u4f1a\u8bdd\u5df2\u4e0d\u5b58\u5728\u3002\u8bf7\u5728\u5de6\u4fa7\u91cd\u65b0\u6253\u5f00\u7ad9\u70b9\uff0c\u6216\u8005\u76f4\u63a5\u5173\u95ed\u6b64\u9762\u677f\u3002',
    'remotePane.createDirectoryPrompt': '\u8f93\u5165\u65b0\u76ee\u5f55\u540d\u79f0',
    'remotePane.createDirectoryToast': '\u8fdc\u7aef\u76ee\u5f55\u5df2\u521b\u5efa',
    'remotePane.pathPlaceholder': '\u8f93\u5165\u8fdc\u7aef\u8def\u5f84',
    'remotePane.uploadLocalSelection': '\u4e0a\u4f20\u5de5\u4f5c\u533a\u9009\u4e2d\u9879',
    'remotePane.downloadSelection': '\u4e0b\u8f7d\u5230\u5de5\u4f5c\u533a',
    'remotePane.renamePrompt': '\u8f93\u5165\u65b0\u7684\u6587\u4ef6\u6216\u76ee\u5f55\u540d\u79f0',
    'remotePane.renameToast': '\u8fdc\u7aef\u8def\u5f84\u5df2\u91cd\u547d\u540d',
    'remotePane.empty': '\u5f53\u524d\u8fdc\u7aef\u76ee\u5f55\u4e3a\u7a7a\u3002',
    'remotePane.loadError': '\u65e0\u6cd5\u8bfb\u53d6\u8fdc\u7aef\u76ee\u5f55',
    'http.sessionInvalid': 'The current login session is invalid. Please log in again.',
    'http.sessionExpired': 'The login session has expired. Please log in again.',
    'http.backendNotReadyTitle': 'Backend Not Ready',
    'http.backendNotReadyMessage': 'The service is reachable, but its dependencies are not ready or required capabilities are missing on this machine.',
    'http.requestFailed': 'Request failed',
    'http.backendStartupIncomplete': 'The backend has not finished starting yet.',
    'http.initFailed': 'Initialization failed',
    'activity.title': '\u6d3b\u52a8\u6d41',
    'activity.description': '\u5f53\u524d\u7528\u6237\u6700\u8fd1\u7684\u767b\u5f55\u3001\u5de5\u4f5c\u533a\u3001\u4f1a\u8bdd\u548c\u4efb\u52a1\u4e8b\u4ef6\u3002',
    'activity.pageDescription': '\u5f53\u524d\u5df2\u767b\u5f55\u7528\u6237\u7684\u5b9e\u65f6\u6d3b\u52a8\u6d41\u3002',
    'activity.summary': ({ total }) => `\u5171 ${total} \u6761\u4e8b\u4ef6`,
    'activity.autoScroll': '\u81ea\u52a8\u6eda\u52a8',
    'activity.emptyTitle': '\u8fd8\u6ca1\u6709\u6d3b\u52a8',
    'activity.emptyBody': '\u7b49\u5f85\u767b\u5f55\u3001\u5de5\u4f5c\u533a\u3001\u4f1a\u8bdd\u6216\u4efb\u52a1\u64cd\u4f5c\u751f\u6210\u4e8b\u4ef6\u3002',
    'activity.backendRestartRequired':
      '\u5f53\u524d\u540e\u7aef\u8fd8\u6ca1\u6709\u66b4\u9732\u6d3b\u52a8\u6d41\u80fd\u529b\uff0c\u6216\u8005\u6d3b\u52a8\u6d41\u80fd\u529b\u5c1a\u672a\u63a5\u5165\u3002',
    'activity.pollFailed': '\u6d3b\u52a8\u8f6e\u8be2\u5931\u8d25',
    'activity.channelErrorTitle': '\u6d3b\u52a8\u901a\u9053\u8fd4\u56de\u9519\u8bef',
    'activity.websocketError': '\u6d3b\u52a8 WebSocket \u8fde\u63a5\u9519\u8bef',
    'activity.category.auth': '\u8ba4\u8bc1',
    'activity.category.site': '\u7ad9\u70b9',
    'activity.category.session': '\u4f1a\u8bdd',
    'activity.category.workspace': '\u5de5\u4f5c\u533a',
    'activity.category.remote': '\u8fdc\u7aef',
    'activity.category.task': '\u4efb\u52a1',
    'activity.category.system': '\u7cfb\u7edf',
    'log.description': '\u4ec5 owner \u53ef\u89c1\u7684\u540e\u7aef\u65e5\u5fd7\u7f13\u51b2\u533a\uff0c\u7528\u4e8e\u5e95\u5c42\u8bca\u65ad\u3002',
    'log.pageDescription': '\u4ec5 owner \u53ef\u89c1\u7684\u539f\u59cb\u540e\u7aef\u65e5\u5fd7\u6d41\uff0c\u7528\u4e8e\u8c03\u8bd5\u548c\u91cd\u542f\u5206\u6790\u3002',  },
  en: {
    'app.title': 'SSHFerry',
    'language.label': 'Language',
    'language.zh': 'ZH',
    'language.en': 'EN',
    'brand.frontend': 'SSHFerry Frontend',
    'nav.workspace': 'Workspace',
    'nav.tasks': 'Tasks',
    'nav.activity': 'Activity',
    'nav.debugLogs': 'Debug Logs',
    'nav.logs': 'Logs',
    'common.add': 'Add',
    'common.edit': 'Edit',
    'common.remove': 'Remove',
    'common.check': 'Check',
    'common.refresh': 'Refresh',
    'common.cancel': 'Cancel',
    'common.clear': 'Clear',
    'common.close': 'Close',
    'common.confirm': 'Confirm',
    'common.processing': 'Processing...',
    'common.save': 'Save',
    'common.saving': 'Saving...',
    'common.parse': 'Parse',
    'common.delete': 'Delete',
    'common.rename': 'Rename',
    'common.dismiss': 'Dismiss',
    'common.selectAll': 'Select All',
    'common.id': 'ID',
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
    'common.session': 'Session',
    'common.ready': 'Ready',
    'common.loading': 'Loading',
    'common.booting': 'Booting',
    'common.ok': 'OK',
    'common.fail': 'Fail',
    'common.loadingDirectory': 'Loading directory...',
    'common.directoryLoadFailed': 'Directory load failed',
    'common.viewFailureDetails': 'View failure details',
    'common.stale': 'Stale',
    'endpoint.local': 'Local',
    'endpoint.remote': 'Remote',
    'endpoint.workspace': 'Workspace',
    'protocol.auto': 'Auto',
    'auth.password': 'Password',
    'auth.key': 'Key',
    'auth.loginRequired': 'This deployed environment requires login before entering the workspace.',
    'auth.logout': 'Log Out',
    'auth.loggedOut': 'Logged out.',
    'auth.loginFailed': 'Login failed',
    'socket.idle': 'Idle',
    'socket.connecting': 'Connecting',
    'socket.connected': 'Connected',
    'socket.reconnecting': 'Reconnecting',
    'socket.polling': 'Polling',
    'socket.error': 'Error',
    'socket.pollFailed': 'Task polling failed',
    'socket.channelErrorTitle': 'Task channel returned an error',
    'socket.websocketError': 'Task WebSocket connection error',
    'socket.logPollFailed': 'Log polling failed',
    'socket.logChannelErrorTitle': 'Log channel returned an error',
    'socket.logWebsocketError': 'Log WebSocket connection error',
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
      `${done}/${total} files / ${progress}%${current || ''}`,
    'task.progress.bytes': ({ progress, done, total }) => `${progress}% / ${done}/${total}`,
    'task.progress.percent': ({ progress }) => `${progress}%`,
    'bootstrap.title': 'Preparing SSHFerry Workspace',
    'bootstrap.error': 'Initialization failed',
    'bootstrap.retry': 'Retry Initialization',
    'bootstrap.description': 'Checking backend health, restoring the login session, and preparing sites, sessions, and the task channel.',
    'bootstrap.complete': 'Ready',
    'bootstrap.connecting': 'Connecting...',
    'workspace.waitTitle': 'Waiting for Backend Initialization',
    'workspace.waitDescription': 'Preparing login state, sites, sessions, and the task channel.',
    'workspace.toast.noUploadSelection': 'No workspace selection available for upload',
    'workspace.toast.uploadSubmitted': 'Upload tasks submitted',
    'workspace.toast.downloadSubmitted': 'Download tasks submitted',
    'workspace.toast.remoteCopySubmitted': 'Remote copy tasks submitted',
    'workspace.toast.queueSummary': ({ successCount, total }) => `${successCount}/${total} items entered backend scheduling.`,
    'workspace.toast.noDownloadTarget': 'Missing download source or workspace target directory',
    'workspace.toast.noRemoteCopySelection': 'No remote selection available for copy',
    'workspace.toast.sessionClosed': 'Remote session closed',
    'workspace.middlePanelMode': 'Middle Panel',
    'workspace.middlePanelDescription': 'Switch between the upload workspace and an open remote session.',
    'workspace.middleSession': 'Displayed Session',
    'workspace.middleRemoteEmptyTitle': 'No remote session is available here',
    'workspace.middleRemoteEmptyBody': 'Open at least one remote session from the left, or switch back to the workspace panel.',
    'workspace.secondaryRemoteEmptyTitle': 'No additional remote sessions',
    'workspace.secondaryRemoteEmptyBody': 'One remote session is already pinned in the middle panel. Open another session to show it on the right.',
    'topbar.tagline': 'Multi-session file transfer workspace',
    'topbar.backend': 'Backend',
    'topbar.activityChannel': 'Activity WS',
    'topbar.protocol': 'Protocol',
    'topbar.language': 'Language',
    'topbar.user': 'User',
    'login.title': 'Log In to SSHFerry',
    'login.description': 'Use your SSHFerry account to sign in, or create a new account to enter the deployed workspace.',
    'login.switchPrompt': 'Need an account?',
    'login.switchAction': 'Sign up',
    'login.username': 'Username',
    'login.password': 'Password',
    'auth.captcha': 'Captcha',
    'auth.captchaPlaceholder': 'Enter captcha',
    'auth.refreshCaptcha': 'Refresh',
    'login.usernamePlaceholder': 'Enter username',
    'login.passwordPlaceholder': 'Enter password',
    'login.submit': 'Log In',
    'login.submitting': 'Logging in...',
    'signup.title': 'Create Your SSHFerry Account',
    'signup.description': 'Create a new account and you will be signed into the workspace immediately.',
    'signup.username': 'Username',
    'signup.usernamePlaceholder': 'For example alice',
    'signup.displayName': 'Display Name',
    'signup.displayNamePlaceholder': 'Optional. Defaults to the username.',
    'signup.password': 'Password',
    'signup.passwordPlaceholder': 'At least 8 characters',
    'signup.confirmPassword': 'Confirm Password',
    'signup.confirmPasswordPlaceholder': 'Enter the password again',
    'signup.submit': 'Create Account',
    'signup.submitting': 'Creating account...',
    'signup.failed': 'Signup failed',
    'signup.passwordMismatch': 'The two passwords do not match.',
    'signup.switchPrompt': 'Already have an account?',
    'signup.switchAction': 'Log in',
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
    'siteSidebar.toast.sessionOpenedMessage': ({ siteName, sessionId }) => `${siteName} / ${sessionId}`,
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
    'siteSidebar.connectionLine': ({ status, name, message }) => `${status} / ${name} / ${message}`,
    'siteSidebar.loadError': 'Failed to load the site sidebar',
    'siteSidebar.secretCheckTitle': 'Runtime Credentials: Connection Check',
    'siteSidebar.secretOpenTitle': 'Runtime Credentials: Open Session',
    'siteSidebar.secretCheckSubmit': 'Start Check',
    'siteSidebar.secretOpenSubmit': 'Open Session',
    'siteSidebar.closeSession': 'Close Session',
    'siteEditor.newTitle': 'New Site',
    'siteEditor.editTitle': 'Edit Site',
    'siteEditor.description': 'Aligned with backend fields and form semantics.',
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
    'siteEditor.keyPassphrasePlaceholderSaved': 'Key passphrase already stored. Leave blank to keep it unchanged.',
    'siteEditor.keyPassphrasePlaceholderNew': 'Enter a key passphrase if needed',
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
      `Total ${total} / Running ${running} / Pending ${pending} / Failed ${failed} / Done ${done}`,
    'taskCenter.clearFinished': 'Clear Finished',
    'taskCenter.toast.actionSubmitted': ({ action }) => `${action} requests submitted`,
    'taskCenter.toast.actionAccepted': ({ successCount, total }) => `${successCount}/${total} requests accepted.`,
    'taskCenter.toast.clearedFinished': 'Finished tasks cleared',
    'taskCenter.empty': 'No tasks right now.',
    'localPanel.title': 'Upload Workspace',
    'localPanel.description': 'Manage the deployed user workspace, upload files and folders, and receive remote downloads.',
    'localPanel.localModeTitle': 'Local Files',
    'localPanel.localModeDescription': 'Browse files on this machine directly without uploading them into an intermediate workspace first.',
    'localPanel.summary': ({ files, dirs, size }) => `${files} files / ${dirs} directories / ${size}`,
    'localPanel.pathPlaceholder': 'Enter a workspace path, for example /releases',
    'localPanel.localModePathPlaceholder': 'Enter a local path, for example E:\\Projects',
    'localPanel.localModeDrivePlaceholder': 'Select a drive',
    'localPanel.searchLabel': 'Search local files',
    'localPanel.searchPlaceholder': 'Search this folder, for example *.log or report',
    'localPanel.searchSummary': ({ total, scanned, truncated }) =>
      `Found ${total} / scanned ${scanned}${truncated ? ' / showing first matches' : ''}`,
    'localPanel.searchEmpty': 'No matching local files found.',
    'localPanel.searchError': 'Local search failed',
    'localPanel.empty': 'This directory is empty.',
    'localPanel.localModeEmpty': 'This local directory is empty.',
    'localPanel.loadError': 'Unable to read the workspace directory',
    'localPanel.uploadAction': 'Upload File/Folder',
    'localPanel.uploadFiles': 'Upload Files',
    'localPanel.uploadFolder': 'Upload Folder',
    'localPanel.deleteSelected': 'Delete Selected',
    'localPanel.deleteTitle': 'Delete Workspace Items',
    'localPanel.deleteDescription': 'The following workspace items will be deleted:\n{labels}',
    'localPanel.deleteConfirm': 'Confirm Delete',
    'localPanel.uploaded': 'Workspace upload completed',
    'localPanel.uploadedSummary': '{total} files uploaded into the workspace.',
    'localPanel.uploadFailed': 'Workspace upload failed',
    'localPanel.uploadCanceled': 'Workspace upload canceled',
    'localPanel.deleted': 'Workspace items deleted',
    'localPanel.resetAction': 'Clear My Data',
    'localPanel.resetTitle': 'Clear Current User Data',
    'localPanel.resetDescription': "This removes the current user's saved site and key information, closes the current user's remote sessions, clears the current user's task history, and deletes every uploaded file in the workspace.\nThis action cannot be undone.",
    'localPanel.resetConfirm': 'Confirm Clear',
    'localPanel.resetDone': 'Current user data cleared',
    'localPanel.resetSummary': ({ sites, sessions, tasks, files, dirs }) => `Removed ${sites} sites, closed ${sessions} sessions, cleared ${tasks} task records, and emptied ${files} files / ${dirs} directories from the workspace.`,
    'localPanel.resetFailed': 'Clear user data failed',
    'localPanel.resetBackendRestartRequired': 'The current backend does not expose the clear-user-data endpoint yet. Restart the backend and try again.',
    'log.title': 'Raw Logs',
    'log.summary': ({ total }) => `Buffer ${total}`,
    'log.clear': 'Clear Logs',
    'log.cleared': 'Logs cleared',
    'log.autoScroll': 'Auto Scroll',
    'log.emptyTitle': 'No logs yet',
    'log.emptyBody': 'Wait for backend events, task scheduling, or connection activity to generate new log lines.',
    'log.backendRestartRequired': 'The current backend does not expose the deployed log channel yet, or the log capability is not wired in.',
    'remoteWorkspace.title': 'Remote Workspace',
    'remoteWorkspace.description': 'Side-by-side multi-session workspace.',
    'remoteWorkspace.emptyTitle': 'No remote sessions are open',
    'remoteWorkspace.emptyBody': 'Select a site on the left and open a session. Remote panes will be appended on the right in order.',
    'remotePane.deleteTitle': 'Delete Remote Path',
    'remotePane.deleteDescription': 'The following remote objects will be deleted:\n{labels}',
    'remotePane.deleteConfirm': 'Confirm Delete',
    'remotePane.deleteToast': 'Remote delete request submitted',
    'remotePane.closePane': 'Close Pane',
    'remotePane.staleTitle': 'Session Expired',
    'remotePane.staleBody': 'The backend restarted or the session no longer exists. Reopen the site from the left, or close this pane directly.',
    'remotePane.createDirectoryPrompt': 'Enter a new directory name',
    'remotePane.createDirectoryToast': 'Remote directory created',
    'remotePane.pathPlaceholder': 'Enter remote path',
    'remotePane.uploadLocalSelection': 'Upload Workspace Selection',
    'remotePane.downloadSelection': 'Download to Workspace',
    'remotePane.renamePrompt': 'Enter a new file or directory name',
    'remotePane.renameToast': 'Remote path renamed',
    'remotePane.empty': 'This remote directory is empty.',
    'remotePane.loadError': 'Unable to read the remote directory',
    'http.sessionInvalid': 'The current login session is invalid. Please log in again.',
    'http.sessionExpired': 'The login session has expired. Please log in again.',
    'http.backendNotReadyTitle': 'Backend Not Ready',
    'http.backendNotReadyMessage': 'The service is reachable, but its dependencies are not ready or required capabilities are missing on this machine.',
    'http.requestFailed': 'Request failed',
    'http.backendStartupIncomplete': 'The backend has not finished starting yet.',
    'http.initFailed': 'Initialization failed',
    'activity.title': 'Activity Feed',
    'activity.description': 'Recent auth, workspace, session, and task events for the current user.',
    'activity.pageDescription': 'Live activity stream for the current authenticated user.',
    'activity.summary': ({ total }) => `Events ${total}`,
    'activity.autoScroll': 'Auto Scroll',
    'activity.emptyTitle': 'No activity yet',
    'activity.emptyBody': 'Wait for auth, workspace, session, or task operations to generate new events.',
    'activity.backendRestartRequired':
      'The current backend does not expose the deployed activity feed yet, or the activity capability is not wired in.',
    'activity.pollFailed': 'Activity polling failed',
    'activity.channelErrorTitle': 'Activity channel returned an error',
    'activity.websocketError': 'Activity WebSocket connection error',
    'activity.category.auth': 'Auth',
    'activity.category.site': 'Site',
    'activity.category.session': 'Session',
    'activity.category.workspace': 'Workspace',
    'activity.category.remote': 'Remote',
    'activity.category.task': 'Task',
    'activity.category.system': 'System',
    'log.description': 'Owner-only backend log buffer for low-level diagnosis.',
    'log.pageDescription': 'Owner-only raw backend log stream for debugging and restart analysis.',  },
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
  workspace: 'endpoint.workspace',
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
    const current = task.current_file ? ` / ${task.current_file}` : '';
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

