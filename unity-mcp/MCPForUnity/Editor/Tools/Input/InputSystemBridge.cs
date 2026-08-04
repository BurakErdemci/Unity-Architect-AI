using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using UnityEngine;

namespace MCPForUnity.Editor.Tools.Input
{
    /// <summary>
    /// Input System paketine REFLECTION ile bağlanan katman.
    ///
    /// Neden reflection: MCPForUnity.Editor.asmdef hiçbir isteğe bağlı pakete
    /// referans vermiyor (Cinemachine de aynı sebeple UnityTypeResolver üzerinden
    /// çözülüyor, bkz Tools/Cameras/CameraHelpers.cs). asmdef'e "Unity.InputSystem"
    /// eklemek, paketi olmayan projelerde derlemeyi riske atardı; bu repoda derleme
    /// hatası MCP köprüsünün HİÇ kalkmaması demek, yani yeni bir aracın maliyeti
    /// ürünün tamamı olurdu. Paket yoksa Available=false döner ve araç sebebini söyler.
    ///
    /// Neden sanal cihaz: Unity'nin eski UnityEngine.Input API'si salt okunurdur,
    /// dışarıdan beslenemez. Input System'in QueueStateEvent'i ise olayı Unity
    /// sürecinin İÇİNDEN üretir — pencere odağı gerektirmez.
    /// ⚠️ Bunun sınırı: oyun kodu hâlâ Input.GetKey yazıyorsa bu olayları GÖRMEZ.
    /// Describe() tam da bunu ölçülebilir kılmak için var.
    /// </summary>
    internal static class InputSystemBridge
    {
        internal const string KeyboardDeviceName = "MCPVirtualKeyboard";
        internal const string MouseDeviceName = "MCPVirtualMouse";
        internal const string GamepadDeviceName = "MCPVirtualGamepad";

        private static bool _resolved;
        private static string _unavailableReason;

        private static Type _inputSystemType;
        private static Type _keyType;
        private static Type _keyboardStateType;
        private static Type _mouseStateType;
        private static Type _mouseButtonType;
        private static Type _gamepadStateType;
        private static Type _gamepadButtonType;

        private static MethodInfo _addDevice;
        private static MethodInfo _removeDevice;
        private static MethodInfo _queueStateEventOpen;
        private static MethodInfo _update;
        private static PropertyInfo _devicesProperty;
        private static MethodInfo _mouseWithButton;
        private static MethodInfo _gamepadWithButton;

