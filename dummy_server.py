from http.server import HTTPServer, BaseHTTPRequestHandler
import os

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/logs':
            if os.path.exists('oci_occ.log'):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                with open('oci_occ.log', 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Log file not found")
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Alive")

httpd = HTTPServer(("0.0.0.0", 8000), SimpleHTTPRequestHandler)
httpd.serve_forever()
