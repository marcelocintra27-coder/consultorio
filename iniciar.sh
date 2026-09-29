#!/bin/sh
# Sobe o consultório.
# Sem CLAMAV_ATIVO=1 o arranque é o de sempre: migrate, collectstatic e gunicorn.
# O valor 1 é só para o plano com 2 GB. O plano de 512 MB não aguenta o ClamAV.
set -eu

iniciar_aplicacao() {
  python manage.py migrate --noinput
  python manage.py collectstatic --noinput
  exec gunicorn consultorio.wsgi:application --bind 0.0.0.0:${PORT:-8000}
}

if [ "${CLAMAV_ATIVO:-}" != "1" ]; then
  iniciar_aplicacao
fi

DISCO="${RENDER_DISK_PATH:-}"
if [ -z "$DISCO" ]; then
  echo "ClamAV: RENDER_DISK_PATH não está definido. O antivírus não será iniciado."
  iniciar_aplicacao
fi

DIR="${DISCO%/}/clamav"
mkdir -p "$DIR"

PORTA="${EXAMES_CLAMD_PORT:-3310}"
case "$PORTA" in
  ''|*[!0-9]*) PORTA=3310 ;;
esac

ESPERA="${CLAMAV_ESPERA_SEGUNDOS:-120}"
case "$ESPERA" in
  ''|*[!0-9]*) ESPERA=120 ;;
esac

CLAMD_CONF="${DIR}/clamd.conf"
FRESH_UMA_VEZ="${DIR}/freshclam-uma-vez.conf"
FRESH_DAEMON="${DIR}/freshclam.conf"

if id clamav >/dev/null 2>&1; then
  chown clamav:clamav "$DIR"
else
  echo "ClamAV: usuário clamav não encontrado. O serviço seguirá com o usuário atual."
fi
chmod 755 "$DIR"

{
  echo "DatabaseDirectory ${DIR}"
  echo "LogTime yes"
  echo "PidFile ${DIR}/clamd.pid"
  echo "TCPSocket ${PORTA}"
  echo "TCPAddr 127.0.0.1"
  echo "StreamMaxLength 25M"
  echo "ConcurrentDatabaseReload no"
  echo "Foreground yes"
  if id clamav >/dev/null 2>&1; then
    echo "User clamav"
  fi
} > "$CLAMD_CONF"
chmod 644 "$CLAMD_CONF"

escrever_fresh() {
  arquivo="$1"
  foreground="$2"
  checks="$3"
  notificar="$4"
  {
    echo "DatabaseDirectory ${DIR}"
    echo "LogTime yes"
    echo "Foreground ${foreground}"
    echo "Checks ${checks}"
    echo "DatabaseMirror database.clamav.net"
    echo "ConnectTimeout 30"
    # Evita segurar o site para sempre se o espelho travar. O daemon tenta de novo.
    echo "ReceiveTimeout 300"
    echo "Bytecode yes"
    if id clamav >/dev/null 2>&1; then
      echo "DatabaseOwner clamav"
    fi
    if [ "$notificar" = "sim" ]; then
      echo "NotifyClamd ${CLAMD_CONF}"
    fi
  } > "$arquivo"
  chmod 644 "$arquivo"
}

escrever_fresh "$FRESH_UMA_VEZ" yes 1 nao
escrever_fresh "$FRESH_DAEMON" no 12 sim

if freshclam --config-file="$FRESH_UMA_VEZ" --foreground --stdout; then
  echo "ClamAV: assinaturas atualizadas."
else
  if find "$DIR" -maxdepth 1 -type f \( -name '*.cvd' -o -name '*.cld' \) | grep -q .; then
    echo "ClamAV: a atualização falhou, mas já existem assinaturas no disco. Seguindo."
  else
    echo "ClamAV: a atualização falhou e ainda não há assinaturas no disco. Seguindo."
  fi
fi

# Somente 127.0.0.1. A porta não é publicada para fora do container.
clamd --config-file="$CLAMD_CONF" &
CLAMD_PID=$!

if python - "$PORTA" "$ESPERA" "$CLAMD_PID" <<'PY'
import os
import socket
import sys
import time

porta = int(sys.argv[1])
espera = int(sys.argv[2])
pid = int(sys.argv[3])
prazo = time.monotonic() + espera


def processo_vivo():
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


while True:
    try:
        with socket.create_connection(("127.0.0.1", porta), timeout=2) as sock:
            sock.settimeout(2)
            sock.sendall(b"zPING\0")
            dados = b""
            while b"\0" not in dados and len(dados) < 64:
                parte = sock.recv(64)
                if not parte:
                    break
                dados += parte
            if b"PONG" in dados:
                raise SystemExit(0)
    except OSError:
        pass
    if not processo_vivo() or time.monotonic() >= prazo:
        raise SystemExit(1)
    time.sleep(1)
PY
then
  echo "ClamAV: clamd pronto."
else
  echo "ClamAV: clamd não respondeu em ${ESPERA} segundos. O sistema segue; fotos e exames ficam retidos até o antivírus responder."
fi

freshclam --config-file="$FRESH_DAEMON" --daemon --checks=12 \
  || echo "ClamAV: o freshclam em segundo plano não iniciou. O clamd segue com as assinaturas que já estiverem no disco."

iniciar_aplicacao
