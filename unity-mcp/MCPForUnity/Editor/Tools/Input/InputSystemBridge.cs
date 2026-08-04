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

        // Basılı tutulan tuşlar. KeyboardState TÜM tuş kümesini taşıdığı için her
        // olayda kümenin tamamı yeniden gönderilmek zorunda; tek tuş göndermek
        // diğerlerini sessizce bırakırdı.
        private static readonly HashSet<string> HeldKeys = new(StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> HeldMouseButtons = new(StringComparer.OrdinalIgnoreCase);
        private static readonly HashSet<string> HeldGamepadButtons = new(StringComparer.OrdinalIgnoreCase);
        private static Vector2 _mousePosition;
        private static Vector2 _leftStick;
        private static Vector2 _rightStick;

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
                _gamepadButtonType = FindType("UnityEngine.InputSystem.LowLevel.GamepadButton")
                                     ?? FindType("UnityEngine.InputSystem.LowLevel.GamepadButton, Unity.InputSystem");

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
                    return $"'{name}' kaldırılamadı: {ex.InnerException?.Message ?? ex.Message}";
                }
            }

            // Cihaz zaten yoksa da başarı: reset'in sözleşmesi "sonrasında temiz
            // olsun", "bir şey sildim" değil.
            ResetCachedState();
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

            if (down != null)
            {
                foreach (var k in down)
                {
                    if (!TryParseEnum(_keyType, k, out _, out var err)) return err;
                    HeldKeys.Add(k);
                }
            }
            if (up != null)
            {
                foreach (var k in up)
                {
                    if (!TryParseEnum(_keyType, k, out _, out var err)) return err;
                    HeldKeys.RemoveWhere(h => string.Equals(h, k, StringComparison.OrdinalIgnoreCase));
                }
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

            if (buttonsDown != null)
            {
                foreach (var b in buttonsDown)
                {
                    if (!TryParseEnum(_mouseButtonType, b, out _, out var err)) return err;
                    HeldMouseButtons.Add(b);
                }
            }
            if (buttonsUp != null)
            {
                foreach (var b in buttonsUp)
                {
                    if (!TryParseEnum(_mouseButtonType, b, out _, out var err)) return err;
                    HeldMouseButtons.RemoveWhere(h => string.Equals(h, b, StringComparison.OrdinalIgnoreCase));
                }
            }

            if (absolutePosition.HasValue) _mousePosition = absolutePosition.Value;
            else if (delta.HasValue) _mousePosition += delta.Value;

            var device = EnsureDevice("Mouse", MouseDeviceName, out var deviceError);
            if (device == null) return deviceError;

            object state;
            try
            {
                state = Activator.CreateInstance(_mouseStateType);
                SetFieldIfPresent(_mouseStateType, state, "position", _mousePosition);
                SetFieldIfPresent(_mouseStateType, state, "delta", delta ?? Vector2.zero);
                SetFieldIfPresent(_mouseStateType, state, "scroll", scroll ?? Vector2.zero);

                // WithButton bir KOPYA döndürüyor (struct); dönen değeri geri almazsak
                // düğme basımı sessizce kaybolur.
                var withButton = _mouseStateType.GetMethod("WithButton");
                if (withButton != null)
                {
                    foreach (var held in HeldMouseButtons)
                    {
                        if (!TryParseEnum(_mouseButtonType, held, out var value, out var err)) return err;
                        state = withButton.Invoke(state, new[] { value, (object)true });
                    }
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

            if (buttonsDown != null)
            {
                foreach (var b in buttonsDown)
                {
                    if (!TryParseEnum(_gamepadButtonType, b, out _, out var err)) return err;
                    HeldGamepadButtons.Add(b);
                }
            }
            if (buttonsUp != null)
            {
                foreach (var b in buttonsUp)
                {
                    if (!TryParseEnum(_gamepadButtonType, b, out _, out var err)) return err;
                    HeldGamepadButtons.RemoveWhere(h => string.Equals(h, b, StringComparison.OrdinalIgnoreCase));
                }
            }

            if (leftStick.HasValue) _leftStick = leftStick.Value;
            if (rightStick.HasValue) _rightStick = rightStick.Value;

            var device = EnsureDevice("Gamepad", GamepadDeviceName, out var deviceError);
            if (device == null) return deviceError;

            object state;
            try
            {
                state = Activator.CreateInstance(_gamepadStateType);
                SetFieldIfPresent(_gamepadStateType, state, "leftStick", _leftStick);
                SetFieldIfPresent(_gamepadStateType, state, "rightStick", _rightStick);
                if (leftTrigger.HasValue) SetFieldIfPresent(_gamepadStateType, state, "leftTrigger", leftTrigger.Value);
                if (rightTrigger.HasValue) SetFieldIfPresent(_gamepadStateType, state, "rightTrigger", rightTrigger.Value);

                var withButton = _gamepadStateType.GetMethod("WithButton");
                if (withButton != null)
                {
                    foreach (var held in HeldGamepadButtons)
                    {
                        if (!TryParseEnum(_gamepadButtonType, held, out var value, out var err)) return err;
                        state = withButton.Invoke(state, new[] { value, (object)true });
                    }
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

        private static void SetFieldIfPresent(Type type, object boxedStruct, string fieldName, object value)
        {
            var field = type.GetField(fieldName, BindingFlags.Public | BindingFlags.Instance);
            if (field == null) return;

            // Alan tipi Vector2 yerine iç bir tip olabilir; dönüştüremezsek sessizce
            // atlamak yerine atlıyoruz ama Describe() alanın varlığını raporluyor.
            if (value != null && !field.FieldType.IsInstanceOfType(value))
            {
                try { value = Convert.ChangeType(value, field.FieldType); }
                catch { return; }
            }
            field.SetValue(boxedStruct, value);
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
                resolved = new
                {
                    inputSystem = _inputSystemType?.FullName,
                    keyEnum = _keyType?.FullName,
                    keyboardState = _keyboardStateType?.FullName,
                    mouseState = _mouseStateType?.FullName,
                    gamepadState = _gamepadStateType?.FullName,
                    addDevice = _addDevice?.ToString(),
                    queueStateEvent = _queueStateEventOpen?.ToString(),
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
            };
        }
    }
}
