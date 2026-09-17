# Python 3.12.14 / Debian Bookworm, imagem oficial fixada por digest.
FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# O serviço de transcrição usa o executável ffmpeg em ia_seguranca/servicos.py.
# A versão é a publicada para Debian Bookworm e fica fixa para builds repetíveis.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg=7:5.1.9-0+deb12u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

CMD ["/bin/sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn consultorio.wsgi:application --bind 0.0.0.0:${PORT:-8000}"]
