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
  <div style="display: flex; justify-content: center; gap: 10px; margin-bottom: 15px; flex-wrap: wrap;">
    <span style="background: #21262d; border: 1px solid #30363d; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; color: #58a6ff;">🏛️ Region: us-ashburn-1 (US East)</span>
    <span style="background: #21262d; border: 1px solid #30363d; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; color: #7ee787;">⚙️ ADs: AD-1, AD-2, AD-3 (Concurrent Sweep)</span>
    <span style="background: #21262d; border: 1px solid #30363d; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; color: #d2a8ff;">💻 Shape: VM.Standard.A1.Flex (2 OCPU / 12GB)</span>
    <span style="background: #21262d; border: 1px solid #30363d; padding: 4px 10px; border-radius: 6px; font-size: 0.85em; color: #f0883e;">⏰ Timezone: IST (UTC+5:30)</span>
  </div>
  <div class="terminal-container">
    <div class="terminal-header">
      <span>oci_occ.log (IST)</span>
      <span>Auto-refreshing every 5s</span>
    </div>
    <div class="terminal" id="terminal">Loading live logs from container...</div>
  </div>
</body>
</html>"""

import configparser
import datetime
import os
import re
import threading
import time
import requests

IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
UTC_LOG_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}(?:,\d{3})?)(?!\s*IST)(\s+.*)$")

def convert_line_to_ist(line: str) -> str:
    m = UTC_LOG_RE.match(line)
    if not m:
        return line.replace("legacy:", "silicon box:")
    date_str, time_str, rest = m.groups()
    try:
        if "," in time_str:
            main_time, msec = time_str.split(",")
            dt = datetime.datetime.strptime(f"{date_str} {main_time}", "%Y-%m-%d %H:%M:%S")
            msec_str = f",{msec}"
        else:
            dt = datetime.datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
            msec_str = ""
        dt_utc = dt.replace(tzinfo=datetime.timezone.utc)
        dt_ist = dt_utc.astimezone(IST_TZ)
        dt_formatted = dt_ist.strftime("%Y-%m-%d %H:%M:%S")
        res = f"{dt_formatted}{msec_str} IST{rest}"
        return res.replace("legacy:", "silicon box:")
    except Exception:
        return line.replace("legacy:", "silicon box:")

def send_weekly_telegram_status():
    token = os.environ.get("OCCFIX_TELEGRAM_BOT_TOKEN", "")
    uid = os.environ.get("OCCFIX_TELEGRAM_UID", "")
    
    if os.path.exists("configuration.ini"):
        try:
            cp = configparser.ConfigParser()
            cp.read("configuration.ini")
            if cp.has_section("Telegram"):
                token = cp.get("Telegram", "bot_token", fallback=token)
                uid = cp.get("Telegram", "uid", fallback=uid)
        except Exception:
            pass

    if not token or not uid or token == "xxxx" or uid == "xxxx":
        print("Telegram credentials not configured for status update.")
        return

    last_log = "Polling active..."
    if os.path.exists("oci_occ.log"):
        try:
            with open("oci_occ.log", "r", encoding="utf-8", errors="ignore") as f:
                lines = [line.strip() for line in f if line.strip()]
                if lines:
                    last_log = convert_line_to_ist(lines[-1])
        except Exception:
            pass

    region = "us-ashburn-1"
    if os.path.exists("config"):
        try:
            cfg = configparser.ConfigParser()
            cfg.read("config")
            if cfg.has_section("DEFAULT"):
                region = cfg.get("DEFAULT", "region", fallback=region)
        except Exception:
            pass

    display_name = "silicon box"
    ads_str = "All Configured ADs"
    shape_str = "VM.Standard.A1.Flex (2 OCPU / 12GB)"
    if os.path.exists("configuration.ini"):
        try:
            cp = configparser.ConfigParser()
            cp.read("configuration.ini")
            if cp.has_section("Instance"):
                display_name = cp.get("Instance", "display_name", fallback=display_name)
            if cp.has_section("OCI"):
                raw_ads = cp.get("OCI", "availability_domains", fallback="")
                if raw_ads:
                    import json
                    try:
                        parsed_ads = json.loads(raw_ads)
                        ads_str = ", ".join([ad.split(":")[-1] for ad in parsed_ads])
                    except Exception:
                        ads_str = raw_ads
            if cp.has_section("Machine"):
                m_shape = cp.get("Machine", "shape", fallback="VM.Standard.A1.Flex")
                m_ocpus = cp.get("Machine", "ocpus", fallback="2")
                m_mem = cp.get("Machine", "memory", fallback="12")
                shape_str = f"{m_shape} ({m_ocpus} OCPU / {m_mem}GB)"
        except Exception:
            pass

    msg = (
        "📊 Weekly Oracle Bot Status Update\n\n"
        "🟢 Status: Active & Hunting\n"
        f"📍 Target: {display_name}\n"
        f"🏛️ Region: {region}\n"
        f"⚙️ ADs: {ads_str}\n"
        f"💻 Shape: {shape_str}\n\n"
        f"📝 Latest Status: {last_log}\n\n"
        "The bot is running smoothly in the background. You will receive an immediate alert when the server is secured!"
    )

    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": uid, "text": msg},
            timeout=10,
        )
    except Exception as e:
        print("Failed to send status update:", e)

def weekly_schedule_worker():
    last_sent_day = -1
    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            # IST is UTC + 5h30m. Friday 21:00 IST is Friday 15:30 UTC.
            ist_time = now_utc + datetime.timedelta(hours=5, minutes=30)
            # Friday is weekday 4 (0=Monday, 4=Friday)
            if ist_time.weekday() == 4 and ist_time.hour == 21 and ist_time.minute == 0:
                if last_sent_day != ist_time.day:
                    send_weekly_telegram_status()
                    last_sent_day = ist_time.day
        except Exception:
            pass
        time.sleep(30)

threading.Thread(target=weekly_schedule_worker, daemon=True).start()

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/logs':
            if os.path.exists('oci_occ.log'):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                try:
                    with open('oci_occ.log', 'r', encoding='utf-8', errors='ignore') as f:
                        lines = [convert_line_to_ist(line.rstrip('\r\n')) for line in f]
                    self.wfile.write('\n'.join(lines).encode('utf-8'))
                except Exception as e:
                    self.wfile.write(f"Error reading logs: {e}".encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Log file not found")
        elif self.path == '/status-ping':
            try:
                send_weekly_telegram_status()
                self.send_response(200)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write(b"Weekly status ping sent to Telegram successfully")
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(str(e).encode('utf-8'))
        else:
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))

httpd = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
httpd.serve_forever()
