import fs from 'fs'
import path from 'path'

/**
 * Symlink-safe path çözücü.
 * Yol mevcutsa fs.realpathSync ile gerçek yolu çözer.
 * Yol henüz mevcut değilse, en yakın mevcut parent dizini realpath ile çözüp
 * kalan path segmentlerini onun üzerine ekler. Böylece symlink klasör altına
 * yeni dosya yazma girişimleri de doğru şekilde yakalanır.
 */
function safeResolve(filePath: string): string {
  try {
    const absolutePath = path.resolve(filePath)
    if (fs.existsSync(absolutePath)) {
      return fs.realpathSync(absolutePath)
    }

    let currentPath = absolutePath
    const missingSegments: string[] = []

    while (!fs.existsSync(currentPath)) {
      const parentPath = path.dirname(currentPath)
      if (parentPath === currentPath) {
        return absolutePath
      }
      missingSegments.unshift(path.basename(currentPath))
      currentPath = parentPath
    }

    const resolvedExistingPath = fs.realpathSync(currentPath)
    return path.join(resolvedExistingPath, ...missingSegments)
  } catch {
    // realpathSync başarısız olursa fallback
  }
  return path.resolve(filePath)
}

/**
 * Yazma/okuma izni sadece workspace içindeki Assets/Scripts/*.cs dosyalarına verilir.
 * Path traversal, symlink ve dışarı çıkış girişimlerini engeller.
 */
export function isAllowedUnityScriptPath(filePath: string, workspacePath: string): boolean {
  try {
    const resolvedFile = safeResolve(filePath)
    const resolvedWorkspace = safeResolve(workspacePath)
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
 * Symlink çözümü dahildir.
 */
export function isAllowedWorkspacePath(targetPath: string, workspacePath: string): boolean {
  try {
    if (!targetPath || !workspacePath) return false

    const resolvedTarget = safeResolve(targetPath)
    const resolvedWorkspace = safeResolve(workspacePath)
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
 * Symlink çözümü dahildir.
 */
export function isAllowedWorkspaceReadFile(filePath: string, workspacePath: string): boolean {
  try {
    if (!isAllowedWorkspacePath(filePath, workspacePath)) {
      return false
    }

    return path.extname(safeResolve(filePath)).toLowerCase() === '.cs'
  } catch {
    return false
  }
}
