"""Utilitário manual de diagnóstico do Whisper.

O guard abaixo evita execução por descoberta/importação da suíte Django.
Use explicitamente: ``python testar_whisper.py``.
"""


def main():
    import time

    from faster_whisper import WhisperModel

    arquivo = 'teste2.wav'
    print('Carregando modelo...')
    modelo = WhisperModel('small', device='cpu', compute_type='int8')

    print('Transcrevendo...')
    inicio = time.time()
    segmentos, _info = modelo.transcribe(arquivo, language='pt')

    texto = ''
    for segmento in segmentos:
        print(f'[{segmento.start:.1f}s -> {segmento.end:.1f}s] {segmento.text}')
        texto += segmento.text

    print('=' * 40)
    print('TEXTO COMPLETO:')
    print(texto.strip())
    print('=' * 40)
    print(f'Tempo: {round(time.time() - inicio, 1)}s')


if __name__ == '__main__':
    main()
