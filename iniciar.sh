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

  if command -v runuser >/dev/null 2>&1; then
    FERRAMENTA=runuser
  elif command -v setpriv >/dev/null 2>&1; then
    FERRAMENTA=setpriv
  else
    echo "ClamAV: nem runuser nem setpriv foram encontrados. O antivírus não será iniciado."
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

  linha_presente() {
    grep -F -x -q -- "$2" "$1"
  }

  publicar() {
    destino="$1"
    shift
    temporario="${destino}.tmp.$$"
    umask 077
    cat > "$temporario"
    if [ $? -ne 0 ] || [ ! -s "$temporario" ]; then
      echo "ClamAV: falha ao gravar a configuração temporária. O antivírus não será iniciado."
      rm -f "$temporario"
      return 1
    fi
    for linha in "$@"; do
      if ! linha_presente "$temporario" "$linha"; then
        echo "ClamAV: configuração incompleta; o antivírus não será iniciado. Falta: ${linha}."
        rm -f "$temporario"
        return 1
      fi
    done
    if ! mv "$temporario" "$destino"; then
      echo "ClamAV: não foi possível instalar a configuração. O antivírus não será iniciado."
      rm -f "$temporario"
      return 1
    fi
    for linha in "$@"; do
      if ! linha_presente "$destino" "$linha"; then
        echo "ClamAV: configuração incompleta; o antivírus não será iniciado. Falta: ${linha}."
        rm -f "$destino"
        return 1
      fi
    done
    if ! chown clamav:clamav "$destino"; then
      echo "ClamAV: não foi possível ajustar o dono da configuração. O antivírus não será iniciado."
      rm -f "$destino"
      return 1
    fi
    if ! chmod 640 "$destino"; then
      echo "ClamAV: não foi possível ajustar a permissão da configuração. O antivírus não será iniciado."
      rm -f "$destino"
      return 1
    fi
    return 0
  }

  if ! {
    echo "DatabaseDirectory ${DIR}"
    echo "LogTime yes"
    echo "PidFile ${DIR}/clamd.pid"
    echo "TCPSocket ${PORTA}"
    echo "TCPAddr 127.0.0.1"
    echo "StreamMaxLength 25M"
    echo "ConcurrentDatabaseReload no"
    echo "Foreground yes"
    echo "User clamav"
  } | publicar "$CLAMD_CONF" \
    "DatabaseDirectory ${DIR}" \
    "TCPSocket ${PORTA}" \
    "TCPAddr 127.0.0.1" \
    "User clamav"
  then
    exit 0
  fi

  if ! {
    echo "DatabaseDirectory ${DIR}"
    echo "LogTime yes"
    echo "Foreground yes"
    echo "Checks 1"
    echo "DatabaseMirror database.clamav.net"
    echo "ConnectTimeout 30"
    echo "ReceiveTimeout 300"
    echo "Bytecode yes"
    echo "DatabaseOwner clamav"
  } | publicar "$FRESH_UMA_VEZ" \
    "DatabaseDirectory ${DIR}" \
    "DatabaseOwner clamav"
  then
    exit 0
  fi

  if ! {
    echo "DatabaseDirectory ${DIR}"
    echo "LogTime yes"
    echo "Foreground no"
    echo "Checks 12"
    echo "DatabaseMirror database.clamav.net"
    echo "ConnectTimeout 30"
    echo "ReceiveTimeout 300"
    echo "Bytecode yes"
    echo "DatabaseOwner clamav"
    echo "NotifyClamd ${CLAMD_CONF}"
  } | publicar "$FRESH_DAEMON" \
    "DatabaseDirectory ${DIR}" \
    "DatabaseOwner clamav"
  then
    exit 0
  fi

  como_clamav() {
    if [ "$FERRAMENTA" = runuser ]; then
      runuser -u clamav -- "$@"
    else
      setpriv --reuid=clamav --regid=clamav --init-groups --inh-caps=-all -- "$@"
    fi
  }

  tem_assinatura() {
    find "$DIR" -maxdepth 1 -type f \( -name '*.cvd' -o -name '*.cld' \) 2>/dev/null | grep -q .
  }

  if ! command -v timeout >/dev/null 2>&1; then
    echo "ClamAV: comando timeout não encontrado. A atualização inicial foi pulada."
  elif [ "$FERRAMENTA" = runuser ]; then
    timeout --kill-after=30 900 runuser -u clamav -- freshclam --config-file="$FRESH_UMA_VEZ" --foreground --stdout
    codigo=$?
  else
    timeout --kill-after=30 900 setpriv --reuid=clamav --regid=clamav --init-groups --inh-caps=-all -- freshclam --config-file="$FRESH_UMA_VEZ" --foreground --stdout
    codigo=$?
  fi
  if command -v timeout >/dev/null 2>&1; then
    if [ "$codigo" -eq 0 ]; then
      echo "ClamAV: assinaturas atualizadas."
    elif [ "$codigo" -eq 124 ] || [ "$codigo" -eq 137 ]; then
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
    como_clamav clamd --config-file="$CLAMD_CONF" &
    CLAMD_PID=$!
  }

  iniciar_clamd

  como_clamav freshclam --config-file="$FRESH_DAEMON" --daemon --checks=12
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
