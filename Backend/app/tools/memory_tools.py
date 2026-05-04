import logging
from rag.memory_manager import memory_manager

logger = logging.getLogger(__name__)

def save_to_memory(content: str, conversation_id: str):
    """
    AI'nın bu sohbet için önemli bilgileri hafızasına kaydetmesini sağlar.
    Kullanım: Önemli mimari kararlar, dosya ilişkileri veya kullanıcı talimatlarını saklamak için.
    """
    try:
        # Mevcut hafızayı alıp üstüne ekleme yapabiliriz veya tamamen güncelleyebiliriz
        # Şimdilik temiz bir güncel hafıza mantığıyla gidelim
        memory_manager.save_memory(conversation_id, content)
        return {"success": True, "message": "Bilgiler başarıyla hafızaya kaydedildi."}
    except Exception as e:
        return {"success": False, "error": str(e)}

def recall_memory(conversation_id: str):
    """
    AI'nın bu sohbet için daha önce kaydettiği bilgileri okumasını sağlar.
    """
    try:
        content = memory_manager.load_memory(conversation_id)
        if content:
            return {"success": True, "memory": content}
        return {"success": True, "memory": "Henüz bu sohbet için kaydedilmiş bir hafıza bulunmuyor."}
    except Exception as e:
        return {"success": False, "error": str(e)}
