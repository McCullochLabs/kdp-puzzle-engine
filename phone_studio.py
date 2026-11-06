"""Private loopback Studio: checked plans, durable packs, explicit Codex help."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import re
import threading
from time import monotonic

from publishing.studio_reader_profiles import BALANCES, READER_PROFILES
from publishing.activity_packs import FORMATS
from publishing.studio_pack_planning import available_pack_themes, prepare_pack_request
from publishing.phone_pack_service import PackService, Conflict, suggest_pack

ASSETS = Path(__file__).resolve().parent/'publishing/phone_web'
ROOT = Path(__file__).resolve().parent
PLANNING_LOCK = threading.Lock()
AI_LOCK = threading.Lock()
REQUEST_BODY_LIMIT = 8192
REJECTED_BODY_DRAIN_LIMIT = 65536


def configuration():
    return {'readers':{key:value['label'] for key,value in READER_PROFILES.items()},
        'balances':list(BALANCES), 'formats':list(FORMATS),
        'themes':list(available_pack_themes(ROOT)), 'prototype':True,
        'generation_available':True, 'ai_available':True,
        'ai_policy':'ChatGPT/Codex for explicit AI help; local rules for routine work.'}


class PrototypeHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def trusted_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def respond(self, data, status=200, mime='application/json; charset=utf-8', filename=None):
        if not isinstance(data, bytes):
            data=json.dumps(data,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        if filename:
            self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(data)

    def _discard_small_request_body(self, maximum=REQUEST_BODY_LIMIT):
        """Avoid a Windows TCP reset when rejecting an unread, bounded body."""
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            return
        if not 0 < length <= maximum:
            return
        previous_timeout = self.connection.gettimeout()
        try:
            deadline=monotonic()+0.25
            remaining=length
            while remaining:
                budget=deadline-monotonic()
                if budget<=0:break
                self.connection.settimeout(budget)
                chunk=self.rfile.read1(min(remaining,8192))
                if not chunk:break
                remaining-=len(chunk)
        except OSError:
            pass
        finally:
            self.connection.settimeout(previous_timeout)

    def do_POST(self):
        if (not self.trusted_host() or self.headers.get('Origin') != 'http://'+self.headers.get('Host','') or
                self.headers.get('X-Studio-Request') != 'plan'):
            self._discard_small_request_body()
            self.respond({'error':'Open the Studio on this computer and try again.'},403)
            return
        routes=('/api/plan','/api/projects','/api/create','/api/assist')
        if self.path not in routes:
            self._discard_small_request_body()
            self.respond({'error':'This action is not available.'},404)
            return
        if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
            self._discard_small_request_body()
            self.respond({'error':'Send a JSON plan.'},415)
            return
        try:
            length=int(self.headers.get('Content-Length','0'))
        except ValueError:
            length=0
        if not 0 < length <= REQUEST_BODY_LIMIT:
            self._discard_small_request_body(REJECTED_BODY_DRAIN_LIMIT)
            self.respond({'error':'This request is too large or empty.'},413)
            return
        lock = AI_LOCK if self.path == '/api/assist' else PLANNING_LOCK
        if not lock.acquire(blocking=False):
            self._discard_small_request_body()
            self.respond({'error':'Another request is finishing. Wait a moment and try again.'},409)
            return
        try:
            data=json.loads(self.rfile.read(length))
            if self.path == '/api/plan':
                result=prepare_pack_request(data,ROOT)
            elif self.path == '/api/assist':
                if not isinstance(data,dict) or set(data) != {'text'}:
                    raise ValueError('Describe your activity pack using the AI help box.')
                result={'request':suggest_pack(ROOT,data['text']), 'provider':'Codex', 'generated':False}
            elif self.path == '/api/projects':
                if not isinstance(data,dict) or set(data) != {'request','id','revision'}:
                    raise ValueError('Save the project choices shown in the form.')
                if data['id'] is not None and (not isinstance(data['id'],str) or not re.fullmatch('[a-f0-9]{32}',data['id'])):
                    raise ValueError('This project identifier is invalid.')
                result=self.server.service.save(data['request'],data['id'],data['revision'])
            else:
                if not isinstance(data,dict) or set(data) != {'id','revision'} or not isinstance(data['id'],str) or not re.fullmatch('[a-f0-9]{32}',data['id']):
                    raise ValueError('Choose a saved project to create.')
                result={'job':self.server.service.enqueue(data['id'],data['revision'])}
            self.respond(result)
        except Conflict as exc:
            self.respond({'error':str(exc)},409)
        except (ValueError,UnicodeError) as exc:
            self.respond({'error':str(exc)},422)
        except (TimeoutError,ConnectionError):
            return
        except Exception:
            message=('ChatGPT/Codex could not complete this request. Check its sign-in in the desktop Studio, or use the activity buttons. No fallback provider was used.'
                     if self.path == '/api/assist' else 'The request could not be completed. Your saved projects are preserved. Try again or use the desktop Studio.')
            self.respond({'error':message},503)
        finally:
            lock.release()

    def do_GET(self):
        if not self.trusted_host():
            self.send_error(403)
            return
        path=self.path.split('?',1)[0]
        routes={'/':('index.html','text/html; charset=utf-8'), '/app.js':('app.js','text/javascript; charset=utf-8'), '/style.css':('style.css','text/css; charset=utf-8')}
        try:
            if path == '/api/config':
                self.respond(configuration())
            elif path in routes:
                filename,mime=routes[path]
                self.respond((ASSETS/filename).read_bytes(),mime=mime)
            elif path == '/api/projects':
                self.respond({'projects':self.server.service.projects()})
            elif match := re.fullmatch(r'/api/jobs/([a-f0-9]{32})',path):
                self.respond(self.server.service.job(match[1]))
            elif match := re.fullmatch(r'/api/files/([a-f0-9]{32})/(activities|answers|zip)',path):
                file=self.server.service.artifact(match[1],match[2])
                self.respond(file.read_bytes(),mime='application/zip' if match[2]=='zip' else 'application/pdf',filename=file.name)
            elif match := re.fullmatch(r'/api/preview/([a-f0-9]{32})/(activities|answers)/(\d{1,2})',path):
                self.respond(self.server.service.preview(match[1],match[2],int(match[3])),mime='image/png')
            else:
                self.send_error(404)
        except ValueError as exc:
            self.respond({'error':str(exc)},404)
        except (TimeoutError,ConnectionError):
            return
        except Exception:
            self.respond({'error':'The requested project or file is unavailable. Your saved work is preserved.'},503)

    def log_message(self,*_):
        pass


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Choose a port between 1024 and 65535.')
    # Bind first: a second launcher cannot start a competing worker/recovery pass.
    with ThreadingHTTPServer(('127.0.0.1',args.port),PrototypeHandler) as server:
        server.service=PackService(ROOT)
        print(f'Family Studio: http://127.0.0.1:{args.port}',flush=True)
        print('This HP only. Saved projects and pack jobs continue independently of browser tabs. Ctrl+C to stop.',flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.service.close()


if __name__ == '__main__':
    main()