        // Basılı tutulan tuşlar. KeyboardState TÜM tuş kümesini taşıdığı için her
        // olayda kümenin tamamı yeniden gönderilmek zorunda; tek tuş göndermek
        // diğerlerini sessizce bırakırdı.
        private static readonly HashSet<string> HeldKeys = new(StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> HeldMouseButtons = new(StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> HeldGamepadButtons = new(StringComparer.OrdinalIgnoreCase);
        private static Vector2 _mousePosition;
        private static Vector2 _leftStick;
        private static Vector2 _rightStick;

        // Tetikler de önbelleklenmek ZORUNDA. Denetimde ölçüldü (4 Ağu 2026): her
        // çağrı sıfırlanmış bir GamepadState kurduğu için, yalnız çubuğu güncelleyen
        // ikinci bir çağrı basılı duran tetiği SESSİZCE bırakıyordu — kullanıcı
        // "yalnız yönü değiştirdim" derken gaz/ateş düşüyordu.
        private static float _leftTrigger;
        private static float _rightTrigger;

        internal static bool Available
        {
            get
            {
                Resolve();
                return _unavailableReason == null;
            }
        }

        internal static string UnavailableReason
        {
            get
            {
                Resolve();
                return _unavailableReason;
            }
        }

        /// <summary>
        /// Domain reload sanal cihazları ve basılı tuş kümesini uçurur. Bunu
        /// yakalayıp durumu sıfırlamazsak, var olmayan bir cihaza olay göndermeye
        /// çalışıp anlaşılmaz hatalar üretirdik.
        /// </summary>
        internal static void ResetCachedState()
        {
            HeldKeys.Clear();
            HeldMouseButtons.Clear();
            HeldGamepadButtons.Clear();
            _mousePosition = Vector2.zero;
            _leftStick = Vector2.zero;
            _rightStick = Vector2.zero;
            _leftTrigger = 0f;
            _rightTrigger = 0f;
        }

        /// <summary>
        /// Bir isim listesinin TAMAMINI, hiçbir şeye dokunmadan doğrular.
        /// Denetimde ölçüldü (4 Ağu 2026): doğrulama ve mutasyon aynı döngüdeyken
        /// `keys=['W','gecersiz']` hata döndürüyor ama W basılı kümede KALIYOR ve
        /// bir sonraki başarılı çağrıda basılıyordu — reddedilen bir isteğin girdisi
        /// başka bir isteğin üstünde beliriyordu. Önce hepsini doğrula, sonra yaz.
        /// </summary>
        private static bool ValidateAll(Type enumType, IEnumerable<string> names, out string error)
        {
            error = null;
            if (names == null) return true;
            foreach (var n in names)
            {
                if (!TryParseEnum(enumType, n, out _, out error)) return false;
            }
            return true;
        }

        private static void Resolve()
        {
            if (_resolved) return;
            _resolved = true;

            try
            {
                _inputSystemType = FindType("UnityEngine.InputSystem.InputSystem");
                if (_inputSystemType == null)
                {
                    _unavailableReason =
                        "Input System paketi (com.unity.inputsystem) bu projede bulunamadı. " +
                        "Package Manager'dan kurulup Project Settings > Player > Active Input Handling " +
                        "'Input System Package' ya da 'Both' yapılmalı.";
                    return;
                }

                _keyType = FindType("UnityEngine.InputSystem.Key");
                _keyboardStateType = FindType("UnityEngine.InputSystem.LowLevel.KeyboardState");
                _mouseStateType = FindType("UnityEngine.InputSystem.LowLevel.MouseState");
                _mouseButtonType = FindType("UnityEngine.InputSystem.LowLevel.MouseButton");
                _gamepadStateType = FindType("UnityEngine.InputSystem.LowLevel.GamepadState");
                // (Denetimde ölü bir `?? FindType("...,Unity.InputSystem")` yedeği vardı:
                // FindType zaten Type.GetType ile assembly-nitelikli adı çözüyor, ikinci
                // çağrı hiçbir zaman ek bilgi getiremezdi. Kaldırıldı.)
                _gamepadButtonType = FindType("UnityEngine.InputSystem.LowLevel.GamepadButton");

                var statics = _inputSystemType.GetMethods(BindingFlags.Public | BindingFlags.Static);

                _addDevice = statics.FirstOrDefault(m =>
                    m.Name == "AddDevice"
                    && !m.IsGenericMethod
                    && m.GetParameters().Length >= 1
                    && m.GetParameters()[0].ParameterType == typeof(string));

                _removeDevice = statics.FirstOrDefault(m =>
                    m.Name == "RemoveDevice" && m.GetParameters().Length == 1);

                _queueStateEventOpen = statics.FirstOrDefault(m =>
                    m.Name == "QueueStateEvent"
                    && m.IsGenericMethodDefinition
                    && m.GetParameters().Length == 3);

                _update = statics.FirstOrDefault(m =>
                    m.Name == "Update" && m.GetParameters().Length == 0);

                _devicesProperty = _inputSystemType.GetProperty("devices",
                    BindingFlags.Public | BindingFlags.Static);

                var missing = new List<string>();
                if (_keyType == null) missing.Add("Key");
                if (_keyboardStateType == null) missing.Add("LowLevel.KeyboardState");
                if (_mouseStateType == null) missing.Add("LowLevel.MouseState");
                if (_mouseButtonType == null) missing.Add("LowLevel.MouseButton");
                if (_gamepadStateType == null) missing.Add("LowLevel.GamepadState");
                if (_gamepadButtonType == null) missing.Add("LowLevel.GamepadButton");
                if (_addDevice == null) missing.Add("InputSystem.AddDevice(string,...)");
                if (_removeDevice == null) missing.Add("InputSystem.RemoveDevice(...)");
                if (_queueStateEventOpen == null) missing.Add("InputSystem.QueueStateEvent<T>(device,state,time)");
                if (_update == null) missing.Add("InputSystem.Update()");
                if (_devicesProperty == null) missing.Add("InputSystem.devices");

                // ⚠️ Bu blok denetimde eklendi (4 Ağu 2026). Öncesinde `missing` yalnız
                // TİPLERİ ve birkaç statik üyeyi kontrol ediyordu; kodun asıl bağımlı
                // olduğu ALANLAR ve WithButton hiç bakılmıyordu. Sonuç: bir sürüm
                // farkında Available=true kalıyor ve araç hiçbir şey yapmadan
                // "başarılı" diyordu. Bağımlı olunan her üye burada olmak zorunda.
                _mouseWithButton = _mouseStateType?.GetMethod("WithButton");
                _gamepadWithButton = _gamepadStateType?.GetMethod("WithButton");
                if (_mouseStateType != null && _mouseWithButton == null) missing.Add("MouseState.WithButton");
                if (_gamepadStateType != null && _gamepadWithButton == null) missing.Add("GamepadState.WithButton");

                foreach (var f in new[] { "position", "delta", "scroll" })
                    if (_mouseStateType != null && _mouseStateType.GetField(f, BindingFlags.Public | BindingFlags.Instance) == null)
                        missing.Add($"MouseState.{f}");
                foreach (var f in new[] { "leftStick", "rightStick", "leftTrigger", "rightTrigger" })
                    if (_gamepadStateType != null && _gamepadStateType.GetField(f, BindingFlags.Public | BindingFlags.Instance) == null)
                        missing.Add($"GamepadState.{f}");

                if (missing.Count > 0)
                {
                    // Paket var ama beklenen API şekli yok — büyük olasılıkla sürüm farkı.
                    // Sessizce yanlış davranmaktansa neyin bulunamadığını ADIYLA söylüyoruz.
                    _unavailableReason =
                        "Input System paketi bulundu ama beklenen API üyeleri çözülemedi: "
                        + string.Join(", ", missing)
                        + ". Paket sürümü desteklenmiyor olabilir.";
                }
            }
            catch (Exception ex)
            {
                _unavailableReason = $"Input System çözümlemesi başarısız: {ex.Message}";
            }
        }

        private static Type FindType(string fullName)
        {
            var t = Type.GetType(fullName);
            if (t != null) return t;

            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    t = asm.GetType(fullName, false);
                    if (t != null) return t;
                }
                catch
                {
                    // Bazı assembly'ler yansıma sırasında patlar; taramayı durdurmaz.
                }
            }
            return null;
        }

