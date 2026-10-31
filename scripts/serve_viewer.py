"""Serve generated viewer on loopback; original imaging inputs are not served."""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit
import argparse

ROOT = Path(__file__).resolve().parents[1]
class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.mjs': 'text/javascript', '.stl': 'application/octet-stream', '.bin': 'application/octet-stream'}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)
    def do_GET(self):
        request_path = unquote(urlsplit(self.path).path)
        resolved = (ROOT / request_path.lstrip('/')).resolve()
        try:
            relative = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            self.send_error(403); return
        if request_path == '/':
            self.path = '/index.html'
        elif relative != 'index.html' and not relative.startswith('web/'):
            self.send_error(404); return
        if '/source-cache/' in relative or '/backup/' in relative or '/qa/' in relative:
            self.send_error(404); return
        return super().do_GET()
    def list_directory(self, path):
        self.send_error(404); return None
    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache')
        super().end_headers()

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    args=parser.parse_args()
    print(f'CT viewer: http://127.0.0.1:{args.port}/index.html', flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
