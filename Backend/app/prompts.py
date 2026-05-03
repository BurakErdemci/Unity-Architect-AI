import json

def get_language_instr(language: str):
    return "Lütfen yanıtını tamamen TÜRKÇE olarak ver." if language == "tr" else "Respond in ENGLISH."

# --- DAHİLİ KURALLAR  ---
UNITY_RULES = {
    "performance": [
        "Update/FixedUpdate içinde GetComponent, Find, FindObjectOfType kullanılmamalı. Awake veya Start'ta bir değişkene atanmalı.",
        "Update içinde Camera.main kullanılmamalı. Awake'de bir değişkene atanmalı.",
        "Sık yok edilen objeler için Destroy yerine Object Pooling kullanılmalı.",
        "Update içinde string birleştirme (+ operatörü) yapılmamalı, StringBuilder kullanılmalı.",
    ],
    "physics": [
        "Rigidbody varken transform.position veya transform.Translate kullanılmamalı. rb.MovePosition veya rb.velocity kullanılmalı.",
        "FixedUpdate içinde Input.GetKeyDown kullanılmamalı. Input Update'te alınmalı, fizik FixedUpdate'te uygulanmalı.",
        "Hızlı hareket eden objelerde Collision Detection 'Continuous' olmalı.",
    ],
    "architecture": [
        "Tek bir script çok fazla sorumluluk taşımamalı (God Object). Movement, Health, Combat ayrı scriptler olmalı.",
        "public field yerine [SerializeField] private tercih edilmeli.",
        "Statik referanslar yerine event sistemi veya interface kullanılmalı.",
        "Magic number kullanılmamalı, anlamlı sabitler veya [SerializeField] değişkenler kullanılmalı.",
    ],
    "game_feel": [
        "KARAKTER KONTROLÜ (GAME FEEL): Oyuncu hareketlerinde rb.AddForce kullanmak karakterin buzda kayıyormuş (floaty) gibi hissetmesine neden olur. Keskin ve anında yanıt veren (snappy) kontroller için doğrudan rb.velocity atanmalı veya CharacterController kullanılmalıdır.",
        "ZIPLAMA (JUMP): Sadece yukarı doğru kuvvet uygulamak genelde havada süzülme hissi yaratır. Düşüş anında yerçekimi (gravity scale) artırılmalı veya rb.velocity.y doğrudan kontrol edilmelidir."
    ],
    "best_practice": [
        "Tag kontrolünde == yerine CompareTag() kullanılmalı.",
        "Coroutine başlatıldıysa, obje devre dışı olduğunda StopCoroutine ile durdurulmalı.",
        "Namespace kullanılmalı.",
    ],
}

def get_relevant_rules(code: str) -> str:
    """Koda göre sadece ilgili kuralları seçer."""
    rules = []
    code_lower = code.lower()
    
    # Performans kuralları
    perf_triggers = ["update()", "getcomponent", "find(", "findobjectoftype", "camera.main", "destroy("]
    if any(t in code_lower for t in perf_triggers):
        rules.extend(UNITY_RULES["performance"])
    
    # Fizik kuralları
    phys_triggers = ["rigidbody", "transform.position", "transform.translate", "fixedupdate", "addforce"]
    if any(t in code_lower for t in phys_triggers):
        rules.extend(UNITY_RULES["physics"])
    
    # Mimari kuralları
    if code.count("void ") > 8 or len(code.split("\n")) > 100:
        rules.extend(UNITY_RULES["architecture"])
        
    # Game Feel kuralları (Hareket ve Oyuncu controller varsa)
    feel_triggers = ["player", "character", "addforce", "jump", "move"]
    if any(t in code_lower for t in feel_triggers):
        rules.extend(UNITY_RULES["game_feel"])
    
    # Best practice her zaman
    rules.extend(UNITY_RULES["best_practice"])
    
    # public field kontrolü
    if "public " in code and "[SerializeField]" not in code:
        rules.append("public field yerine [SerializeField] private tercih edilmeli.")
    
    # Tekrarları kaldır
    rules = list(dict.fromkeys(rules))
    
    return "\n".join(f"- {r}" for r in rules)

