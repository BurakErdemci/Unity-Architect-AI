# 🤖 AI Model Karşılaştırması — Unity Architect AI

Bu sayfa, Unity Architect AI platformunun kullandığı modeller dahil çeşitli AI sistemlerinin aynı prompt üzerindeki kod üretim kalitesini karşılaştırmaktadır.

> **Not:** Bu karşılaştırma aşağıda tanımlanan teknik kriterler esas alınarak yapılmıştır. Farklı kullanım senaryolarında (hızlı prototip, basit script, öğrenme amaçlı kullanım vb.) sonuçlar değişebilir. Her model kendi bağlamında farklı avantajlar sunabilir.

---

## 📐 Değerlendirme Kriterleri

Karşılaştırma aşağıdaki dört ana kriter üzerinden yapılmıştır:

| Kriter | Açıklama |
|--------|----------|
| **Kod Doğruluğu** | Physics bug yokluğu, doğru Update/FixedUpdate ayrımı, Unity API'sinin doğru kullanımı |
| **Game Feel** | Apex gravity, acceleration/deceleration, double jump gibi oyun hissiyatını doğrudan etkileyen mekanikler |
| **Mimari Yapı** | Single Responsibility, ScriptableObject kullanımı, event-driven tasarım, genişletilebilirlik |
| **Production Readiness** | Interpolation, ContinuousCD, null korumaları, namespace, defensive coding |

---

## 📋 Test Promptu

```
Unity 2D platformer için yerçekimi ve zıplama sistemi yaz.
Karakter yerde olduğunda zıplayabilsin, havada ikinci zıplama yapabilsin.
Coyote time ve jump buffer ekle.
```

Bu prompt bilinçli seçildi: **coyote time**, **jump buffer** ve **double jump** gibi game feel detayları bir AI sisteminin Unity bilgisini ve kod kalitesini net biçimde ortaya koyar.

---

## 🏆 Sonuç Tablosu

| Sıra | Model | Dosya | Mimari | Kod Doğruluğu | Game Feel | Production Ready |
|------|-------|:---:|:---:|:---:|:---:|:---:|
| 🥇 1 | **Unity Architect AI — Multi-Agent** | 6 | ⭐⭐⭐ | ✅ | ⭐⭐⭐ | ✅ |
| 🥈 2 | **Unity Architect AI — Claude 4.6 Opus** | 1 | ⭐⭐ | ✅ | ⭐⭐ | ✅ |
| 🥉 3 | **Kimi K2.5** | 1 | ⭐⭐ | ⚠️ minor | ⭐⭐ | ⚠️ |
| 4 | **ChatGPT 5.4** | 1 | ⭐ | ✅ | ⭐ | ⚠️ |
| 5 | **DeepSeek V3** | 1 | ⭐ | ❌ | ⭐ | ❌ |
| 6 | **Gemini 3.1 Flash Lite** | 1 | ⭐ | ❌ | ⭐ | ❌ |

> **KB Modu** (AI kullanmadan, kural tabanlı): İstenmeden wall sliding ekledi. Farklı bir kategori olduğundan sıralamaya dahil edilmedi.

**Detaylı özellik karşılaştırması:**

| Özellik | Multi-Agent | Opus (Tek Ajan) | Kimi K2.5 | ChatGPT 5.4 | DeepSeek V3 | Gemini Lite |
|---------|:-----------:|:---------------:|:---------:|:-----------:|:-----------:|:-----------:|
| Acceleration/Deceleration | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| Double Jump | ✅ | ✅ | ✅ | ❌ | ❌ | ⚠️ |
| Apex Gravity | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| ScriptableObject | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Event System | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Interpolation + ContinuousCD | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| OverlapBox (hassas ground check) | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| Physics Bug | ❌ | ❌ | ⚠️ minor | ❌ | ✅ | ✅ |

---

## 🔍 Model Bazlı Detaylı Analiz

### 🥇 1. Unity Architect AI — Multi-Agent Modu

**6 dosya, modüler production mimarisi.**

| Kriter | Değerlendirme |
|--------|---------------|
| Kod Doğruluğu | Hatasız. Update/FixedUpdate ayrımı doğru. |
| Game Feel | Apex gravity, air control, double jump — en kapsamlı |
| Mimari | ScriptableObject + event-driven + Single Responsibility |
| Production Ready | Interpolation, ContinuousCD, namespace, sealed, null korumaları |

**Üretilen dosyalar:**
- `PlayerController.cs` — hareket + input
- `PlayerJumpSystem.cs` — zıplama mantığı
- `GravityController.cs` — yerçekimi yönetimi
- `PlayerGroundDetector.cs` — yer tespiti + event
- `GravitySettings.cs` — ScriptableObject
- `JumpSettings.cs` — ScriptableObject

Öne çıkan teknik detaylar: `OnGroundStateChanged` event'i sayesinde animator, ses ve particle sistemleri ground detection'a polling yapmadan bağlanabilir. Designer kod açmadan Inspector üzerinden tüm parametreleri ayarlayabilir.

---

