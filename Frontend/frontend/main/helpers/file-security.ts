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
 * Uygulama içinden okunup yazılabilen metin dosyası uzantıları.
 * Dosya ağacı (read-directory) ile aynı liste — md/txt gibi dokümanlar da
 * (örn. CLAUDE.md, README.md) editörde açılıp düzenlenebilsin diye.
 * Çalıştırılabilir/binary türler bilerek dışarıda.
 */
export const TEXT_FILE_EXTENSIONS = [
  '.cs', '.shader', '.json', '.txt', '.md', '.xml', '.yaml', '.yml',
  '.compute', '.asmdef', '.cginc', '.hlsl', '.uss', '.uxml',
]

/**
 * Yazma/okuma izni sadece workspace içindeki Assets/Scripts/*.cs dosyalarına verilir.
 * Path traversal, symlink ve dışarı çıkış girişimlerini engeller.
 */
export function isAllowedUnityScriptPath(filePath: string, workspacePath: string): boolean {
  try {
    if (!filePath || !workspacePath) return false

    // Eğer yol absolute değilse, önce workspace ile birleştirip öyle kontrol etmeliyiz
    const absoluteFilePath = path.isAbsolute(filePath) ? filePath : path.resolve(workspacePath, filePath)

    const resolvedFile = safeResolve(absoluteFilePath)
    const resolvedWorkspace = safeResolve(workspacePath)
    const relativePath = path.relative(resolvedWorkspace, resolvedFile)

    // Workspace dışına çıkış kontrolü
    if (!relativePath || relativePath.startsWith('..') || path.isAbsolute(relativePath)) {
      return false
    }

    const parts = relativePath.split(path.sep).filter(Boolean)
    if (parts.length < 3 || parts[0] !== 'Assets' || parts[1] !== 'Scripts') {
      return false
    }

    // Sadece Assets/Scripts altındaki .cs dosyalarına yazma izni ver
    return path.extname(resolvedFile).toLowerCase() === '.cs'
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
 * Dosya okuma izni workspace içindeki metin dosyaları (TEXT_FILE_EXTENSIONS) için verilir
 * — dosya ağacının listelediği her tür (md, json, shader…) editörde de açılabilir.
 * Symlink çözümü dahildir.
 */
export function isAllowedWorkspaceReadFile(filePath: string, workspacePath: string): boolean {
  try {
    if (!isAllowedWorkspacePath(filePath, workspacePath)) {
      return false
    }

    return TEXT_FILE_EXTENSIONS.includes(path.extname(safeResolve(filePath)).toLowerCase())
  } catch {
    return false
  }
}

/**
 * Dosya yazma izni: workspace içi + metin beyaz listesi.
 * - .cs için eski kural KORUNUR (yalnızca Assets/Scripts altı — AI kod üretimi oraya akar).
 * - Diğer metin türleri (md, txt, json, shader…) workspace içinde her yere yazılabilir
 *   (örn. kök dizinde CLAUDE.md oluşturma). Path traversal/symlink koruması aynen.
 */
export function isAllowedWorkspaceWriteFile(filePath: string, workspacePath: string): boolean {
  try {
    if (!filePath || !workspacePath) return false

    const absoluteFilePath = path.isAbsolute(filePath) ? filePath : path.resolve(workspacePath, filePath)
    const ext = path.extname(safeResolve(absoluteFilePath)).toLowerCase()

    if (ext === '.cs') {
      return isAllowedUnityScriptPath(filePath, workspacePath)
    }
    if (!TEXT_FILE_EXTENSIONS.includes(ext)) {
      return false
    }
    return isAllowedWorkspacePath(absoluteFilePath, workspacePath)
  } catch {
    return false
  }
}
