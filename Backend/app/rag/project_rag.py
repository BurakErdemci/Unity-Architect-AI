import os
import re
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ProjectRAG:
    """
    Unity Proje RAG (Retrieval-Augmented Generation) Motoru.
    Projeyi tarar, kodları anlamlı parçalara böler ve arama yapılmasını sağlar.
    """
    
    def __init__(self, workspace_path: Optional[str] = None):
        self.workspace_path = workspace_path
        self.documents = []  # { 'path': str, 'content': str, 'metadata': dict }
        self.chunks = []     # { 'doc_id': int, 'text': str, 'range': tuple }
        
    def scan_project(self):
        """Proje klasöründeki tüm .cs dosyalarını tarar."""
        if not self.workspace_path or not os.path.exists(self.workspace_path):
            logger.error(f"[RAG] Geçersiz workspace yolu: {self.workspace_path}")
            return
        
        logger.info(f"[RAG] Proje taranıyor: {self.workspace_path}")
        self.documents = []
        
        for root, dirs, files in os.walk(self.workspace_path):
            # Unity özel klasörlerini atla (Library, Temp, Obj, vb.)
            if any(skip in root for skip in ["Library", "Temp", "obj", ".git", "Packages"]):
                continue
                
            for file in files:
                if file.endswith(".cs"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            self.documents.append({
                                "path": file_path,
                                "name": file,
                                "content": content
                            })
                    except Exception as e:
                        logger.error(f"[RAG] Dosya okuma hatası ({file}): {e}")
        
        logger.info(f"[RAG] {len(self.documents)} dosya tarandı. Chunking başlatılıyor...")
        self._chunk_files()

    def _chunk_files(self):
        """Dosyaları anlamlı parçalara böler (Class/Method bazlı basit bölme)."""
        self.chunks = []
        for doc_id, doc in enumerate(self.documents):
            content = doc["content"]
            # Şimdilik basitçe 1000 karakterlik parçalara bölüyoruz
            # İleride bunu AST veya Regex ile class/method bazlı yapabiliriz
            lines = content.split('\n')
            current_chunk = []
            current_size = 0
            
            for line_num, line in enumerate(lines):
                current_chunk.append(line)
                current_size += len(line)
                
                if current_size > 800: # Yaklaşık 800 karakter/chunk
                    self.chunks.append({
                        "doc_id": doc_id,
                        "text": "\n".join(current_chunk),
                        "start_line": line_num - len(current_chunk) + 1,
                        "end_line": line_num + 1,
                        "file_name": doc["name"],
                        "file_path": doc["path"]
                    })
                    current_chunk = []
                    current_size = 0
            
            # Kalan parça
            if current_chunk:
                self.chunks.append({
                    "doc_id": doc_id,
                    "text": "\n".join(current_chunk),
                    "start_line": line_num - len(current_chunk) + 1,
                    "end_line": line_num + 1,
                    "file_name": doc["name"],
                    "file_path": doc["path"]
                })

    def _extract_architecture(self, content: str) -> Dict:
        """Bir C# dosyasından class, method ve kalıtım bilgilerini çıkarır."""
        architecture = {
            "classes": [],
            "methods": [],
            "inheritance": []
        }
        
        # Sınıf isimlerini ve kalıtımları bul (Örn: public class Player : MonoBehaviour)
        class_matches = re.finditer(r"(?:public|private|protected|internal|static)?\s+class\s+(\w+)(?:\s*:\s*([\w,\s]+))?", content)
        for match in class_matches:
            class_name = match.group(1)
            base_classes = match.group(2).strip().split(',') if match.group(2) else []
            architecture["classes"].append(class_name)
            if base_classes:
                architecture["inheritance"].append({class_name: [b.strip() for b in base_classes]})
                
        # Public metodları bul (Basit bir regex ile)
        method_matches = re.finditer(r"(?:public|protected)\s+(?:virtual|override|static|async)?\s*[\w<>\[\]]+\s+(\w+)\s*\(", content)
        for match in method_matches:
            architecture["methods"].append(match.group(1))
            
        return architecture

    def generate_project_report(self) -> str:
        """Tüm projenin teknik özetini çıkarır (AI'nın 'hafıza' dosyası için girdi)."""
        report = ["# Proje Teknik Haritası\n"]
        
        for doc in self.documents:
            arch = self._extract_architecture(doc["content"])
            if arch["classes"]:
                report.append(f"## Dosya: {doc['name']}")
                report.append(f"- **Sınıflar:** {', '.join(arch['classes'])}")
                if arch["inheritance"]:
                    for inh in arch["inheritance"]:
                        for k, v in inh.items():
                            report.append(f"  - *Kalıtım:* {k} -> {', '.join(v)}")
                if arch["methods"]:
                    # Sadece ilk 10 metodu alalım (çok kalabalık olmasın)
                    methods = list(set(arch["methods"]))[:10]
                    report.append(f"- **Önemli Metodlar:** {', '.join(methods)}")
                report.append("") # Boşluk
                
        return "\n".join(report)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Query ile en alakalı kod parçalarını bulur.
        Şimdilik 'Keyword' tabanlı basit arama yapıyoruz. 
        Vektör store entegrasyonu buraya gelecek.
        """
        query_terms = query.lower().split()
        results = []
        
        for chunk in self.chunks:
            score = 0
            text_lower = chunk["text"].lower()
            for term in query_terms:
                if term in text_lower:
                    score += 1
            
            if score > 0:
                results.append((score, chunk))
        
        # Skora göre sırala ve top_k dön
        results.sort(key=lambda x: x[0], reverse=True)
        return [r[1] for r in results[:top_k]]

# Test kullanımı
if __name__ == "__main__":
    rag = ProjectRAG("/Users/burakemreerdemci/Documents/UnityAideneme") # Örnek yol
    rag.scan_project()
    print(f"Toplam chunk: {len(rag.chunks)}")
    matches = rag.search("Movement")
    for m in matches:
        print(f"--- {m['file_name']} (Satır {m['start_line']}-{m['end_line']}) ---")
        print(m['text'][:100] + "...")
