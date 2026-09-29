"""Diz se o ClamAV local responde, sem enviar arquivo de paciente."""
import socket
from datetime import datetime

from django.core.management.base import BaseCommand

from exames.config import limite


def _ler(sock):
    resposta = b''
    while b'\0' not in resposta and len(resposta) < 512:
        parte = sock.recv(256)
        if not parte:
            break
        resposta += parte
    return resposta.split(b'\0', 1)[0].decode('utf-8', 'replace')


def _comando(porta, comando):
    with socket.create_connection(('127.0.0.1', porta), timeout=3) as sock:
        sock.settimeout(3)
        sock.sendall(comando)
        return _ler(sock)


def consultar():
    """PING e VERSION em conexões separadas. Não usa INSTREAM e não lê arquivo."""
    porta = limite('EXAMES_CLAMD_PORT', 3310)
    if 'PONG' not in _comando(porta, b'zPING\0'):
        return False, ''
    try:
        versao = _comando(porta, b'zVERSION\0')
    except (OSError, TimeoutError):
        return True, ''
    return True, versao


def data_das_assinaturas(versao):
    # Formato do clamd: ClamAV 1.4.3/27000/Tue Sep 29 08:00:00 2026
    if versao.count('/') < 2:
        return ''
    bruto = versao.split('/', 2)[2].strip()
    try:
        momento = datetime.strptime(bruto, '%a %b %d %H:%M:%S %Y')
    except ValueError:
        return bruto
    return momento.strftime('%d/%m/%Y')


class Command(BaseCommand):
    help = 'Diz se o antivírus local está respondendo e a data das assinaturas, sem enviar arquivos.'

    def handle(self, **options):
        try:
            respondeu, versao = consultar()
        except (OSError, TimeoutError):
            respondeu, versao = False, ''
        if not respondeu:
            self.stdout.write('Antivírus: não respondendo.')
            return
        self.stdout.write('Antivírus: respondendo.')
        data = data_das_assinaturas(versao)
        if data:
            self.stdout.write(f'Data das assinaturas: {data}.')
        else:
            self.stdout.write('Data das assinaturas: não informada.')
