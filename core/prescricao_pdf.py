"""PDF em memória: conteúdo assinado e retificações, sem novo armazenamento."""
from html import escape
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether, PageBreak, CondPageBreak
from django.utils import timezone


def gerar_pdf_prescricao(ficha, assinatura, retificacoes):
    fontes = Path(reportlab.__file__).parent / 'fonts'
    if 'Prescricao' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('Prescricao', str(fontes / 'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('PrescricaoNegrito', str(fontes / 'VeraBd.ttf')))
        pdfmetrics.registerFontFamily('Prescricao', normal='Prescricao', bold='PrescricaoNegrito')
    corpo = ParagraphStyle('corpo', fontName='Prescricao', fontSize=10, leading=15, spaceAfter=6, splitLongWords=True)
    titulo = ParagraphStyle('titulo', parent=corpo, fontName='PrescricaoNegrito', fontSize=19, leading=24, textColor=colors.HexColor('#0B6E8E'), spaceAfter=14)
    subtitulo = ParagraphStyle('subtitulo', parent=corpo, fontName='PrescricaoNegrito', fontSize=11, leading=16, spaceBefore=12)
    pequeno = ParagraphStyle('pequeno', parent=corpo, fontSize=7, leading=10, textColor=colors.HexColor('#4B5563'))

    def par(texto, estilo=corpo):
        return Paragraph(escape(str(texto or '')).replace('\n', '<br/>'), estilo)

    def assinatura_blocos(sig, nome, cro):
        with sig.imagem.open('rb') as arquivo:
            imagem = Image(BytesIO(arquivo.read()))
        fator = min((65 * mm) / imagem.imageWidth, (20 * mm) / imagem.imageHeight, 1)
        imagem.drawWidth = imagem.imageWidth * fator
        imagem.drawHeight = imagem.imageHeight * fator
        imagem.hAlign = 'LEFT'
        return KeepTogether([
            Spacer(1, 7 * mm), imagem,
            par(f'{nome} - CRO {cro}'),
            par('Assinatura manuscrita registrada em ' + timezone.localtime(sig.assinado_em).strftime('%d/%m/%Y %H:%M'), pequeno),
            par('Integridade conferida. Hash do conteúdo:', pequeno),
            par(sig.hash_conteudo, pequeno),
        ])

    saida = BytesIO()
    documento = SimpleDocTemplate(saida, pagesize=A4, leftMargin=22*mm, rightMargin=22*mm, topMargin=22*mm, bottomMargin=21*mm, title=f'Prescrição {ficha.pk}', author=ficha.nome_profissional)
    blocos = [par('Prescrição', titulo), par(f'Paciente: {ficha.nome_paciente}')]
    if ficha.cpf_paciente:
        blocos.append(par(f'CPF: {ficha.cpf_paciente}'))
    if ficha.data_nascimento_paciente:
        blocos.append(par('Nascimento: ' + ficha.data_nascimento_paciente.strftime('%d/%m/%Y')))
    blocos += [par(f'Profissional: {ficha.nome_profissional} - CRO {ficha.cro}'), par('Emissão: ' + timezone.localtime(ficha.emitida_em).strftime('%d/%m/%Y %H:%M')), Spacer(1, 4*mm)]
    for numero, item in enumerate(ficha.itens.all(), 1):
        blocos += [CondPageBreak(25*mm), par(f'{numero}. {item.medicamento}', subtitulo)]
        for rotulo, campo in [('Concentração / apresentação', 'concentracao_apresentacao'), ('Quantidade', 'quantidade'), ('Posologia', 'posologia'), ('Via', 'via'), ('Duração', 'duracao'), ('Orientações', 'orientacoes')]:
            if getattr(item, campo):
                blocos.append(par(rotulo + ': ' + getattr(item, campo)))
    if ficha.texto_livre:
        blocos += [CondPageBreak(25*mm), par('Texto da prescrição', subtitulo), par(ficha.texto_livre)]
    if ficha.orientacoes:
        blocos += [CondPageBreak(25*mm), par('Orientações gerais', subtitulo), par(ficha.orientacoes)]
    blocos.append(assinatura_blocos(assinatura, ficha.nome_profissional, ficha.cro))
    for numero, registro in enumerate(retificacoes, 1):
        blocos += [PageBreak(), par(f'Retificação {numero}', titulo), par(f'Anotação complementar vinculada à prescrição {ficha.pk}.'), par(f'Paciente: {ficha.nome_paciente}'), par('Justificativa', subtitulo), par(registro.justificativa), CondPageBreak(25*mm), par('Anotação complementar', subtitulo), par(registro.conteudo), assinatura_blocos(registro.assinatura, registro.nome_profissional, registro.cro)]

    def rodape(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor('#D1D5DB'))
        canvas.line(22*mm, 17*mm, A4[0]-22*mm, 17*mm)
        canvas.setFont('Prescricao', 8)
        canvas.drawString(22*mm, 12*mm, f'Prescrição {ficha.pk} - {ficha.nome_paciente[:50]}')
        canvas.drawRightString(A4[0]-22*mm, 12*mm, f'Página {doc.page}')
        canvas.restoreState()
    documento.build(blocos, onFirstPage=rodape, onLaterPages=rodape)
    return saida.getvalue()