        // ---------- Cihaz yaşam döngüsü ----------

        private static object FindDeviceByName(string name)
        {
            if (_devicesProperty?.GetValue(null) is not IEnumerable devices) return null;

            foreach (var device in devices)
            {
                if (device == null) continue;
                var nameProp = device.GetType().GetProperty("name");
                if (nameProp?.GetValue(device) as string == name) return device;
            }
            return null;
        }

        private static object EnsureDevice(string layout, string deviceName, out string error)
        {
            error = null;
            var existing = FindDeviceByName(deviceName);
            if (existing != null) return existing;

            try
            {
                var parameters = _addDevice.GetParameters();
                var args = new object[parameters.Length];
                args[0] = layout;
                if (parameters.Length > 1) args[1] = deviceName;
                for (int i = 2; i < parameters.Length; i++) args[i] = null;

                var device = _addDevice.Invoke(null, args);
                if (device == null)
                {
                    error = $"'{layout}' düzeninde sanal cihaz oluşturulamadı.";
                }
                return device;
            }
            catch (Exception ex)
            {
                error = $"Sanal cihaz eklenemedi ({layout}): {ex.InnerException?.Message ?? ex.Message}";
                return null;
            }
        }

        internal static string RemoveAllVirtualDevices()
        {
            Resolve();
            if (_unavailableReason != null) return _unavailableReason;

            var failures = new List<string>();
            foreach (var name in new[] { KeyboardDeviceName, MouseDeviceName, GamepadDeviceName })
            {
                var device = FindDeviceByName(name);
                if (device == null) continue;
                try
                {
                    _removeDevice.Invoke(null, new[] { device });
                }
                catch (Exception ex)
                {
                    failures.Add($"{name}: {ex.InnerException?.Message ?? ex.Message}");
                }
            }

            // ⚠️ Önbellek, bir cihaz kaldırma BAŞARISIZ olsa da temizleniyor.
            // Denetimde ölçüldü (4 Ağu 2026): eski hâli ilk hatada erken dönüyordu,
            // yani klavye silinmiş ama HeldKeys'te W duruyor olabiliyordu — sonraki
            // çağrı klavyeyi yeniden yaratıp W'yi TEKRAR basıyordu. reset'in tek işi
            // temiz bir duruma dönmek; kısmen başarısız olsa bile önbellek yalan
            // söylememeli. Hata yine de çağırana bildiriliyor.
            ResetCachedState();

            if (failures.Count > 0)
            {
                return "Sanal cihazların bir kısmı kaldırılamadı (" + string.Join("; ", failures)
                       + "). Basılı tuş önbelleği yine de temizlendi; kalan cihaz için Unity'yi "
                       + "play mode'dan çıkarıp tekrar dene.";
            }
            return null;
        }

