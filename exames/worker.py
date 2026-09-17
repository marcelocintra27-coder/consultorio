"""Validação isolada: sem Django, banco ou rede; tempo limitado pelo pai."""
import json
import os
import sys
import warnings


def limitar_memoria():
    teto = 512 * 1024 * 1024
    if os.name != 'nt':
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (teto, teto))
        return None
    import ctypes as c
    from ctypes import wintypes as w
    class Basic(c.Structure):
        _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong), ('flags', w.DWORD),
                    ('min_ws', c.c_size_t), ('max_ws', c.c_size_t), ('active', w.DWORD),
                    ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
    class IO(c.Structure):
        _fields_ = [(n, c.c_ulonglong) for n in ('ro', 'wo', 'oo', 'rb', 'wb', 'ob')]
    class Extended(c.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', c.c_size_t),
                    ('job_memory', c.c_size_t), ('peak_process', c.c_size_t), ('peak_job', c.c_size_t)]
    k = c.WinDLL('kernel32', use_last_error=True)
    k.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.GetCurrentProcess.restype = w.HANDLE
    job = k.CreateJobObjectW(None, None)
    info = Extended()
    info.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.process_memory = teto
    if not job or not k.SetInformationJobObject(job, 9, c.byref(info), c.sizeof(info)) or not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        raise RuntimeError('Limite de memória indisponível')
    return job


def validar(caminho, extensao, pixels, paginas):
    from PIL import Image
    with open(caminho, 'rb') as f:
        inicio = f.read(12)
    if extensao in ('.jpg', '.jpeg', '.png'):
        esperado = 'PNG' if extensao == '.png' else 'JPEG'
        Image.MAX_IMAGE_PIXELS = pixels
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with Image.open(caminho) as imagem:
                if imagem.format != esperado or imagem.width * imagem.height > pixels or getattr(imagem, 'n_frames', 1) != 1:
                    raise ValueError
                imagem.verify()
            with Image.open(caminho) as imagem:
                imagem.load()
        return 'image/png' if esperado == 'PNG' else 'image/jpeg'
    if extensao != '.pdf' or not inicio.startswith(b'%PDF-'):
        raise ValueError
    from pypdf import PdfReader
    from pypdf.generic import DictionaryObject, ArrayObject, IndirectObject
    with open(caminho, 'rb') as f:
        reader = PdfReader(f, strict=True)
        if reader.is_encrypted:
            raise ValueError
        quantidade = 0
        for _ in reader.pages:
            quantidade += 1
            if quantidade > paginas:
                raise ValueError
        if not quantidade:
            raise ValueError
        proibidos = {'/A', '/AA', '/OpenAction', '/JS', '/JavaScript', '/EmbeddedFiles', '/EF',
                     '/RichMedia', '/XFA', '/AcroForm', '/Launch', '/URI', '/GoToR', '/SubmitForm',
                     '/ImportData', '/Sound', '/Movie', '/EmbeddedFile'}
        visitados = set()
        fila = [(reader.trailer, 0)]
        for geracao, objetos in reader.xref.items():
            if geracao != 65535:
                fila.extend((IndirectObject(i, geracao, reader), 0) for i in objetos if i)
        fila.extend((IndirectObject(i, 0, reader), 0) for i in reader.xref_objStm)
        passos = 0
        while fila:
            objeto, nivel = fila.pop()
            passos += 1
            if passos > 100000 or nivel > 100:
                raise ValueError
            if isinstance(objeto, IndirectObject):
                chave = (objeto.idnum, objeto.generation)
                if chave in visitados:
                    continue
                visitados.add(chave)
                objeto = objeto.get_object()
            if isinstance(objeto, DictionaryObject):
                if proibidos.intersection(objeto.keys()) or str(objeto.get('/Type', '')) == '/EmbeddedFile':
                    raise ValueError
                fila.extend((valor, nivel + 1) for valor in objeto.values())
            elif isinstance(objeto, ArrayObject):
                fila.extend((valor, nivel + 1) for valor in objeto)
    return 'application/pdf'


if __name__ == '__main__':
    try:
        job = limitar_memoria()
        resultado = validar(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
        print(json.dumps({'tipo': resultado}))
    except Exception:
        print('{}')
        sys.exit(1)
