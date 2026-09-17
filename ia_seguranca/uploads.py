from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler, StopUpload


class LimiteAudioTranscricaoUploadHandler(FileUploadHandler):
    """Interrompe áudio excessivo antes do armazenamento temporário do Django."""

    def __init__(self, request=None):
        super().__init__(request)
        self._audio_transcricao = False
        self._bytes_recebidos = 0

    def new_file(self, field_name, *args, **kwargs):
        super().new_file(field_name, *args, **kwargs)
        self._audio_transcricao = bool(
            field_name == 'audio'
            and self.request.path.startswith('/ia_seguranca/consultas/')
            and self.request.path.endswith('/transcrever/')
        )

    def receive_data_chunk(self, raw_data, start):
        if self._audio_transcricao:
            self._bytes_recebidos += len(raw_data)
            if self._bytes_recebidos > settings.IA_AUDIO_MAX_BYTES:
                raise StopUpload(connection_reset=False)
        return raw_data

    def file_complete(self, file_size):
        # Este handler só limita o fluxo; o handler seguinte cria o arquivo.
        return None
