export const ALLOWED_INVOKE_CHANNELS = new Set([
  'get-backend-base-url',
  'open-file-dialog',
  'open-folder-dialog',
  'read-directory',
  'read-file',
  'write-file',
  'file-exists',
  'write-multiple-files',
  'session-get',
  'session-set',
  'session-clear',
])

export function assertAllowedInvokeChannel(channel: string): void {
  if (!ALLOWED_INVOKE_CHANNELS.has(channel)) {
    throw new Error(`IPC channel izinsiz: ${channel}`)
  }
}