        private static void Flush()
        {
            _update.Invoke(null, Array.Empty<object>());
        }

        private static string QueueState(object device, Type stateType, object boxedState)
        {
            try
            {
                var closed = _queueStateEventOpen.MakeGenericMethod(stateType);
                closed.Invoke(null, new[] { device, boxedState, (object)(-1.0) });
                Flush();
                return null;
            }
            catch (Exception ex)
            {
                return $"Olay kuyruğa alınamadı: {ex.InnerException?.Message ?? ex.Message}";
            }
        }

        // ---------- Klavye ----------

        internal static string[] KnownKeyNames()
        {
            Resolve();
            return _keyType == null ? Array.Empty<string>() : Enum.GetNames(_keyType);
        }

        internal static string SetKeys(IEnumerable<string> down, IEnumerable<string> up)
        {
            Resolve();
            if (_unavailableReason != null) return _unavailableReason;

            if (!ValidateAll(_keyType, down, out var validationError)) return validationError;
            if (!ValidateAll(_keyType, up, out validationError)) return validationError;

            if (down != null)
            {
                foreach (var k in down) HeldKeys.Add(k);
            }
            if (up != null)
            {
                foreach (var k in up)
                    HeldKeys.RemoveWhere(h => string.Equals(h, k, StringComparison.OrdinalIgnoreCase));
            }

            var device = EnsureDevice("Keyboard", KeyboardDeviceName, out var deviceError);
            if (device == null) return deviceError;

            // KeyboardState(params Key[]) — basılı olan TÜM tuşlar her seferinde
            // yeniden gönderiliyor, çünkü state tam durumdur, fark değil.
            var keyArray = Array.CreateInstance(_keyType, HeldKeys.Count);
            int i = 0;
            foreach (var held in HeldKeys)
            {
                if (!TryParseEnum(_keyType, held, out var value, out var err)) return err;
                keyArray.SetValue(value, i++);
            }

            object state;
            try
            {
                state = Activator.CreateInstance(_keyboardStateType, new object[] { keyArray });
            }
            catch (Exception ex)
            {
                return $"KeyboardState oluşturulamadı: {ex.InnerException?.Message ?? ex.Message}";
            }

            return QueueState(device, _keyboardStateType, state);
        }

        internal static IReadOnlyCollection<string> CurrentlyHeldKeys() => HeldKeys;

        // ---------- Fare ----------

        internal static string SetMouse(Vector2? absolutePosition, Vector2? delta, Vector2? scroll,
                                        IEnumerable<string> buttonsDown, IEnumerable<string> buttonsUp)
        {
            Resolve();
            if (_unavailableReason != null) return _unavailableReason;

            if (!ValidateAll(_mouseButtonType, buttonsDown, out var validationError)) return validationError;
            if (!ValidateAll(_mouseButtonType, buttonsUp, out validationError)) return validationError;

            if (buttonsDown != null)
            {
                foreach (var b in buttonsDown) HeldMouseButtons.Add(b);
            }
            if (buttonsUp != null)
            {
                foreach (var b in buttonsUp)
                    HeldMouseButtons.RemoveWhere(h => string.Equals(h, b, StringComparison.OrdinalIgnoreCase));
            }

            if (absolutePosition.HasValue) _mousePosition = absolutePosition.Value;
            else if (delta.HasValue) _mousePosition += delta.Value;

            var device = EnsureDevice("Mouse", MouseDeviceName, out var deviceError);
            if (device == null) return deviceError;

            object state;
            try
            {
                state = Activator.CreateInstance(_mouseStateType);
                if (!SetField(_mouseStateType, ref state, "position", _mousePosition, out var fieldError)) return fieldError;
                if (!SetField(_mouseStateType, ref state, "delta", delta ?? Vector2.zero, out fieldError)) return fieldError;
                if (!SetField(_mouseStateType, ref state, "scroll", scroll ?? Vector2.zero, out fieldError)) return fieldError;

                // WithButton bir KOPYA döndürüyor (struct); dönen değeri geri almazsak
                // düğme basımı sessizce kaybolur. Varlığı Resolve()'da doğrulanıyor,
                // burada null olması bir programlama hatasıdır — sessizce atlamak yok.
                foreach (var held in HeldMouseButtons)
                {
                    if (!TryParseEnum(_mouseButtonType, held, out var value, out var err)) return err;
                    state = _mouseWithButton.Invoke(state, new[] { value, (object)true });
                }
            }
            catch (Exception ex)
            {
                return $"MouseState oluşturulamadı: {ex.InnerException?.Message ?? ex.Message}";
            }

            return QueueState(device, _mouseStateType, state);
        }

