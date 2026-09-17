"""ClamAV INSTREAM apenas em loopback; nunca envia dados a serviços externos."""
import socket
import struct
import time
from .config import limite


def inspecionar(arquivo):
    prazo = time.monotonic() + limite('EXAMES_SCAN_TIMEOUT', 15)
    try:
        with socket.create_connection(('127.0.0.1', limite('EXAMES_CLAMD_PORT', 3310)), timeout=3) as sock:
            def restante():
                valor = prazo - time.monotonic()
                if valor <= 0:
                    raise TimeoutError
                sock.settimeout(valor)
            restante()
            sock.sendall(b'zINSTREAM\0')
            arquivo.seek(0)
            while bloco := arquivo.read(65536):
                restante()
                sock.sendall(struct.pack('!I', len(bloco)) + bloco)
            restante()
            sock.sendall(b'\0\0\0\0')
            resposta = b''
            while b'\0' not in resposta and len(resposta) < 4096:
                restante()
                parte = sock.recv(512)
                if not parte:
                    break
                resposta += parte
            if resposta == b'stream: OK\0':
                return 'liberado'
            if resposta.endswith(b' FOUND\0'):
                return 'rejeitado'
    except (OSError, TimeoutError):
        pass
    finally:
        arquivo.seek(0)
    return 'quarentena'
