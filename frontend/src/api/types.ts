export type AuthMethod = 'password' | 'key';
export type TransferProtocol = 'sftp' | 'scp';
export type TaskEngine = 'auto' | 'sftp' | 'scp' | 'parallel';
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
  auth_header_name: string;
}

export interface AuthSessionResponse {
  token: string;
  header_name: string;
  token_type: string;
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

export interface ApiListResponse<T> {
  items: T[];
  total: number;
}

export interface TransferDragPayload {
  kind: 'local' | 'remote';
  sessionId?: string;
  paths: string[];
}
