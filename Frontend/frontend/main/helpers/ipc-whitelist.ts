export const ALLOWED_INVOKE_CHANNELS = new Set([
  'get-backend-base-url',
  'open-file-dialog',
  'open-folder-dialog',
  'read-directory',
  'read-file',
  'write-file',
  'file-exists',
  'write-multiple-files',
  'create-file',
  'create-folder',
  'rename-entry',
  'delete-entry',
  'move-entry',
  'app-token-get',
  'save-file-dialog',
  'export-text-file',
  'import-text-file',
  'delete-file',
  'terminal-spawn',
  'terminal-write',
  'terminal-resize',
])

export function assertAllowedInvokeChannel(channel: string): void {
  if (!ALLOWED_INVOKE_CHANNELS.has(channel)) {
    throw new Error(`IPC channel izinsiz: ${channel}`)
  }
}
