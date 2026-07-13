## Unity Architect AI v2.1.2

Canlı animasyon-pipeline testinden çıkan üç düzeltme ve bir CLI oturum-durumu hatası giderildi.

### 🎞️ Animasyon tool düzeltmeleri
- **`manage_fbx full_setup` artık klip ayarlarını EZMİYOR:** `setup_clips` ile verdiğin klip adlarını ve loop bayraklarını koruyor. Daha önce `full_setup`'ı tekrar çalıştırınca klip adları FBX adına dönüyor, loop'lar `false`'a sıfırlanıyordu. Artık mevcut konfig korunuyor ve diagnostics'te `CLIP_CONFIG_PRESERVED` bilgisi düşüyor.
- **Akıllı adlandırma artık `X_Anim_Walk` / Mixamo `@` konvansiyonlarını tanıyor:** `YagmaciBrute_Anim_Walk.fbx` gibi önekli dosyalar doğru kategoriye (Walk/Run/Attack…) çözülüyor; ayrıca `setup_clips` ile verdiğin klip adı da tespit kaynağı olarak kullanılıyor. Böylece controller'ı elle kurmaya gerek kalmıyor.
- **`animator_get_info` artık child'larda Animator arıyor:** Prefab kökünü verdiğinde Animator model child'ındaysa da buluyor (`GetComponentInChildren`) — "No Animator component" hatası kalktı.

### 🐛 CLI oturum-durumu düzeltmesi
- **Cursor "Giriş Yap" butonu:** Cursor'dan çıkış yapınca model seçicide artık doğru şekilde "Giriş Yap" butonu görünüyor. Daha önce `agent status`'un "Not logged in" çıktısı yanlış yorumlanıyordu (metin "logged in" alt-dizesini içerdiği için oturum açık sanılıyordu).

### 🔄 Güncelleme & Güvenlik
Uygulama açılışta yeni sürümü kontrol eder ve **haber verir** — kurulumu sen onaylarsın, sessiz/otomatik kurulum yoktur. Windows'ta kurulum eski sürümü otomatik kaldırır.

> macOS (Apple Silicon) paketi ayrıca eklenecektir.
