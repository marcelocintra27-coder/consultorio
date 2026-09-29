# Python 3.12.14 / Debian Bookworm, imagem oficial fixada por digest.
FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ffmpeg é usado pela transcrição em ia_seguranca/servicos.py.
# clamav-daemon e clamav-freshclam atendem exames/antivirus.py em 127.0.0.1.
# As versões são as do Debian Bookworm e ficam fixas para builds repetíveis.
# invoke-rc.d é desviado na instalação para o pacote não baixar assinaturas
# nem subir serviço durante o build. As assinaturas só entram no disco, em runtime.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y debconf \
    && echo 'clamav-freshclam clamav-freshclam/autoupdate_freshclam select manual' | debconf-set-selections \
    && dpkg-divert --local --rename --divert /usr/sbin/invoke-rc.d.real --add /usr/sbin/invoke-rc.d \
    && printf '%s\n' '#!/bin/sh' 'exit 0' > /usr/sbin/invoke-rc.d \
    && chmod +x /usr/sbin/invoke-rc.d \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
        ffmpeg=7:5.1.9-0+deb12u1 \
        clamav-daemon=1.4.3+dfsg-1~deb12u2 \
        clamav-freshclam=1.4.3+dfsg-1~deb12u2 \
    && rm -f /usr/sbin/invoke-rc.d \
    && dpkg-divert --local --rename --remove /usr/sbin/invoke-rc.d \
    && rm -rf /var/lib/apt/lists/* /var/lib/clamav/*.cvd /var/lib/clamav/*.cld

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

CMD ["/bin/sh", "/app/iniciar.sh"]