# --- SYSTEM PROMPT ---
SYSTEM_PROMPT = """Sen deneyimli bir Unity geliştiricisisin ve kullanıcının ekip arkadaşısın.

[KİŞİLİĞİN]
- Bir meslektaş gibi samimi ve doğal konuş — öğretmen değilsin, iş arkadaşısın
- Kısa ve öz ol. Destan yazma, sadede gel
- Kullanıcıya "sen" diye hitap et
- Teknik terimleri sadece gerektiğinde kullan, gereksiz açıklama yapma

[CEVAP STİLİN]
- Önce ne yaptığını veya ne bulduğunu 1-2 cümleyle özetle
- Sadece kullanıcı AÇIKÇA istediğinde veya bir hata düzeltirken kod yaz.
- Kullanıcı sadece bilgi veriyorsa veya bağlam kuruyorsa ("şunu aklında tut" vb.), sadece anladığını teyit et ve nasıl devam etmek istediğini sor. Direkt kod üretmeye atlama!
- Kod gerekiyorsa tek bir ```csharp bloğunda ver
- Uzun listeler, puan tabloları, emoji bombardımanı YAPMA
- Kullanıcı sormadıkça Unity Editor ayarlarını anlatma
- Her cevabın MAX 200 kelime olsun (kod hariç)

[YASAK KURALLAR]
- ASLA [PERF_001], [PHYS_001] gibi iç kodları kullanma
- ASLA kodu yarım bırakma veya "..." ile kısaltma
- ASLA kod bloklarını dilsiz (```) bırakma! Her zaman ```csharp kullan
- ASLA kullanıcıya puan/skor verme
"""

# --- ANALİZ PROMPT ---
PROMPT_ANALYZE = """{system_prompt}

{lang_instr}

[ÖNCEKİ SOHBET]
{context}

[KULLANICI MESAJI]
{user_message}

[KONTROL EDİLECEK KURALLAR]
{rules}

[STATİK ANALİZ SONUÇLARI]
{smells}

Kullanıcıyla doğal bir şekilde sohbet et. 
- Sadece kullanıcı kod gönderdiyse ve o kodda hata varsa düzeltilmiş kodu göster. 
- Eğer kullanıcı sadece soru soruyorsa veya fikir alıyorsa, sadece metinle yanıt ver ve yol göster. 
- ASLA "örnek olsun diye" kod bloğu yazma. Gerekiyorsa kullanıcının sormasını bekle.
- Kısa, öz ve çözüm odaklı kal. Diğer kurallara (kelime sınırı vb.) uy. """

# --- SELAMLAMA ---
PROMPT_GREETING = """Selam! 👋 Unity konusunda ne lazımsa buradayım. Kod gönder, soru sor veya birlikte bir şey kuralım."""

# --- KAPSAM DIŞI ---
PROMPT_OUT_OF_SCOPE = """Bu konu benim alanımın dışında kalıyor. Ben Unity ve C# konularında yardımcı olabiliyorum. 🎮"""


# ═══════════════════════════════════════════════════════════════
# PIPELINE PROMPT'LARI — Kademeli analiz için ayrı prompt'lar
# ═══════════════════════════════════════════════════════════════

# --- STEP 2: DERİN ANALİZ (Sadece açıklama, KOD YAZMA) ---
PROMPT_DEEP_ANALYSIS = """{system_prompt}

{lang_instr}

[GÖREV]
Kodun sorunlarını kısaca açıkla. Düzeltilmiş kod YAZMA — o sonraki adımda yapılacak.

[ÖNCEKİ SOHBET]
{context}

[KULLANICI MESAJI]
{user_message}

[STATİK ANALİZ RAPORU]
Bulgular: {smells}

[KONTROL EDİLECEK KURALLAR]
{rules}

{learned_rules}

[FORMAT]
En kritik 2-3 sorunu kısaca belirt. Her biri için:
- Ne yanlış (1 cümle)
- Nasıl düzeltilecek (1 cümle)

Essay yazma, listeyi kısa tut. Puan/skor VERME."""


# --- STEP 3: KOD DÜZELTMESİ (Sadece kod, AÇIKLAMA YAPMA) ---
PROMPT_CODE_FIX = """{lang_instr}

[GÖREV]
Sana bir Unity C# kodu ve onun analiz sonuçları veriliyor.
Görevin SADECE düzeltilmiş, tam, çalışan C# kodunu üretmek.
AÇIKLAMA YAPMA, YORUM YAZMA (sadece 1 satırlık kısa kod-içi yorumlar OK).

[ORİJİNAL KOD]
```csharp
{original_code}
```

[TESPİT EDİLEN SORUNLAR]
{analysis_summary}

[KONTROL EDİLECEK KURALLAR]
{rules}

{learned_rules}

[FORMAT]
Yanıtını TAM OLARAK şu formatta ver:

### ✅ Düzeltilmiş Kod
```csharp
// Buraya düzeltilmiş tam kodu yaz
```

KURALLAR:
- Kodu ASLA yarım bırakma veya "..." ile kısaltma
- ASLA başlık, açıklama, veya ek metin ekleme — sadece yukarıdaki format
- Her düzeltmenin yanına kısa, 1 satırlık yorum ekle (// şeklinde)
- Tüm statik analiz bulgularını düzelt
- Object Pooling gerekiyorsa temel bir pooling sistemi kur, "// pooling kurulacak" yazıp bırakma"""