        internal static string[] KnownMouseButtons()
        {
            Resolve();
            return _mouseButtonType == null ? Array.Empty<string>() : Enum.GetNames(_mouseButtonType);
        }

        // ---------- Gamepad ----------

        internal static string SetGamepad(Vector2? leftStick, Vector2? rightStick,
                                          float? leftTrigger, float? rightTrigger,
                                          IEnumerable<string> buttonsDown, IEnumerable<string> buttonsUp)
        {
            Resolve();
            if (_unavailableReason != null) return _unavailableReason;

            if (!ValidateAll(_gamepadButtonType, buttonsDown, out var validationError)) return validationError;
            if (!ValidateAll(_gamepadButtonType, buttonsUp, out validationError)) return validationError;

            if (buttonsDown != null)
            {
                foreach (var b in buttonsDown) HeldGamepadButtons.Add(b);
            }
            if (buttonsUp != null)
            {
                foreach (var b in buttonsUp)
                    HeldGamepadButtons.RemoveWhere(h => string.Equals(h, b, StringComparison.OrdinalIgnoreCase));
            }

            if (leftStick.HasValue) _leftStick = leftStick.Value;
            if (rightStick.HasValue) _rightStick = rightStick.Value;
            if (leftTrigger.HasValue) _leftTrigger = leftTrigger.Value;
            if (rightTrigger.HasValue) _rightTrigger = rightTrigger.Value;

            var device = EnsureDevice("Gamepad", GamepadDeviceName, out var deviceError);
            if (device == null) return deviceError;

            object state;
            try
            {
                state = Activator.CreateInstance(_gamepadStateType);
                // Dördü de HER olayda yazılıyor: state bir fark değil tam durumdur,
                // atlanan alan sıfırlanmış olarak gider.
                if (!SetField(_gamepadStateType, ref state, "leftStick", _leftStick, out var fieldError)) return fieldError;
                if (!SetField(_gamepadStateType, ref state, "rightStick", _rightStick, out fieldError)) return fieldError;
                if (!SetField(_gamepadStateType, ref state, "leftTrigger", _leftTrigger, out fieldError)) return fieldError;
                if (!SetField(_gamepadStateType, ref state, "rightTrigger", _rightTrigger, out fieldError)) return fieldError;

                foreach (var held in HeldGamepadButtons)
                {
                    if (!TryParseEnum(_gamepadButtonType, held, out var value, out var err)) return err;
                    state = _gamepadWithButton.Invoke(state, new[] { value, (object)true });
                }
            }
            catch (Exception ex)
            {
                return $"GamepadState oluşturulamadı: {ex.InnerException?.Message ?? ex.Message}";
            }

            return QueueState(device, _gamepadStateType, state);
        }

        internal static string[] KnownGamepadButtons()
        {
            Resolve();
            return _gamepadButtonType == null ? Array.Empty<string>() : Enum.GetNames(_gamepadButtonType);
        }

        // ---------- Ortak ----------

        /// <summary>
        /// Bir state alanını yazar; YAZAMAZSA sessizce dönmez, hata döndürür.
        ///
        /// Denetimde ölçüldü (4 Ağu 2026): eski hâli alanı bulamayınca sessizce
        /// dönüyordu. Sonuç, aracın verebileceği en kötü cevaptı — "fare (500,300)'e
        /// taşındı" der, fare (0,0)'dadır, ve Describe() de `available: true` derdi.
        /// Bir paket sürümünde alan yeniden adlandırılırsa arıza artık ADIYLA görünür.
        /// </summary>
        private static bool SetField(Type type, ref object boxedStruct, string fieldName,
                                     object value, out string error)
        {
            error = null;
            var field = type.GetField(fieldName, BindingFlags.Public | BindingFlags.Instance);
            if (field == null)
            {
                error = $"Input System'in '{type.Name}' yapısında '{fieldName}' alanı bulunamadı. "
                        + "Paket sürümü desteklenmiyor olabilir; action='describe' çözülen üyeleri listeler.";
                return false;
            }

            if (value != null && !field.FieldType.IsInstanceOfType(value))
            {
                try { value = Convert.ChangeType(value, field.FieldType); }
                catch (Exception ex)
                {
                    error = $"'{type.Name}.{fieldName}' alanına yazılamadı "
                            + $"({value.GetType().Name} → {field.FieldType.Name}): {ex.Message}";
                    return false;
                }
            }

