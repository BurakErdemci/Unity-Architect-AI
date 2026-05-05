"""
Unity Proje Dosya Araçları — Agentic AI'ın projede dosya okuma, yazma ve listeleme yapabilmesi için.
"""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Güvenlik: Sadece workspace içinde çalış
def _validate_path(file_path: str, workspace_path: str) -> str:
    """Dosya yolunun workspace içinde olduğunu doğrular."""
    resolved = Path(file_path).resolve()
    workspace = Path(workspace_path).resolve()
    if not str(resolved).startswith(str(workspace)):
        raise PermissionError(f"Güvenlik: {file_path} workspace dışında.")
    return str(resolved)


def read_file(file_path: str, workspace_path: str) -> dict:
    """
    Belirtilen dosyayı okur ve içeriğini döndürür.
    Uzun dosyalar için ilk 500 satırı döndürür.
    """
    try:
        abs_path = _validate_path(file_path, workspace_path)
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"Dosya bulunamadı: {file_path}"}

        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        # Çok büyük dosyalarda ilk 500 satır
        if total_lines > 500:
            content = "".join(lines[:500])
            truncated = True
        else:
            content = "".join(lines)
            truncated = False

        return {
            "success": True,
            "content": content,
            "total_lines": total_lines,
            "truncated": truncated,
            "path": file_path,
        }
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Dosya okuma hatası: {str(e)}"}


def write_file(file_path: str, content: str, workspace_path: str) -> dict:
    """Belirtilen dosyaya içerik yazar. Klasör yoksa oluşturur."""
    try:
        abs_path = _validate_path(file_path, workspace_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"success": True, "path": abs_path, "bytes_written": len(content)}
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Dosya yazma hatası: {str(e)}"}


def list_directory(dir_path: str, workspace_path: str, extensions: list = None) -> dict:
    """
    Klasör içeriğini listeler. Opsiyonel olarak uzantıya göre filtreler.
    extensions örneği: [".cs", ".shader"]
    """
    try:
        abs_path = _validate_path(dir_path, workspace_path)
        if not os.path.isdir(abs_path):
            return {"success": False, "error": f"Klasör bulunamadı: {dir_path}"}

        items = []
        for entry in sorted(os.listdir(abs_path)):
            full = os.path.join(abs_path, entry)
            is_dir = os.path.isdir(full)

            if extensions and not is_dir:
                if not any(entry.endswith(ext) for ext in extensions):
                    continue

            item = {
                "name": entry,
                "is_directory": is_dir,
                "path": os.path.join(dir_path, entry),
            }
            if not is_dir:
                item["size_bytes"] = os.path.getsize(full)
            else:
                # Alt dosya sayısını hesapla
                try:
                    item["child_count"] = len(os.listdir(full))
                except PermissionError:
                    item["child_count"] = -1

            items.append(item)

        return {"success": True, "path": dir_path, "items": items, "count": len(items)}
    except PermissionError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Listeleme hatası: {str(e)}"}


def delete_file(file_path: str, workspace_path: str) -> dict:
    """
    Unity projesindeki bir dosyayı siler. 
    GÜVENLİK: Bu işlem kullanıcı onayı gerektirir. 
    Ajan bu komutu çağırdığında, kullanıcı arayüzünde bir onay paneli belirir.
    """
    try:
        abs_path = _validate_path(file_path, workspace_path)
        # Dosya var mı kontrol et
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"Dosya bulunamadı: {file_path}"}
        
        # Gerçek silme işlemi Electron tarafında yapılacağı için 
        # burada sadece ajana bilgi veriyoruz.
        return {
            "success": True, 
            "summary": f"'{file_path}' dosyası için silme isteği kullanıcıya iletildi. Kullanıcı onayladığında dosya silinecektir. Lütfen kullanıcıdan onay almasını bekle.",
            "path": file_path
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_command(command: str, workspace_path: str) -> dict:
    """
    Terminalde bir sistem komutu çalıştırır (örn: npm install, git status, unity build vb.).
    GÜVENLİK: Bu işlem kullanıcı onayı gerektirir.
    Komut çalıştırılmadan önce kullanıcı arayüzünde onay paneli belirir.
    """
    try:
        # Güvenlik ve bilgi amaçlı ajana dönüş yapıyoruz.
        # Gerçek çalıştırma işlemi frontend onayından sonra Terminal üzerinden yapılacak.
        return {
            "success": True,
            "summary": f"'{command}' komutu onay için kullanıcıya iletildi. Lütfen kullanıcının terminal üzerinden onay vermesini bekle.",
            "command": command
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
