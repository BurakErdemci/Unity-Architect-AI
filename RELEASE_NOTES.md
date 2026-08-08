<!--
  ⚠️ BU DOSYA ELLE GÜNCELLENİYOR ve bayatlamaya açık.
  `.github/workflows/release.yml` taslak release'in GÖVDESİ olarak bunu basıyor
  (`body_path: RELEASE_NOTES.md`). 2 Ağu 2026'da içeriği hâlâ v2.2.0'ındı; o iş
  koşsaydı v2.3.0 release'ine bir önceki sürümün notları giderdi.
  ▶ Yeni sürümden ÖNCE: `CHANGELOG.md`'nin en üst bölümünü buraya taşı.
  Bu yorum GitHub'da görünmez (HTML yorumu).
-->

## Gamachine v2.3.1

Küçük ama can sıkıcı bir hatanın sürümü: **sohbete fotoğraf yapıştırınca oturum
bazen komple düşüyordu.**

> 🍎 **macOS (Apple Silicon):** `Gamachine-2.3.1-arm64.dmg`
> · 🪟 **Windows:** `Gamachine-Setup-2.3.1.exe`

### 🖼 Yapıştırılan görsel artık sohbeti öldürmüyor

Belirti şuydu: iki fotoğrafla oturum düşüyor, üç fotoğrafla düşmüyordu — yani
sorun *adet* değil **boyut**tu.

Sebep zincirin ucundaydı. Yapıştırdığın görsel diske yazılıyor ve modele yalnız
dosya *yolu* veriliyor; model o dosyayı `Read` ile açtığında sonuç base64 olarak
tek bir satır hâlinde geri geliyor. O satırın 1 MB'lık bir tavanı vardı ve
aşıldığında hata kırpılmıyor, **oturumun tamamı düşüyordu**. base64 ham boyutun
~4/3'ü olduğu için 750 KB'lık sıradan bir fotoğraf bile tavanı aşmaya yetiyordu.

Düzeltme iki katmanlı:
- Satır tavanı, ürünün diğer CLI yolunda zaten kullandığı değere yükseltildi.
- **Asıl sınır kaynağa kondu:** büyük görseller diske yazılmadan önce küçültülüyor.
  Bu hem çökmeyi kapatıyor hem de token maliyetini düşürüyor.

Şeffaf PNG'ler bu sırada bozulmuyor: alfa kanalı korunuyor. (İlk düzeltme
denemesinde şeffaf görseller tamamen siyah kareye dönüyordu — bir denetim turu
bunu yakaladı ve düzeltildi.)

### 🎮 AI artık oyunu oynayabiliyor (`manage_input`)

Play mode'a girmek ve ekran görüntüsü almak zaten vardı; eksik olan **müdahale**
etmekti. `manage_input` çalışan oyuna klavye, fare, gamepad ve UI girdisi
gönderiyor — yani AI yaptığı şeyi deneyebiliyor.

Girdi, Unity Input System'in sanal cihazlarına sürecin içinden basılıyor:
**pencere odağı gerekmiyor**, AI oynarken klavyen kilitlenmiyor.

> ⚠️ **Sınırı önce ölç:** bu olayları yalnız yeni Input System'e göre yazılmış
> oyun kodu görür. Projen eski `Input.GetKey` kullanıyorsa girdi ona ulaşmaz;
> o projelerde çalışan tek yol uGUI düğmelerini tetikleyen `ui_click`'tir.
> `manage_input action="describe"` projenin girdi arka ucunu raporlar.

### 📸 Ekran görüntüsü aracının adı düzeltildi

Modele var olmayan bir eylem adı öğretiliyordu; ekran görüntüsü istekleri bu
yüzden bazen boşa düşüyordu. Doğru ada bağlandı.

### 📖 Dokümantasyon

README (TR + EN) 105 commit'lik gerçeklikle hizalandı. Öne çıkan düzeltme bir
güvenlik iddiasıydı: dokümanlar "unityMCP hiçbir zaman onay kartı göstermez"
diyordu, oysa v2.3.0'dan beri Claude yolunda sahneyi **değiştiren** çağrılar kart
açıyor. Artık sağlayıcı bazında doğru anlatılıyor.

---

**Kurulum:** Windows'ta installer önceki sürümü otomatik kaldırır.
macOS'ta imzasız dmg "hasar görmüş" derse:
`xattr -cr "/Applications/Gamachine.app"`

⚠️ macOS'ta yalnız **Apple Silicon (arm64)** dağıtılıyor — Intel dmg'nin içine
host mimarisinin backend'i gömüldüğü ve sınanacak Intel Mac olmadığı için
bilerek yayınlanmıyor.
