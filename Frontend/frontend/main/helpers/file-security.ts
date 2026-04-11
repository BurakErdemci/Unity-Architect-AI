import path from 'path'

/**
 * Yazma/okuma izni sadece workspace içindeki Assets/Scripts/*.cs dosyalarına verilir.
 * Path traversal ve dışarı çıkış girişimlerini engeller.
 */
export function isAllowedUnityScriptPath(filePath: string, workspacePath: string): boolean {
  try {
    const resolvedFile = path.resolve(filePath)
    const resolvedWorkspace = path.resolve(workspacePath)
    const relativePath = path.relative(resolvedWorkspace, resolvedFile)

    if (!relativePath || relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
      return false
    }

    const parts = relativePath.split(path.sep)
    if (parts.length < 3) return false
    if (parts[0] !== 'Assets' || parts[1] !== 'Scripts') return false
    if (path.extname(resolvedFile).toLowerCase() !== '.cs') return false

    return true
  } catch {
    return false
  }
}

/**
 * Workspace dosya ağacını gezerken yalnızca seçili workspace içindeki yol okunabilir.
 */
export function isAllowedWorkspacePath(targetPath: string, workspacePath: string): boolean {
  try {
    if (!targetPath || !workspacePath) return false

    const resolvedTarget = path.resolve(targetPath)
    const resolvedWorkspace = path.resolve(workspacePath)
    const relativePath = path.relative(resolvedWorkspace, resolvedTarget)

    if (!relativePath) {
      return true
    }

    return !relativePath.startsWith('..') && !path.isAbsolute(relativePath)
  } catch {
    return false
  }
}

/**
 * Dosya okuma izni sadece workspace içindeki .cs dosyaları için verilir.
 */
export function isAllowedWorkspaceReadFile(filePath: string, workspacePath: string): boolean {
  try {
    if (!isAllowedWorkspacePath(filePath, workspacePath)) {
      return false
    }

    return path.extname(path.resolve(filePath)).toLowerCase() === '.cs'
  } catch {
    return false
  }
}