### 🥈 2. Unity Architect AI — Claude 4.6 Opus (Tek Ajan)

**Tek dosya, ancak diğer modellerin atladığı 2 kritik satır:**

```csharp
rb.interpolation = RigidbodyInterpolation2D.Interpolate;         // Farklı frame rate'lerde titreme önlenir
rb.collisionDetectionMode = CollisionDetectionMode2D.Continuous; // İnce platformlarda geçip gitme (tunneling) önlenir
```

Unity tutorial'larında bile sık atlanan bu iki ayar, test edilen diğer modellerin hiçbirinde yer almadı.

| Kriter | Değerlendirme |
|--------|---------------|
| Kod Doğruluğu | Hatasız. |
| Game Feel | Acceleration + double jump mevcut, apex gravity yok |
| Mimari | Tek dosya ama clean callback pattern (`OnLanded()`), genişletilebilir |
| Production Ready | Interpolation + ContinuousCD + null fallback + OverlapBox |

---

### 🥉 3. Kimi K2.5

**Güçlü mimari, küçük matematik hatası.**

Acceleration/deceleration ve double jump doğru implement edilmiş. Input/physics ayrımı yerinde (`jumpRequested` Update'te, `HandleJump` FixedUpdate'te).

Ancak gravity formülünde hata mevcut:

```csharp
// rb.gravityScale = 0 → tüm gravity manuel uygulanmalı
// ❌ Yanlış: beklenenden zayıf gravity uygular
rb.velocity += Vector2.up * Physics2D.gravity.y * (currentGravity - 1f) * dt;

// ✅ Doğru:
rb.velocity += Vector2.up * Physics2D.gravity.y * currentGravity * dt;
```

| Kriter | Değerlendirme |
|--------|---------------|
| Kod Doğruluğu | Gravity formülü matematiksel olarak hatalı |
| Game Feel | Acceleration + double jump mevcut |
| Mimari | Tek dosya, temiz yapı |
| Production Ready | Interpolation/ContinuousCD yok |

---

### 4. ChatGPT 5.4

**Okunabilir ve temiz, ancak sade.**

Variable jump height (`JumpCutMultiplier`) doğru implement edilmiş. Genel kod kalitesi iyi.

| Kriter | Değerlendirme |
|--------|---------------|
| Kod Doğruluğu | Hatasız |
| Game Feel | Variable jump height var, acceleration/apex gravity yok |
| Mimari | Tek dosya, düz yapı |
| Production Ready | Interpolation/ContinuousCD yok, OverlapCircle kullanılmış |

Hızlı prototip için yeterli, production için eksik.

---

### 5. DeepSeek V3

**Framerate'e bağımlı physics bug.**

```csharp
// ❌ Update() içinde physics modifikasyonu + Time.fixedDeltaTime
private void HandleJump() // Update()'te çağrılıyor
{
    rb.velocity += Vector2.up * Physics2D.gravity.y * (fallMultiplier - 1) * Time.fixedDeltaTime;
}
```

`Update` her frame'de, `FixedUpdate` ise sabit aralıklarla çalışır. `Time.fixedDeltaTime`'ı `Update` içinde kullanmak 60fps ile 120fps'de farklı zıplama yüksekliği üretir.

| Kriter | Değerlendirme |
|--------|---------------|
| Kod Doğruluğu | Update/FixedUpdate hatası — framerate bağımlı davranış |
| Game Feel | Temel coyote time + buffer mevcut |
| Mimari | Namespace var, tek dosya |
| Production Ready | Eksik |

---

### 6. Gemini 3.1 Flash Lite

**Birden fazla teknik sorun.**

```csharp
// ❌ Physics Update'te yapılıyor
private void ApplyJumpGravity() // Update()'te çağrılıyor
{
    rb.velocity += Vector2.up * Physics2D.gravity.y * (fallMultiplier - 1) * Time.deltaTime;
}

// ❌ Gravity double-apply riski:
// Rigidbody gravity scale sıfırlanmadan üstüne manuel gravity ekleniyor
```

Double jump logic'i, `canDoubleJump` bool'u coyote time ile aynı koşulu paylaşıyor — edge case'lerde yanlış ateşleyebilir.

| Kriter | Değerlendirme |
|--------|---------------|
| Kod Doğruluğu | Update/FixedUpdate hatası + gravity double-apply riski |
| Game Feel | Kısmi double jump, temel coyote time |
| Mimari | Namespace yok, tek dosya |
| Production Ready | Eksik |

---

## 🛠️ Test Bilgileri

| Alan | Detay |
|------|-------|
| Prompt | 2D platformer yerçekimi + zıplama + coyote time + jump buffer |
| Test tarihi | Nisan 2026 |
| Karşılaştırılan modeller | Multi-Agent Claude, Claude 4.6 Opus, Kimi K2.5, ChatGPT 5.4, DeepSeek V3, Gemini 3.1 Flash Lite |
| Değerlendirme yöntemi | Kod doğruluğu, game feel, mimari yapı, production readiness |

---

*Unity Architect AI — [GitHub](https://github.com/BurakErdemci/Unity-Architect-AI)*
