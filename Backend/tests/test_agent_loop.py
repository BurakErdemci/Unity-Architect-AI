import sys
import asyncio
import os

# app klasörüne erişim için path ayarı
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

from database import DatabaseManager
from agentic.agent_runner import AgentRunner

async def main():
    # Database yolu app içindeki unity_ai.db'ye bakmalı
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../app/unity_ai.db'))
    db = DatabaseManager(db_path)
    
    # Sadece ilk kullanıcıyı (admin) alıyoruz
    user_id = 1
    provider_type, model_name, _, _, _ = db.get_ai_config(user_id)
    api_key = db.get_api_key(user_id, provider_type)
    workspace_path = db.get_last_workspace(user_id)

    print(f"🔹 Provider: {provider_type}")
    print(f"🔹 Model: {model_name}")
    print(f"🔹 Workspace: {workspace_path}")

    if not api_key:
        print("❌ API Key bulunamadı! (Ollama/KB hariç bir sağlayıcı seçiliyse key gereklidir.)")
        return

    runner = AgentRunner(
        provider_type=provider_type,
        api_key=api_key,
        model_name=model_name,
        workspace_path=workspace_path,
        language="tr",
        context="Bu bir test sohbetidir.",
        use_thinking=True
    )

    user_message = "Projeyi tarayıp içinde 'PlayerMovement' veya hareketle ilgili classlar var mı bir bakar mısın? Varsa içeriğinde ne gibi fonksiyonlar var kısaca özetle."

    print(f"\n👤 Kullanıcı: {user_message}\n")
    print("-" * 50)

    try:
        async for event in runner.run(user_message):
            if event.type == "thinking":
                print(f"🧠 Düşünüyor... {event.data.get('text', '')[:150].strip()}...")
            elif event.type == "tool_call":
                print(f"\n🛠️  ARAÇ ÇAĞRISI: {event.data['tool']}")
                print(f"   Parametreler: {event.data['arguments']}")
            elif event.type == "tool_result":
                print(f"   ✅ Sonuç: {event.data.get('summary', '')}")
            elif event.type == "text":
                print(f"\n🤖 AI: {event.data['content']}")
            elif event.type == "response":
                print(f"\n✨ FİNAL YANIT:\n{event.data['content']}")
            elif event.type == "error":
                print(f"\n❌ HATA: {event.data['message']}")
    except Exception as e:
        print(f"\n❌ SİSTEM HATASI: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
