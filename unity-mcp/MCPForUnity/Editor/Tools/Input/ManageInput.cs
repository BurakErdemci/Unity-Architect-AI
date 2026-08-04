using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using MCPForUnity.Editor.Helpers;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace MCPForUnity.Editor.Tools.Input
{
    /// <summary>
    /// Çalışan oyuna sanal cihazlar üzerinden klavye/fare/gamepad girdisi gönderir.
    ///
    /// Kapsam kararı (kullanıcı, 4 Ağu 2026): yalnız Input System sanal cihazı +
    /// uGUI buton tıklaması. İşletim sistemi düzeyinde girdi (SendInput) BİLEREK
    /// yok — pencere odağı gerektirir, kullanıcının makinesini işgal eder ve ayrı
    /// bir güvenlik yüzeyi açar.
    /// </summary>
    [McpForUnityTool("manage_input", AutoRegister = false, Group = "core")]
    [InitializeOnLoad]
    public static class ManageInput
    {
        /// <summary>
        /// ⚠️ Bu abonelik denetimde eklendi (4 Ağu 2026). InputSystemBridge'in
        /// yorumu "domain reload'u yakalayıp durumu sıfırlıyoruz" diyordu ama
        /// ResetCachedState'i çağıran KİMSE yoktu — yorum var olmayan bir kancayı
        /// tarif ediyordu. Sıradan bir reload statikleri zaten sıfırlıyor, ama
        /// "Enter Play Mode Options → Reload Domain kapalı" projelerinde statikler
        /// yaşıyor: bir oturumda basılı bırakılan W, sonraki oturumda describe'ta
        /// görünüyor ve ilk tuş olayında yeniden basılıyordu.
        /// </summary>
        static ManageInput()
        {
            EditorApplication.playModeStateChanged += state =>
            {
                if (state != PlayModeStateChange.ExitingPlayMode) return;

                // ⚠️ Yalnız önbelleği temizlemek YETMİYOR — doğrulama turunda
                // bulundu (4 Ağu 2026). Sanal cihazlar Editor'de yaşamaya devam
                // ediyor ve son kuyruğa alınan durumlarını taşıyorlar; önbelleği
                // unutup cihazı bırakmak, "describe hiçbir şey basılı değil derken
                // cihazda W basılı" ayrışmasını üretebilirdi. Cihazları da
                // kaldırıyoruz: bir sonraki çağrı zaten temizini yaratır.
                var error = InputSystemBridge.RemoveAllVirtualDevices();
                if (error != null)
                    Debug.LogWarning($"[manage_input] Play mode çıkışında temizlik eksik kaldı: {error}");
            };
        }

        // Tek bir MCP çağrısının Unity'yi süresiz bloke etmesini engelleyen tavan.
        //
        // ⚠️ 60 → 20 (denetim, 4 Ağu 2026). Sebep ölçüldü, tercih değil: taşıma
        // katmanının yanıt penceresi 30 saniye. 60 saniyelik bir tavan, çağıran
        // 30. saniyede zaman aşımı hatası aldıktan SONRA hâlâ girdi göndermeye devam
        // eden bir C# işi bırakıyordu — kullanıcı hatayı görüp yeni bir komut
        // verdiğinde eski dizi onun üstüne yazıyordu. Tavan pencerenin altında
        // kalmak zorunda. Daha uzun oyun için diziyi böl; zaten aralarda ekran
        // görüntüsü almak gereken şey.
        private const double MaxSequenceSeconds = 20.0;

        // Süre verilmeyen tap adımlarının gerçek maliyeti. Tavan hesabı bunu 0
        // sayıyordu; 5000 adımlık bir dizi "0 ms" diye geçip ~250 saniye koşuyordu.
        private const int DefaultTapMs = 50;

        // Süresi olmayan adımlar da iş yapıyor (reflection + kuyruk + flush, ya da
        // ui_click'te keyfi oyun kodu). Süre tavanı onları göremediği için ayrı bir
        // sayı tavanı gerekiyor.
        private const int MaxSequenceSteps = 200;

        public static async Task<object> HandleCommand(JObject @params)
        {
            if (@params == null)
                return new ErrorResponse("Parameters cannot be null.");

            var p = new ToolParams(@params);
            string action = p.Get("action")?.ToLowerInvariant();

            if (string.IsNullOrEmpty(action))
                return new ErrorResponse("'action' parameter is required.");

            var properties = ReadProperties(@params, out var propertiesParseError);
            if (propertiesParseError != null)
                return new ErrorResponse(propertiesParseError);

            // describe her zaman serbest: "neden çalışmıyor" sorusunun cevabı
            // play mode dışındayken de alınabilmeli.
            if (action == "describe")
            {
                return new SuccessResponse("Input bridge durumu.", new
                {
                    bridge = InputSystemBridge.Describe(),
                    playMode = new
                    {
                        isPlaying = EditorApplication.isPlaying,
                        isPaused = EditorApplication.isPaused,
                    },
                    activeInputHandling = DescribeActiveInputHandling(),
                    validKeys = InputSystemBridge.KnownKeyNames(),
                    validMouseButtons = InputSystemBridge.KnownMouseButtons(),
                    validGamepadButtons = InputSystemBridge.KnownGamepadButtons(),
                });
            }

            if (action == "reset")
            {
                var resetError = InputSystemBridge.RemoveAllVirtualDevices();
                return resetError != null
                    ? new ErrorResponse(resetError)
                    : new SuccessResponse("Sanal cihazlar kaldırıldı, basılı tuş kümesi sıfırlandı.");
            }

            // Play mode dışında girdinin alıcısı yok. Sessizce başarılı dönmek,
            // modele "bastım ama bir şey olmadı" dedirtip yanlış teşhise yollar.
            if (!EditorApplication.isPlaying)
                return new ErrorResponse(
                    "Girdi yalnızca play mode'da gönderilebilir. Önce manage_editor(action='play') çağır. " +
                    "Mevcut durumu action='describe' ile görebilirsin.");

            if (EditorApplication.isPaused)
                return new ErrorResponse(
                    "Oyun duraklatılmış durumda; girdi işlenmez. manage_editor(action='pause') ile devam ettir. " +
                    "⚠️ 'pause' bir toggle'dır, ikinci çağrı duraklatmayı KALDIRIR.");

            // ⚠️ ui_click, Input System kapısının ÖNÜNDE. Denetimde ölçüldü
            // (4 Ağu 2026): kapı switch'ten önce çalıştığı için, "girdi arka ucundan
            // bağımsız, eski Input API'li projelerde de çalışır" diye belgelenen tek
            // eylem, paket kurulu değilken erişilemez oluyordu. Araç kendi vaadini
            // tutmuyordu. ui_click yalnız uGUI'ye bağlı, Input System'e değil.
            if (action == "ui_click")
                return HandleUiClick(p, properties);

            // ⚠️ Doğrulama turunda bulundu (4 Ağu 2026): ilk düzeltme yalnız ÜST
            // DÜZEY ui_click'i kapının önüne almıştı. Oysa sequence de ui_click
            // adımını destekliyor, yani "Input System gerekmez" denen eylem bir dizi
            // içine konduğu anda yine engelleniyordu. Kapatma iddiası bir yolu
            // kapatmış, sınıfı kapatmamıştı.
            if (!InputSystemBridge.Available && !OnlyNeedsUgui(action, properties))
                return new ErrorResponse(InputSystemBridge.UnavailableReason);

            try
            {
                switch (action)
                {
                    case "key":
                        return await HandleKey(properties);
                    case "mouse_move":
                        return HandleMouseMove(properties);
                    case "mouse_button":
                        return await HandleMouseButton(properties);
                    case "scroll":
                        return HandleScroll(properties);
                    case "gamepad":
                        return HandleGamepad(properties);
                    case "sequence":
                        return await HandleSequence(properties);
                    default:
                        return new ErrorResponse(
                            $"Unknown action: '{action}'. Valid actions: describe, key, mouse_move, " +
                            "mouse_button, scroll, gamepad, ui_click, sequence, reset.");
                }
            }
            catch (Exception ex)
            {
                return new ErrorResponse($"manage_input '{action}' başarısız: {ex.Message}");
            }
        }

        // ---------- Tekil eylemler ----------

        private static async Task<object> HandleKey(JObject props)
        {
            var keys = ReadStringList(props, "keys", "key");
            if (keys.Count == 0)
                return new ErrorResponse("'key' ya da 'keys' gerekli. Örn: {\"key\": \"W\"}.");

            string state = (props?["state"]?.ToString() ?? "tap").ToLowerInvariant();

            switch (state)
            {
                case "down":
                {
                    var err = InputSystemBridge.SetKeys(keys, null);
                    return err != null ? new ErrorResponse(err) : Held($"{string.Join(", ", keys)} basılı.");
                }
                case "up":
                {
                    var err = InputSystemBridge.SetKeys(null, keys);
                    return err != null ? new ErrorResponse(err) : Held($"{string.Join(", ", keys)} bırakıldı.");
                }
                case "tap":
                {
                    int durationMs = props?["duration_ms"]?.Value<int?>() ?? DefaultTapMs;
                    var downErr = InputSystemBridge.SetKeys(keys, null);
                    if (downErr != null) return new ErrorResponse(downErr);

                    bool completed = await WaitFrames(durationMs);

                    var upErr = InputSystemBridge.SetKeys(null, keys);
                    if (upErr != null) return new ErrorResponse(upErr);

                    if (!completed)
                        return new ErrorResponse(
                            $"Play mode {durationMs}ms dolmadan sona erdi; tuş istenen süre basılı KALMADI. " +
                            "Tuşlar bırakıldı.");

                    return Held($"{string.Join(", ", keys)} {durationMs}ms basılıp bırakıldı.");
                }
                default:
                    return new ErrorResponse($"'state' şunlardan biri olmalı: down, up, tap. Gelen: '{state}'.");
            }
        }

        private static object HandleMouseMove(JObject props)
        {
            Vector2? absolute = ReadVector2(props, "x", "y");
            Vector2? delta = ReadVector2(props, "dx", "dy");

            if (absolute == null && delta == null)
                return new ErrorResponse("Mutlak konum için {\"x\":..,\"y\":..}, göreli için {\"dx\":..,\"dy\":..} ver.");

            var err = InputSystemBridge.SetMouse(absolute, delta, null, null, null);
            return err != null ? new ErrorResponse(err) : Held("Fare taşındı.");
        }

        private static async Task<object> HandleMouseButton(JObject props)
        {
            var buttons = ReadStringList(props, "buttons", "button");
            if (buttons.Count == 0)
                return new ErrorResponse("'button' gerekli. Örn: {\"button\": \"Left\"}.");

            string state = (props?["state"]?.ToString() ?? "tap").ToLowerInvariant();

            switch (state)
            {
                case "down":
                {
                    var err = InputSystemBridge.SetMouse(null, null, null, buttons, null);
                    return err != null ? new ErrorResponse(err) : Held($"{string.Join(", ", buttons)} basılı.");
                }
                case "up":
                {
                    var err = InputSystemBridge.SetMouse(null, null, null, null, buttons);
                    return err != null ? new ErrorResponse(err) : Held($"{string.Join(", ", buttons)} bırakıldı.");
                }
                case "tap":
                {
                    int durationMs = props?["duration_ms"]?.Value<int?>() ?? DefaultTapMs;
                    var downErr = InputSystemBridge.SetMouse(null, null, null, buttons, null);
                    if (downErr != null) return new ErrorResponse(downErr);

                    bool completed = await WaitFrames(durationMs);

                    var upErr = InputSystemBridge.SetMouse(null, null, null, null, buttons);
                    if (upErr != null) return new ErrorResponse(upErr);

                    if (!completed)
                        return new ErrorResponse(
                            $"Play mode {durationMs}ms dolmadan sona erdi; düğme istenen süre basılı KALMADI. " +
                            "Düğmeler bırakıldı.");

                    return Held($"{string.Join(", ", buttons)} tıklandı.");
                }
                default:
                    return new ErrorResponse($"'state' şunlardan biri olmalı: down, up, tap. Gelen: '{state}'.");
            }
        }

        private static object HandleScroll(JObject props)
        {
            var scroll = ReadVector2(props, "x", "y") ?? new Vector2(0f, props?["amount"]?.Value<float?>() ?? 0f);
            if (scroll == Vector2.zero)
                return new ErrorResponse("Kaydırma miktarı sıfır. {\"y\": 1} ya da {\"amount\": -1} ver.");

            var err = InputSystemBridge.SetMouse(null, null, scroll, null, null);
            return err != null ? new ErrorResponse(err) : Held($"Kaydırıldı ({scroll.x}, {scroll.y}).");
        }

        private static object HandleGamepad(JObject props)
        {
            Vector2? left = ReadVector2(props?["left_stick"] as JObject, "x", "y");
            Vector2? right = ReadVector2(props?["right_stick"] as JObject, "x", "y");
            float? leftTrigger = props?["left_trigger"]?.Value<float?>();
            float? rightTrigger = props?["right_trigger"]?.Value<float?>();
            var down = ReadStringList(props, "buttons_down", null);
            var up = ReadStringList(props, "buttons_up", null);

            if (left == null && right == null && leftTrigger == null && rightTrigger == null
                && down.Count == 0 && up.Count == 0)
                return new ErrorResponse(
                    "Değiştirilecek bir şey verilmedi. left_stick/right_stick/left_trigger/" +
                    "right_trigger/buttons_down/buttons_up alanlarından en az biri gerekli.");

            var err = InputSystemBridge.SetGamepad(left, right, leftTrigger, rightTrigger, down, up);
            return err != null ? new ErrorResponse(err) : Held("Gamepad durumu güncellendi.");
        }

        /// <summary>
        /// uGUI butonuna doğrudan onClick.Invoke() ile basar. Sanal cihaz yolundan
        /// AYRI tutuldu: bu yol girdi arka ucundan bağımsızdır, yani oyun kodu hâlâ
        /// eski Input API'sini kullanan projelerde bile çalışan tek eylemdir.
        /// </summary>
        private static object HandleUiClick(ToolParams p, JObject props)
        {
            string target = p.Get("target") ?? props?["target"]?.ToString();
            if (string.IsNullOrWhiteSpace(target))
                return new ErrorResponse("'target' gerekli — sahne hiyerarşisindeki yol ya da GameObject adı.");

            var go = GameObject.Find(target);
            if (go == null)
                return new ErrorResponse(
                    $"'{target}' bulunamadı. GameObject.Find yalnız ETKİN nesneleri bulur ve tam yol bekler " +
                    "(örn. 'Canvas/StartButton').");

            var buttonType = FindUiType("UnityEngine.UI.Button");
            if (buttonType == null)
                return new ErrorResponse("uGUI (com.unity.ugui) bu projede bulunamadı; ui_click kullanılamaz.");

            var button = go.GetComponent(buttonType);
            if (button == null)
                return new ErrorResponse($"'{target}' üzerinde bir UnityEngine.UI.Button bileşeni yok.");

            var interactable = buttonType.GetProperty("interactable")?.GetValue(button) as bool?;
            if (interactable == false)
                return new ErrorResponse($"'{target}' butonu interactable=false; tıklama yok sayılırdı.");

            try
            {
                var onClick = buttonType.GetProperty("onClick")?.GetValue(button);
                var invoke = onClick?.GetType().GetMethod("Invoke", Type.EmptyTypes);
                if (invoke == null)
                    return new ErrorResponse("Button.onClick.Invoke() çözülemedi.");

                invoke.Invoke(onClick, Array.Empty<object>());
                return new SuccessResponse($"'{target}' butonunun onClick olayı tetiklendi.");
            }
            catch (Exception ex)
            {
                return new ErrorResponse($"onClick çağrısı başarısız: {ex.InnerException?.Message ?? ex.Message}");
            }
        }

        // ---------- Sequence ----------

        /// <summary>
        /// Tek MCP turunda çok adımlı girdi. Bunun var olma sebebi hız: her tuş için
        /// ayrı tur atmak saniyeler sürer ve oyun oynanamaz hale gelir.
        /// </summary>
        private static async Task<object> HandleSequence(JObject props)
        {
            if (props?["steps"] is not JArray steps || steps.Count == 0)
                return new ErrorResponse(
                    "'steps' dizisi gerekli. Örn: [{\"type\":\"key\",\"key\":\"W\",\"state\":\"down\"}," +
                    "{\"type\":\"wait\",\"ms\":2000},{\"type\":\"key\",\"key\":\"W\",\"state\":\"up\"}]");

            // ⚠️ Bu hesap denetimde yeniden yazıldı (4 Ağu 2026). Eski hâli iki
            // bağımsız yoldan aşılabiliyordu: (1) süresi verilmeyen tap adımları 0
            // sayılıyordu, (2) negatif bir `ms` toplamı düşürüp pozitif bir beklemeyi
            // maskeliyordu — `[{wait -3540000},{wait 3600000}]` toplamda 60s görünüp
            // gerçekte bir saat koşuyordu. Artık her adım kendi gerçek maliyetiyle
            // ve NEGATİF DEĞER REDDEDİLEREK toplanıyor.
            // ⚠️ Adım sayısı tavanı, doğrulama turunda eklendi (4 Ağu 2026). Süre
            // tavanı tek başına yetmiyordu: mouse_move/scroll/gamepad/ui_click
            // adımlarının süresi yok, yani yüz binlercesi "0 ms" diye geçip her biri
            // için reflection + kuyruk + flush koşturuyordu. Süresi olmayan iş, işsiz
            // demek değil.
            if (steps.Count > MaxSequenceSteps)
                return new ErrorResponse(
                    $"Dizide {steps.Count} adım var, tavan {MaxSequenceSteps}. " +
                    "Süresiz adımlar da (mouse_move, scroll, gamepad, ui_click) iş yapıyor.");

            double totalMs = 0;
            for (int i = 0; i < steps.Count; i++)
            {
                // ⚠️ Bozuk adım artık burada REDDEDİLİYOR. Doğrulama turunda bulundu:
                // ön tarama `continue` ediyordu ama yürütme reddediyordu, yani
                // [{key W down}, 0] dizisi W'yi BASIP sonra duruyor ve hata cevabı
                // stillHeld/log taşımıyordu. Yamadan önceki LINQ hâli böyle bir
                // diziyi hiç çalıştırmadan reddediyordu; düzeltme bir gerileme
                // getirmişti.
                if (steps[i] is not JObject step)
                    return new ErrorResponse(
                        $"Adım {i} bir nesne değil; dizi çalıştırılmadı.");

                string stepType = step["type"]?.ToString()?.ToLowerInvariant();

                double stepMs;
                if (stepType == "wait")
                    stepMs = step["ms"]?.Value<double?>() ?? 0;
                else if (stepType == "key" || stepType == "mouse_button")
                    stepMs = step["duration_ms"]?.Value<double?>()
                             ?? ((step["state"]?.ToString()?.ToLowerInvariant() ?? "tap") == "tap" ? DefaultTapMs : 0);
                else
                    stepMs = 0; // süresiz adımlar: mouse_move, scroll, gamepad, ui_click

                if (stepMs < 0)
                    return new ErrorResponse(
                        $"Adım {i}: negatif süre ({stepMs} ms) geçersiz. Negatif değerler toplamı " +
                        "düşürüp tavanı anlamsız kılıyordu.");

                totalMs += stepMs;
            }

            if (totalMs > MaxSequenceSeconds * 1000)
                return new ErrorResponse(
                    $"Dizinin toplam süresi {totalMs / 1000:0.#}s, tavan {MaxSequenceSeconds}s " +
                    "(süresi verilmeyen tap adımları " + DefaultTapMs + " ms sayılır). " +
                    "Daha kısa dizilere böl — böylece aralarda ekran görüntüsü alıp ne olduğunu görebilirsin.");

            var log = new List<object>();

            for (int i = 0; i < steps.Count; i++)
            {
                if (steps[i] is not JObject step)
                    return new ErrorResponse($"Adım {i} bir nesne değil.");

                string type = step["type"]?.ToString()?.ToLowerInvariant();
                object result;

                // ⚠️ Bu try, denetimde eklendi (4 Ağu 2026). Öncesinde kurtarma
                // mesajı YALNIZ bir adım ErrorResponse döndürdüğünde çıkıyordu;
                // bir istisna (`{"type":"mouse_move","x":"sayi-degil"}` gibi) döngüden
                // KAÇIP dıştaki genel catch'e düşüyor ve kullanıcı "reset çağır"
                // yönlendirmesini hiç görmüyordu — üstelik tuş basılı kalmışken.
                try
                {
                switch (type)
                {
                    case "wait":
                    {
                        int waitMs = step["ms"]?.Value<int?>() ?? 0;
                        bool completed = await WaitFrames(waitMs);
                        result = completed
                            ? new SuccessResponse($"{waitMs}ms beklendi.")
                            : (object)new ErrorResponse(
                                $"Play mode {waitMs}ms dolmadan sona erdi; dizi burada durdu.");
                        break;
                    }
                    case "key":
                        result = await HandleKey(step);
                        break;
                    case "mouse_move":
                        result = HandleMouseMove(step);
                        break;
                    case "mouse_button":
                        result = await HandleMouseButton(step);
                        break;
                    case "scroll":
                        result = HandleScroll(step);
                        break;
                    case "gamepad":
                        result = HandleGamepad(step);
                        break;
                    case "ui_click":
                        result = HandleUiClick(new ToolParams(step), step);
                        break;
                    default:
                        result = new ErrorResponse(
                            $"Adım {i}: bilinmeyen type '{type}'. Geçerli: wait, key, mouse_move, " +
                            "mouse_button, scroll, gamepad, ui_click.");
                        break;
                }
                }
                catch (Exception ex)
                {
                    result = new ErrorResponse($"Adım {i} istisna fırlattı: {ex.Message}");
                }

                log.Add(new { step = i, type, result });

                // Bir adım patladıysa DURUYORUZ: yarısı uygulanmış bir dizi, hiç
                // uygulanmamış bir diziden daha yanıltıcıdır. Hangi girdilerin
                // basılı KALDIĞI cevabın içinde veriliyor — kullanıcıyı ayrı bir
                // describe turuna zorlamak, tam da panik anında fazladan adım demek.
                if (result is ErrorResponse)
                {
                    return new ErrorResponse(
                        $"Dizi {i}. adımda durdu. Basılı kalanları temizlemek için action='reset'.",
                        new
                        {
                            completedSteps = i,
                            stillHeld = InputSystemBridge.Describe(),
                            log,
                        });
                }
            }

            return new SuccessResponse($"{steps.Count} adım tamamlandı.", new
            {
                log,
                held = InputSystemBridge.CurrentlyHeldKeys().ToArray(),
            });
        }

        // ---------- Kareler arası bekleme ----------

        /// <summary>
        /// ExecuteCode.cs / RefreshUnity.cs desenini izler: EditorApplication.update
        /// aboneliği + TaskCompletionSource. Depoda editor coroutine yok.
        /// QueuePlayerLoopUpdate çağrısı, Editor odakta değilken bile oyun döngüsünün
        /// tıklamasını sağlıyor — aksi halde bekleme gerçek oyun karesi üretmezdi.
        /// </summary>
        /// <returns>
        /// true = süre doldu; false = play mode bekleme sırasında SONA ERDİ.
        /// ⚠️ Dönüş tipi denetimde `Task`'tan `Task&lt;bool&gt;`'a çevrildi
        /// (4 Ağu 2026). Öncesinde iptal `TrySetResult(false)` ile kaydediliyor ama
        /// tip düzeyinde okunamıyordu: kullanıcı oyunu 1. saniyede durdursa bile araç
        /// "10000ms beklendi" ve "3 adım tamamlandı" diyordu. Kaydedilen ama
        /// okunamayan bir sinyal, hiç olmayan bir sinyaldir.
        /// </returns>
        private static Task<bool> WaitFrames(int milliseconds)
        {
            if (milliseconds <= 0) return Task.FromResult(true);

            var tcs = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
            double deadline = EditorApplication.timeSinceStartup + (milliseconds / 1000.0);

            void Tick()
            {
                try
                {
                    if (tcs.Task.IsCompleted)
                    {
                        EditorApplication.update -= Tick;
                        return;
                    }

                    // Oyun beklerken durdurulduysa süresiz asılı kalmayalım.
                    if (!EditorApplication.isPlaying)
                    {
                        EditorApplication.update -= Tick;
                        tcs.TrySetResult(false);
                        return;
                    }

                    if (EditorApplication.timeSinceStartup >= deadline)
                    {
                        EditorApplication.update -= Tick;
                        tcs.TrySetResult(true);
                        return;
                    }

                    try { EditorApplication.QueuePlayerLoopUpdate(); } catch { }
                }
                catch (Exception ex)
                {
                    EditorApplication.update -= Tick;
                    tcs.TrySetException(ex);
                }
            }

            EditorApplication.update += Tick;
            try { EditorApplication.QueuePlayerLoopUpdate(); } catch { }
            return tcs.Task;
        }

        // ---------- Yardımcılar ----------

        /// <summary>
        /// Bu istek Input System olmadan da karşılanabilir mi? Yalnızca uGUI'ye
        /// dokunan bir dizi (her adımı ui_click) paket olmadan da çalışmalı.
        /// </summary>
        private static bool OnlyNeedsUgui(string action, JObject props)
        {
            if (action != "sequence") return false;
            if (props?["steps"] is not JArray steps || steps.Count == 0) return false;

            foreach (var s in steps)
            {
                if (s is not JObject step) return false;
                if (step["type"]?.ToString()?.ToLowerInvariant() != "ui_click") return false;
            }
            return true;
        }

        private static SuccessResponse Held(string message)
        {
            return new SuccessResponse(message, new
            {
                heldKeys = InputSystemBridge.CurrentlyHeldKeys().ToArray(),
            });
        }

        /// <summary>
        /// ⚠️ Denetimde değişti (4 Ağu 2026): eskiden bozuk bir JSON dizesi sessizce
        /// yutuluyor ve dış istek nesnesine düşülüyordu. Sonuç, kullanıcıyı YANLIŞ
        /// yere bakmaya yollayan bir hata mesajıydı — "'key' gerekli" diyordu, oysa
        /// key verilmişti, sadece JSON'u bozuktu. Artık ayrıştırma hatası adıyla
        /// çağırana ulaşıyor.
        /// </summary>
        private static JObject ReadProperties(JObject @params, out string parseError)
        {
            parseError = null;
            var raw = @params["properties"];
            if (raw == null) return @params;
            if (raw is JObject obj) return obj;

            // Python tarafı properties'i JSON dizesi olarak da kabul ediyor.
            if (raw.Type == JTokenType.String)
            {
                try { return JObject.Parse(raw.ToString()); }
                catch (Exception ex)
                {
                    parseError = $"'properties' geçerli bir JSON nesnesi değil: {ex.Message}";
                    return @params;
                }
            }
            return @params;
        }

        private static List<string> ReadStringList(JObject props, string pluralKey, string singularKey)
        {
            var result = new List<string>();
            if (props == null) return result;

            if (pluralKey != null && props[pluralKey] is JArray array)
                result.AddRange(array.Select(t => t.ToString()).Where(s => !string.IsNullOrWhiteSpace(s)));

            if (pluralKey != null && props[pluralKey]?.Type == JTokenType.String)
                result.Add(props[pluralKey].ToString());

            if (singularKey != null && props[singularKey] != null)
            {
                var single = props[singularKey].ToString();
                if (!string.IsNullOrWhiteSpace(single)) result.Add(single);
            }

            return result.Distinct(StringComparer.OrdinalIgnoreCase).ToList();
        }

        private static Vector2? ReadVector2(JObject props, string xKey, string yKey)
        {
            if (props == null) return null;
            var x = props[xKey]?.Value<float?>();
            var y = props[yKey]?.Value<float?>();
            if (x == null && y == null) return null;
            return new Vector2(x ?? 0f, y ?? 0f);
        }

        private static Type FindUiType(string fullName)
        {
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    var t = asm.GetType(fullName, false);
                    if (t != null) return t;
                }
                catch
                {
                    // Yansımada patlayan assembly taramayı durdurmasın.
                }
            }
            return null;
        }

        /// <summary>
        /// Project Settings > Player > Active Input Handling.
        /// ⚠️ Bu, sanal cihaz olaylarının görülüp görülmeyeceğini belirleyen tek
        /// şey DEĞİL — doğrulama turunda düzeltildi (4 Ağu 2026), bu yorum önce
        /// "belirleyen tek ayar" diyordu. Ayar yalnız hangi arka uçların AÇIK
        /// olduğunu söylüyor; olayı görecek olan şey oyun kodunun hangi API'yi
        /// çağırdığı ve onu buradan okumuyoruz. "Both" ayarında bu rapor, girdisi
        /// çalışan bir projeyle çalışmayan bir projede AYNI çıkar.
        /// </summary>
        private static object DescribeActiveInputHandling()
        {
            // 0 = yalnız eski Input Manager, 1 = yalnız Input System, 2 = ikisi.
            // activeInputHandler'ın public bir API'si yok; ProjectSettings.asset'i
            // serileştirilmiş nesne olarak okumak bunun bilinen tek yolu.
            try
            {
                var settings = AssetDatabase
                    .LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset")
                    .FirstOrDefault();
                if (settings == null)
                {
                    return new
                    {
                        note = "ProjectSettings.asset okunamadı; karar için Project Settings > Player'a bak.",
                    };
                }

                var so = new SerializedObject(settings);
                var prop = so.FindProperty("activeInputHandler");
                int value = prop?.intValue ?? -1;
                return new
                {
                    value,
                    meaning = value switch
                    {
                        0 => "Yalnız ESKİ Input Manager. Sanal cihaz olayları oyun tarafından GÖRÜLMEZ.",
                        1 => "Yalnız Input System. Sanal cihaz olayları görülür.",
                        2 => "İkisi birden. Sanal cihaz olayları yalnız Input System API'siyle yazılmış kod tarafından görülür; Input.GetKey yazan kod GÖRMEZ.",
                        _ => "Okunamadı.",
                    },
                };
            }
            catch (Exception ex)
            {
                return new { error = ex.Message };
            }
        }
    }
}
