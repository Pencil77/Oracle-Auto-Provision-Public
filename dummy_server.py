from http.server import HTTPServer, BaseHTTPRequestHandler
import os

HTML_CONTENT = """<!DOCTYPE html>
<html>
<head>
  <title>Oracle Auto-Provision Bot</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0d1117; color: #c9d1d9; margin: 0; padding: 20px; display: flex; flex-direction: column; height: 95vh; }
    h1 { color: #58a6ff; text-align: center; margin-top: 0; font-size: 1.8em; }
    .status { text-align: center; font-size: 1.1em; margin-bottom: 20px; font-weight: 500; }
    .pulse { display: inline-block; width: 12px; height: 12px; background: #3fb950; border-radius: 50%; box-shadow: 0 0 10px #3fb950; animation: blink 1.5s infinite; margin-right: 10px; vertical-align: middle; }
    @keyframes blink { 50% { opacity: 0.3; } }
    .terminal-container { flex-grow: 1; background: #010409; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
    .terminal-header { background: #161b22; padding: 8px 15px; border-bottom: 1px solid #30363d; font-size: 0.85em; color: #8b949e; display: flex; justify-content: space-between; align-items: center; }
    .terminal { flex-grow: 1; padding: 15px; font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; white-space: pre-wrap; overflow-y: auto; font-size: 13px; line-height: 1.5; color: #b3b1ad; }
    .terminal::-webkit-scrollbar { width: 10px; }
    .terminal::-webkit-scrollbar-track { background: #010409; }
    .terminal::-webkit-scrollbar-thumb { background: #30363d; border-radius: 5px; }
    .terminal::-webkit-scrollbar-thumb:hover { background: #484f58; }
  </style>
  <script>
    async function fetchLogs() {
      try {
        const response = await fetch('/logs');
        if (response.ok) {
          const text = await response.text();
          const term = document.getElementById('terminal');
          // Only auto-scroll if user is near the bottom
          const isScrolledToBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 50;
          term.textContent = text;
          if (isScrolledToBottom) {
            term.scrollTop = term.scrollHeight;
          }
        }
      } catch (e) {}
    }
    setInterval(fetchLogs, 5000);
    window.onload = fetchLogs;
  </script>
</head>
<body>
  <h1>☁️ Oracle Auto-Provision Dashboard</h1>
  <div class="status"><span class="pulse"></span> LIVE: Polling for 'silicon box'</div>
  <div class="terminal-container">
    <div class="terminal-header">
      <span>oci_occ.log</span>
      <span>Auto-refreshing every 5s</span>
    </div>
    <div class="terminal" id="terminal">Loading live logs from container...</div>
  </div>
</body>
</html>"""

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/logs':
            if os.path.exists('oci_occ.log'):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                with open('oci_occ.log', 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Log file not found")
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))

httpd = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
httpd.serve_forever()
