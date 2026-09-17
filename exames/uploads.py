import tempfile
from pathlib import Path
from django.core.files.uploadedfile import UploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopUpload
from .config import limite
from .storage import pasta_privada, conferir_espaco


class UploadPrivado(FileUploadHandler):
    """Um arquivo por requisição, privado desde o primeiro byte recebido."""
    def __init__(self, request):
        super().__init__(request)
        self.quantidade = 0
        self.temporarios = []

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.quantidade += 1
        if self.quantidade > 1 or self.field_name != 'arquivo':
            self.request.exames_upload_erro = True
            raise StopUpload(connection_reset=False)
        conferir_espaco(limite('EXAMES_MAX_BYTES', 20 * 1024 * 1024))
        self.arquivo = tempfile.NamedTemporaryFile(mode='w+b', prefix='recebimento-', dir=pasta_privada('temporarios'), delete=False)
        self.temporarios.append(self.arquivo)
        self.total = 0

    def receive_data_chunk(self, raw_data, start):
        self.total += len(raw_data)
        if self.total > limite('EXAMES_MAX_BYTES', 20 * 1024 * 1024):
            self.request.exames_upload_erro = True
            raise StopUpload(connection_reset=False)
        self.arquivo.write(raw_data)
        return None

    def file_complete(self, file_size):
        self.arquivo.flush()
        self.arquivo.seek(0)
        return UploadedFile(self.arquivo, self.file_name, self.content_type, file_size)

    def fechar(self):
        for arquivo in self.temporarios:
            arquivo.close()
            Path(arquivo.name).unlink(missing_ok=True)
