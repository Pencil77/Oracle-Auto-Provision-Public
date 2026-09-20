FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN echo 'from http.server import HTTPServer, BaseHTTPRequestHandler\n\
class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):\n\
    def do_GET(self):\n\
        self.send_response(200)\n\
        self.end_headers()\n\
        self.wfile.write(b"Alive")\n\
httpd = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)\n\
httpd.serve_forever()' > dummy_server.py

RUN echo '#!/bin/sh\n\
cp /etc/secrets/* /app/ 2>/dev/null || true
python3 dummy_server.py &\n\
python3 bot.py\n\
wait -n' > start.sh
RUN chmod +x start.sh

EXPOSE 8000
CMD ["./start.sh"]
