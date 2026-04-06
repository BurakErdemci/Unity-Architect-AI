def oauth_success_page(user_id: int, username: str, email: str, avatar: str, session_token: str) -> str:
    return f"""<!DOCTYPE html><html><head><title>Giriş Başarılı</title></head>
<body style="background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;">
<div style="text-align:center;">
<h2>Giriş başarılı!</h2>
<p>Bu pencere kapanacak...</p>
</div>
<script>
  const data = {{ user_id: {user_id}, username: "{username}", email: "{email}", avatar: "{avatar}", session_token: "{session_token}" }};
  if (window.opener) {{
    window.opener.postMessage({{ type: "oauth-success", ...data }}, "*");
    setTimeout(() => window.close(), 1000);
  }} else {{
    document.querySelector('p').textContent = 'Pencereyi kapatabilirsiniz.';
  }}
</script></body></html>"""


def oauth_error_page(error: str) -> str:
    safe_error = error.replace('"', '\\"').replace("'", "\\'")
    return f"""<!DOCTYPE html><html><head><title>Giriş Hatası</title></head>
<body style="background:#000;color:#ff4444;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;">
<div style="text-align:center;">
<h2>Giriş başarısız</h2>
<p>{safe_error}</p>
</div>
<script>
  if (window.opener) {{
    window.opener.postMessage({{ type: "oauth-error", error: "{safe_error}" }}, "*");
  }}
</script></body></html>"""
