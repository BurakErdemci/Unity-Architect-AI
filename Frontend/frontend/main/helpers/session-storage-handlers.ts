import fs from 'fs'
import path from 'path'

export interface SafeStorageAdapter {
  isEncryptionAvailable(): boolean
  encryptString(plainText: string): Buffer
  decryptString(encrypted: Buffer): string
}

export interface SessionHandlerDeps {
  userDataPath: string
  safeStorage: SafeStorageAdapter
}

function sessionFilePath(userDataPath: string): string {
  return path.join(userDataPath, 'session.enc')
}

export async function sessionGet(deps: SessionHandlerDeps): Promise<string | null> {
  try {
    const file = sessionFilePath(deps.userDataPath)
    if (!fs.existsSync(file)) return null
    if (!deps.safeStorage.isEncryptionAvailable()) return null
    const encrypted = fs.readFileSync(file)
    return deps.safeStorage.decryptString(encrypted)
  } catch {
    return null
  }
}

export async function sessionSet(deps: SessionHandlerDeps, token: string): Promise<boolean> {
  try {
    if (!deps.safeStorage.isEncryptionAvailable()) return false
    const encrypted = deps.safeStorage.encryptString(token)
    fs.writeFileSync(sessionFilePath(deps.userDataPath), encrypted)
    return true
  } catch {
    return false
  }
}

export async function sessionClear(deps: SessionHandlerDeps): Promise<boolean> {
  try {
    const file = sessionFilePath(deps.userDataPath)
    if (fs.existsSync(file)) fs.unlinkSync(file)
    return true
  } catch {
    return false
  }
}
