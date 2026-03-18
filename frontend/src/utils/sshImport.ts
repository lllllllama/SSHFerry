export interface ParsedSshCommand {
  name?: string;
  host: string;
  port?: number;
  username?: string;
}

const SSH_COMMAND_PATTERN = /^ssh\s+(?:-p\s+(\d+)\s+)?(?:(\w+)@)?([^\s]+)\s*$/i;

export function parseBasicSshCommand(command: string): ParsedSshCommand | null {
  const trimmed = command.trim();
  const match = trimmed.match(SSH_COMMAND_PATTERN);
  if (!match) {
    return null;
  }

  const [, portValue, username, host] = match;
  return {
    host,
    port: portValue ? Number(portValue) : undefined,
    username: username || undefined,
    name: host.split('.')[0] || host,
  };
}