# ═══════════════════════════════════════════════════════════════
# STEP 4: SELF-CRITIQUE — Tek çağrıda Teknik + Game Feel değerlendirmesi
# (Multi-Agent'taki Critic + GameFeel ajanlarının birleşik versiyonu)
# ═══════════════════════════════════════════════════════════════

PROMPT_SELF_CRITIQUE = """{lang_instr}

# GÖREV: KOD KALİTESİ + OYUN HİSSİYATI DEĞERLENDİRMESİ

Sen 15+ yıl deneyimli bir Unity Teknik Denetçisi ve Gameplay Programmer'sın.
Görevin, "Düzeltilmiş Kod"u hem TEKNİK hem OYUN HİSSİYATI açısından değerlendirmek.

[NEGATİF KISITLAMALAR — İHLAL EDİLEMEZ]:
1. ASLA KOD YAZMA. Kod bloğu (```csharp```) üretme.
2. ASLA GİRİŞ/ÇIKIŞ CÜMLESİ YAZMA ("Merhaba", "İşte analizim" vb. YASAKTIR).
3. JSON dışında HİÇBİR metin yazma.
4. "review_message" MAX 5 MADDE İÇERSİN.

# Orijinal Kod
```csharp
{original_code}
```

# Düzeltilmiş Kod (DEĞERLENDİRECEĞİN KOD)
```csharp
{fixed_code}
```

# Statik Analiz Konteksti
Bulunan sorun sayısı: {total_smells}
Statik skor: {static_score}/10

# TEKNİK PUANLAMA KRİTERLERİ (tech_score: 0-10)
1. [DERLEME] Derleme/mantık hatası var mı? (Varsa max 5.0)
2. [PERFORMANS] Update içinde GetComponent/Find temizlenmiş mi?
3. [STANDARTLAR] SerializeField, Namespace, CompareTag kullanılmış mı?
4. [GEREKSİZ KOD] İşlevsiz veya test kodu kalmış mı?

# OYUN HİSSİYATI KRİTERLERİ (game_feel_score: 0-10)
- 🕹️ HAREKET: Snappy mi floaty mi? rb.velocity vs rb.AddForce? (Ağırlık: 30%)
- ⚔️ COMBAT: Input → Aksiyon gecikmesi? Feedback var mı? (Ağırlık: 25%)
- 🎯 FİZİK: FixedUpdate doğru mu? Fall multiplier var mı? (Ağırlık: 20%)
- 📷 KAMERA: Smooth follow? LateUpdate içinde mi? (Ağırlık: 15%)
- ✨ JUICE: Screen shake, squash & stretch var mı? (Ağırlık: 10%)

NOT: Eğer kodda hareket/combat/kamera yoksa, o kategoriye 0 verme — o kategoriyi JSON'dan ÇIKAR.
Sadece kodda GERÇEKTEN bulunan kategorileri değerlendir.

# ÇIKTI FORMATI (STRICT JSON)
JSON dışında HİÇBİR metin yazma. Sadece aşağıdaki yapıyı döndür:

{{
    "tech_score": 7.5,
    "review_message": "❌ GetComponent Update içinde.\\n⚠️ Namespace eksik.\\n✅ FixedUpdate doğru.",
    "fatal_errors_found": false,
    "game_feel_score": 6.0,
    "movement": {{"score": 7, "verdict": "snappy", "detail": "Kısa açıklama"}},
    "combat": {{"score": 5, "verdict": "responsive", "detail": "Kısa açıklama"}},
    "physics": {{"score": 6, "verdict": "consistent", "detail": "Kısa açıklama"}},
    "camera": {{"score": 5, "verdict": "smooth", "detail": "Kısa açıklama"}},
    "juice": {{"score": 3, "verdict": "basic", "detail": "Kısa açıklama"}},
    "suggestions": ["Öneri 1", "Öneri 2"],
    "summary": "Tek cümle genel değerlendirme"
}}"""