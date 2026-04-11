def oauth_success_page(completion_code: str) -> str:
    return f"""<!DOCTYPE html><html><head><title>Giriş Başarılı</title></head>
<body style="background:#000;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;">
<div style="text-align:center;">
<h2>Giriş başarılı!</h2>
<p>Bu pencere kapanacak...</p>
</div>
<script>
  if (window.opener) {{
    const allowedOrigins = [
      "http://localhost:8888",
      "http://127.0.0.1:8888",
      "http://localhost:3000",
      "http://127.0.0.1:3000"
    ];
    allowedOrigins.forEach((origin) => {{
      window.opener.postMessage({{ type: "oauth-complete", code: "{completion_code}" }}, origin);
    }});
    setTimeout(() => window.close(), 1000);
  }} else {{
    document.querySelector('p').textContent = 'Pencereyi kapatabilirsiniz.';
  }}
</script></body></html>"""


def oauth_error_page(error: str) -> str:
    import html
    safe_error = html.escape(error, quote=True)
    return f"""<!DOCTYPE html><html><head><title>Giriş Hatası</title></head>
<body style="background:#000;color:#ff4444;display:flex;align-items:center;justify-content:center;height:100vh;font-family:system-ui;">
<div style="text-align:center;">
<h2>Giriş başarısız</h2>
<p>{safe_error}</p>
</div>
<script>
  if (window.opener) {{
    const allowedOrigins = [
      "http://localhost:8888",
      "http://127.0.0.1:8888",
      "http://localhost:3000",
      "http://127.0.0.1:3000"
    ];
    allowedOrigins.forEach((origin) => {{
      window.opener.postMessage({{ type: "oauth-error", error: "{safe_error}" }}, origin);
    }});
  }}
</script></body></html>"""
