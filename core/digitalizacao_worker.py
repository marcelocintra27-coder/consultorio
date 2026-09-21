"""Valida imagens em processo isolado, sem Django, banco ou rede."""
import json
from pathlib import Path
import sys
import warnings

# Reutiliza somente o limitador de memória já existente, sem inicializar Django.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from exames.worker import limitar_memoria


def validar(caminho, extensao, pixels):
    from PIL import Image
    formatos = {'.jpg': ('JPEG', 'image/jpeg'), '.jpeg': ('JPEG', 'image/jpeg'),
                '.png': ('PNG', 'image/png'), '.gif': ('GIF', 'image/gif'),
                '.webp': ('WEBP', 'image/webp')}
    esperado, tipo = formatos[extensao]
    Image.MAX_IMAGE_PIXELS = pixels
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        with Image.open(caminho) as imagem:
            if (imagem.format != esperado or imagem.width * imagem.height > pixels
                    or getattr(imagem, 'n_frames', 1) != 1):
                raise ValueError('Imagem incompatível ou acima dos limites.')
            imagem.verify()
        with Image.open(caminho) as imagem:
            imagem.load()
    return tipo


if __name__ == '__main__':
    try:
        job = limitar_memoria()
        print(json.dumps({'tipo': validar(sys.argv[1], sys.argv[2], int(sys.argv[3]))}))
    except Exception:
        print('{}')
        sys.exit(1)