            field.SetValue(boxedStruct, value);
            return true;
        }

        private static bool TryParseEnum(Type enumType, string name, out object value, out string error)
        {
            value = null;
            error = null;
            if (enumType == null)
            {
                error = "Input System enum tipi çözülemedi.";
                return false;
            }
            if (string.IsNullOrWhiteSpace(name))
            {
                error = "Boş isim geçersiz.";
                return false;
            }

            try
            {
                value = Enum.Parse(enumType, name.Trim(), true);
                return true;
            }
            catch
            {
                var names = Enum.GetNames(enumType);
                var suggestion = names.FirstOrDefault(n =>
                    n.StartsWith(name.Trim(), StringComparison.OrdinalIgnoreCase));
                error = $"'{name}' geçerli bir {enumType.Name} değeri değil."
                        + (suggestion != null ? $" Bunu mu demek istedin: '{suggestion}'?" : "")
                        + $" Geçerli değerleri görmek için action='describe' çağır.";
                return false;
            }
        }

        /// <summary>
        /// Reflection'ın neyi çözüp neyi çözemediğini raporlar. Bu aracın kendi
        /// kendini sınaması: bir Unity/paket sürümünde imza değişirse arıza
        /// "çalışmıyor" diye değil, çözülemeyen üyenin ADIYLA görünür.
        /// </summary>
        internal static object Describe()
        {
            Resolve();
            return new
            {
                available = _unavailableReason == null,
                reason = _unavailableReason,
                // ⚠️ Bu blok denetimde genişletildi (4 Ağu 2026). Öncesi yalnız beş tip
                // ve iki metot listeliyordu, oysa yorumlar "değişen üyeyi ADIYLA
                // gösterir" diye söz veriyordu — araç kendi vaadini tutmuyordu ve
                // model bu teşhisi İLK çağırması söylenen şey.
                resolved = new
                {
                    inputSystem = _inputSystemType?.FullName,
                    keyEnum = _keyType?.FullName,
                    keyboardState = _keyboardStateType?.FullName,
                    mouseState = _mouseStateType?.FullName,
                    mouseButtonEnum = _mouseButtonType?.FullName,
                    gamepadState = _gamepadStateType?.FullName,
                    gamepadButtonEnum = _gamepadButtonType?.FullName,
                    addDevice = _addDevice?.ToString(),
                    removeDevice = _removeDevice?.ToString(),
                    queueStateEvent = _queueStateEventOpen?.ToString(),
                    update = _update?.ToString(),
                    devices = _devicesProperty?.ToString(),
                    mouseWithButton = _mouseWithButton?.ToString(),
                    gamepadWithButton = _gamepadWithButton?.ToString(),
                },
                stateFields = new
                {
                    mouse = DescribeFields(_mouseStateType, "position", "delta", "scroll"),
                    gamepad = DescribeFields(_gamepadStateType, "leftStick", "rightStick", "leftTrigger", "rightTrigger"),
                },
                virtualDevices = new
                {
                    keyboard = FindDeviceByName(KeyboardDeviceName) != null,
                    mouse = FindDeviceByName(MouseDeviceName) != null,
                    gamepad = FindDeviceByName(GamepadDeviceName) != null,
                },
                held = new
                {
                    keys = HeldKeys.ToArray(),
                    mouseButtons = HeldMouseButtons.ToArray(),
                    gamepadButtons = HeldGamepadButtons.ToArray(),
                },
                mousePosition = new { x = _mousePosition.x, y = _mousePosition.y },
                // Tetikler de raporlanıyor: önbelleklendikleri için "neden hâlâ gaz
                // veriyor" sorusunun cevabı burada görünmeli.
                triggers = new { left = _leftTrigger, right = _rightTrigger },
                sticks = new
                {
                    left = new { x = _leftStick.x, y = _leftStick.y },
                    right = new { x = _rightStick.x, y = _rightStick.y },
                },
            };
        }

        /// <summary>Bir state tipinde beklenen alanların gerçekten var olup olmadığını listeler.</summary>
        private static Dictionary<string, string> DescribeFields(Type type, params string[] fieldNames)
        {
            var result = new Dictionary<string, string>();
            foreach (var name in fieldNames)
            {
                var field = type?.GetField(name, BindingFlags.Public | BindingFlags.Instance);
                result[name] = field == null ? "YOK" : field.FieldType.Name;
            }
            return result;
        }
    }
}
