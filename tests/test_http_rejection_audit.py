from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from phone_studio import PrototypeHandler


def test_rejected_small_bodies_return_403_reliably():
    with ThreadingHTTPServer(("127.0.0.1",0),PrototypeHandler) as server:
        thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for _ in range(100):
                connection=HTTPConnection("127.0.0.1",server.server_port,timeout=2)
                try:
                    connection.request("POST","/api/plan",body="{}",headers={"Origin":"https://untrusted.example","Content-Type":"application/json","X-Studio-Request":"plan"})
                    response=connection.getresponse()
                    assert response.status==403
                    assert response.read()
                finally:connection.close()
        finally:server.shutdown();thread.join(timeout=3)
