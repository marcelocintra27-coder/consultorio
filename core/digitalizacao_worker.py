"""Valida imagens em processo isolado, sem Django, banco ou rede."""
import json
from pathlib import Path
import sys
import warnings

# Reutiliza somente o limitador de memória já existente, sem inicializar Django.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from exames.worker import limitar_memoria


def _tem_transparencia(imagem):
    if 'A' in imagem.getbands():
        return True
    return 'transparency' in imagem.info


def _reencodar(imagem, extensao, destino):
    """Regrava JPEG ou PNG sem EXIF, perfil de cor, comentário ou texto."""
    from PIL import ImageOps
    if not destino:
        raise ValueError('Destino do re-encode ausente.')
    # in_place: gira sem criar uma segunda cópia da imagem na memória.
    ImageOps.exif_transpose(imagem, in_place=True)
    if imagem.mode.startswith('I'):
        # PNG de 16 bits (tons 0-65535): reduz para 8 bits sem saturar em branco.
        reduzida = imagem.point(lambda v: v * (1 / 256)).convert('L')
        imagem.im = None
        imagem = reduzida
    if extensao in ('.jpg', '.jpeg'):
        modo = 'RGB'
    else:
        modo = 'RGBA' if _tem_transparencia(imagem) else 'RGB'
    limpa = imagem if imagem.mode == modo else imagem.convert(modo)
    if limpa is not imagem:
        imagem.im = None  # libera os pixels originais antes de gravar
    limpa.info = {}
    if extensao in ('.jpg', '.jpeg'):
        limpa.save(destino, format='JPEG', quality=90, exif=b'', icc_profile=None)
    else:
        limpa.save(destino, format='PNG', exif=b'', icc_profile=None)


def validar(caminho, extensao, pixels, destino=None):
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
            if extensao in ('.jpg', '.jpeg', '.png'):
                _reencodar(imagem, extensao, destino)
    return tipo


if __name__ == '__main__':
    try:
        job = limitar_memoria()
        destino = sys.argv[4] if len(sys.argv) > 4 else None
        print(json.dumps({
            'tipo': validar(sys.argv[1], sys.argv[2], int(sys.argv[3]), destino)}))
    except Exception:
        print('{}')
        sys.exit(1)
