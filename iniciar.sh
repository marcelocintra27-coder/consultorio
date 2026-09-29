#!/bin/sh
# Sobe o consultório.
# Sem CLAMAV_ATIVO=1 o arranque é o de sempre: migrate, collectstatic e gunicorn.
# Com CLAMAV_ATIVO=1 o antivírus prepara em segundo plano e o site sobe na hora.
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

# Erros deste bloco só vão para o log. Não usam set -e e não seguram o gunicorn.
(
  trap '' HUP
  set +e

  if ! id clamav >/dev/null 2>&1; then
    echo "ClamAV: usuário clamav não encontrado. O antivírus não será iniciado."
    exit 0
  fi

  DISCO="${RENDER_DISK_PATH:-}"
  if [ -z "$DISCO" ]; then
    echo "ClamAV: RENDER_DISK_PATH não está definido. O antivírus não será iniciado."
    exit 0
  fi

  DIR="${DISCO%/}/clamav"
  PORTA="${EXAMES_CLAMD_PORT:-3310}"
  case "$PORTA" in
    ''|*[!0-9]*) PORTA=3310 ;;
  esac

  CLAMD_CONF="${DIR}/clamd.conf"
  FRESH_UMA_VEZ="${DIR}/freshclam-uma-vez.conf"
  FRESH_DAEMON="${DIR}/freshclam.conf"
  CLAMD_PID=""

  if ! mkdir -p "$DIR"; then
    echo "ClamAV: não foi possível criar a pasta de assinaturas."
    exit 0
  fi
  if ! chown clamav:clamav "$DIR"; then
    echo "ClamAV: não foi possível entregar a pasta ao usuário clamav. O antivírus não será iniciado."
    exit 0
  fi
  if ! chmod 750 "$DIR"; then
    echo "ClamAV: não foi possível ajustar a permissão da pasta de assinaturas. O antivírus não será iniciado."
    exit 0
  fi

  {
    echo "DatabaseDirectory ${DIR}"
    echo "LogTime yes"
    echo "PidFile ${DIR}/clamd.pid"
    echo "TCPSocket ${PORTA}"
    echo "TCPAddr 127.0.0.1"
    echo "StreamMaxLength 25M"
    echo "ConcurrentDatabaseReload no"
    echo "Foreground yes"
    echo "User clamav"
  } > "$CLAMD_CONF"

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
      echo "ReceiveTimeout 300"
      echo "Bytecode yes"
      echo "DatabaseOwner clamav"
      if [ "$notificar" = "sim" ]; then
        echo "NotifyClamd ${CLAMD_CONF}"
      fi
    } > "$arquivo"
  }

  escrever_fresh "$FRESH_UMA_VEZ" yes 1 nao
  escrever_fresh "$FRESH_DAEMON" no 12 sim

  for arquivo in "$CLAMD_CONF" "$FRESH_UMA_VEZ" "$FRESH_DAEMON"; do
    if ! chown clamav:clamav "$arquivo"; then
      echo "ClamAV: não foi possível ajustar o dono de ${arquivo}. O antivírus não será iniciado."
      exit 0
    fi
    if ! chmod 640 "$arquivo"; then
      echo "ClamAV: não foi possível ajustar a permissão de ${arquivo}. O antivírus não será iniciado."
      exit 0
    fi
  done

  tem_assinatura() {
    find "$DIR" -maxdepth 1 -type f \( -name '*.cvd' -o -name '*.cld' \) 2>/dev/null | grep -q .
  }

  if ! command -v timeout >/dev/null 2>&1; then
    echo "ClamAV: comando timeout não encontrado. A atualização inicial foi pulada."
  else
    timeout --foreground 900 freshclam --config-file="$FRESH_UMA_VEZ" --foreground --stdout
    codigo=$?
    if [ "$codigo" -eq 0 ]; then
      echo "ClamAV: assinaturas atualizadas."
    elif [ "$codigo" -eq 124 ]; then
      echo "ClamAV: a atualização inicial passou de 900 segundos e foi interrompida."
    elif tem_assinatura; then
      echo "ClamAV: a atualização falhou, mas já existem assinaturas no disco."
    else
      echo "ClamAV: a atualização falhou e ainda não há assinaturas no disco."
    fi
  fi

  clamd_rodando() {
    if [ -z "$CLAMD_PID" ]; then
      return 1
    fi
    kill -0 "$CLAMD_PID" 2>/dev/null
  }

  iniciar_clamd() {
    if clamd_rodando; then
      return 0
    fi
    echo "ClamAV: iniciando clamd."
    clamd --config-file="$CLAMD_CONF" &
    CLAMD_PID=$!
  }

  iniciar_clamd

  freshclam --config-file="$FRESH_DAEMON" --daemon --checks=12
  if [ $? -ne 0 ]; then
    echo "ClamAV: o freshclam em segundo plano não iniciou."
  fi

  while true; do
    sleep 60
    if tem_assinatura && ! clamd_rodando; then
      echo "ClamAV: clamd parado com assinaturas no disco. Iniciando de novo."
      iniciar_clamd
    fi
  done
) &

iniciar_aplicacao
