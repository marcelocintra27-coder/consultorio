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


def _pixels_sem_metadados(imagem, modo):
    from PIL import Image
    convertida = imagem.convert(modo)
    return Image.frombytes(modo, convertida.size, convertida.tobytes())


def _reencodar(imagem, extensao, destino):
    """Regrava JPEG ou PNG sem EXIF, perfil de cor, comentário ou texto."""
    from PIL import ImageOps
    if not destino:
        raise ValueError('Destino do re-encode ausente.')
    transposta = ImageOps.exif_transpose(imagem)
    if transposta is None:
        transposta = imagem
    try:
        if extensao in ('.jpg', '.jpeg'):
            limpa = _pixels_sem_metadados(transposta, 'RGB')
            limpa.save(destino, format='JPEG', quality=90)
        else:
            modo = 'RGBA' if _tem_transparencia(transposta) else 'RGB'
            limpa = _pixels_sem_metadados(transposta, modo)
            limpa.save(destino, format='PNG')
    finally:
        if transposta is not imagem:
            transposta.close()


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
