export type AuthMethod = 'password' | 'key';
export type TransferProtocol = 'sftp' | 'scp';
export type TaskEngine = 'auto' | 'sftp' | 'scp' | 'parallel' | 'dualpath';
export type ProtocolOverride = 'auto' | 'sftp' | 'scp';
export type TaskStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'done'
  | 'failed'
  | 'canceled'
  | 'skipped';

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
  ready: boolean;
  scheduler_running: boolean;
  session_count: number;
  startup_error: string | null;
  auth_required: boolean;
  auth_header_name: string | null;
  auth_mode: string;
  runtime_mode: 'local-dev' | 'deployed-web';
  access_cookie_name: string;
  refresh_cookie_name: string;
  workspace_root: string;
  features?: string[];
}

export interface AuthSessionResponse {
  token: string;
  header_name: string;
  token_type: string;
}

export interface AuthUserResponse {
  id: string;
  username: string;
  display_name: string;
  role: 'owner' | 'operator' | 'viewer' | string;
  auth_scheme: string;
  session_id: string;
  session_expires_at: number;
}

export interface AuthCaptchaResponse {
  captcha_id: string;
  image_svg: string;
  expires_at: number;
}

export interface AuthLoginRequest {
  username: string;
  password: string;
  captcha_id: string;
  captcha_code: string;
}

export interface AuthSignupRequest {
  username: string;
  password: string;
  display_name?: string | null;
  captcha_id: string;
  captcha_code: string;
}

export interface SiteUpsertRequest {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: AuthMethod;
  remote_root: string;
  password: string | null;
  key_path: string | null;
  key_passphrase: string | null;
  remember_password: boolean;
  proxy_jump: string | null;
  ssh_config_path: string | null;
  ssh_options: string[];
  default_transfer_protocol: TransferProtocol;
}

export interface SiteResponse {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: AuthMethod;
  remote_root: string;
  key_path: string | null;
  remember_password: boolean;
  proxy_jump: string | null;
  ssh_config_path: string | null;
  ssh_options: string[];
  default_transfer_protocol: TransferProtocol;
  has_password: boolean;
  has_key_passphrase: boolean;
}

export interface SiteBulkDeleteResponse {
  deleted: string[];
  closed_sessions: number;
}

export interface ConnectionCheckRequest {
  site_name: string;
  password?: string | null;
  key_passphrase?: string | null;
}

export interface ConnectionCheckResult {
  name: string;
  passed: boolean;
  message: string;
}

export interface ConnectionCheckResponse {
  site_name: string;
  all_passed: boolean;
  results: ConnectionCheckResult[];
}

export interface SessionOpenRequest {
  site_name: string;
  password?: string | null;
  key_passphrase?: string | null;
}

export interface SessionCloseRequest {
  session_id: string;
}

export interface SessionResponse {
  session_id: string;
  site_name: string;
  host: string;
  port: number;
  username: string;
  auth_method: AuthMethod;
  remote_root: string;
  has_password: boolean;
}

export interface LocalDrive {
  path: string;
  label: string;
}

export interface LocalEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  exists: boolean;
}

export interface LocalListResponse {
  current_path: string;
  parent_path: string | null;
  items: LocalEntry[];
  total: number;
}

export interface LocalSearchResponse {
  current_path: string;
  query: string;
  items: LocalEntry[];
  total: number;
  scanned: number;
  truncated: boolean;
}

export interface LocalStatResponse {
  entry: LocalEntry;
}

export interface WorkspaceEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  exists: boolean;
}

export interface WorkspaceListResponse {
  current_path: string;
  parent_path: string | null;
  items: WorkspaceEntry[];
  total: number;
}

export interface WorkspaceStatResponse {
  entry: WorkspaceEntry;
  file_count: number;
  dir_count: number;
  total_size: number;
}

export interface WorkspaceUploadResponse {
  target_path: string;
  uploaded_paths: string[];
  total: number;
}

export interface WorkspaceDeleteResponse {
  deleted_paths: string[];
  total: number;
}

export interface WorkspaceResetResponse {
  deleted_site_count: number;
  closed_session_count: number;
  canceled_task_count: number;
  cleared_task_count: number;
  cleared_activity_count: number;
  workspace_file_count: number;
  workspace_dir_count: number;
  workspace_total_size: number;
}

export interface RemoteEntry {
  name: string;
  path: string;
  is_dir: boolean;
  size: number;
  mtime: number;
  mode: number | null;
}

export interface RemoteListResponse {
  session_id: string;
  current_path: string;
  parent_path: string | null;
  items: RemoteEntry[];
  total: number;
}

export interface RemoteBulkDeleteResponse {
  deleted_paths: string[];
  total: number;
}

export interface TaskItem {
  task_id: string;
  kind: string;
  engine: string;
  status: TaskStatus;
  src: string;
  dst: string;
  src_endpoint_type: string;
  dst_endpoint_type: string;
  src_session_id: string | null;
  dst_session_id: string | null;
  src_display_name: string | null;
  dst_display_name: string | null;
  src_label: string;
  dst_label: string;
  bytes_total: number;
  bytes_done: number;
  progress_percent: number;
  speed: number;
  retries: number;
  error_code: string | null;
  error_message: string | null;
  start_time: number | null;
  end_time: number | null;
  interrupted: boolean;
  paused: boolean;
  skipped: boolean;
  subtask_count: number;
  subtask_done: number;
  current_file: string;
  is_finished: boolean;
}

export interface TaskActionResponse {
  task_id: string;
  action: string;
  status: string;
}

export interface TaskSnapshotMessage {
  type: 'task_snapshot';
  items: TaskItem[];
  total: number;
}

export interface TaskSocketErrorMessage {
  type: 'error';
  detail: string;
}

export type TaskSocketMessage = TaskSnapshotMessage | TaskSocketErrorMessage;

export interface LogItem {
  sequence: number;
  timestamp: number;
  level: string;
  logger: string;
  message: string;
  rendered: string;
}

export interface LogListResponse {
  items: LogItem[];
  total: number;
  sequence: number;
}

export interface LogSnapshotMessage {
  type: 'log_snapshot';
  items: LogItem[];
  total: number;
  sequence: number;
}

export type LogSocketMessage = LogSnapshotMessage | TaskSocketErrorMessage;

export interface ActivityItem {
  sequence: number;
  timestamp: number;
  level: string;
  category: string;
  action: string;
  title: string;
  message: string;
}

export interface ActivityListResponse {
  items: ActivityItem[];
  total: number;
  sequence: number;
}

export interface ActivitySnapshotMessage {
  type: 'activity_snapshot';
  items: ActivityItem[];
  total: number;
  sequence: number;
}

export type ActivitySocketMessage = ActivitySnapshotMessage | TaskSocketErrorMessage;

export interface ApiListResponse<T> {
  items: T[];
  total: number;
}

export interface TransferDragPayload {
  kind: 'local' | 'remote';
  sessionId?: string;
  paths: string[];
}
