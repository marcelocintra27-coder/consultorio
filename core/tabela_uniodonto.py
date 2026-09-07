from decimal import Decimal

FATOR_US_UNIODONTO = Decimal('0.1712')
NOME_CONVENIO_UNIODONTO = 'Uniodonto'

# codigo, nome, categoria, valor_us, valor_reais (R$ oficial colado)
LOTE_PROCEDIMENTOS_UNIODONTO = (
    ('84000031', 'Aplicação de cariostático', 'nao_classificada', '163.56', '28.00'),
    ('84000171', 'Controle de cárie incipiente (crianças até 4 anos)', 'nao_classificada', '200.00', '34.24'),
    ('84000201', 'Remineralização', 'nao_classificada', '375.00', '64.20'),
    ('83000062', 'Coroa de policarbonato em dente decíduo', 'nao_classificada', '344.00', '58.89'),
    ('87000067', 'Coroa de policarbonato em dente permanente', 'nao_classificada', '344.00', '58.89'),
    ('83000046', 'Coroa de aço em dente decíduo', 'nao_classificada', '344.00', '58.89'),
    ('87000059', 'Coroa de aço em dente permanente', 'nao_classificada', '344.00', '58.89'),
    ('83000020', 'Coroa de acetato em dente decíduo', 'nao_classificada', '525.71', '90.00'),
    ('87000040', 'Coroa de acetato em dente permanente', 'nao_classificada', '344.00', '58.89'),
    ('85100013', 'Capeamento pulpar direto', 'nao_classificada', '100.00', '17.12'),
    ('83000127', 'Pulpotomia em dente decíduo', 'nao_classificada', '379.67', '65.00'),
    ('83000151', 'Tratamento endodôntico em dente decíduo', 'nao_classificada', '899.53', '154.00'),
    ('83000089', 'Exodontia simples de decíduo', 'nao_classificada', '292.05', '50.00'),
    (
        '83000097',
        'Mantenedor de espaço fixo (Somente Empresas: ADUFG e Hypera)',
        'nao_classificada',
        '1000.00',
        '171.20',
    ),
    ('81000014', 'Condicionamento em Odontologia', 'nao_classificada', '192.76', '33.00'),
    ('83000135', 'Restauração atraumática em dente decíduo', 'nao_classificada', '125.00', '21.40'),
    ('85100080', 'Restauração atraumática em dente permanente', 'nao_classificada', '125.00', '21.40'),
    (
        '82000700',
        'Estabilização por meio de contenção física e/ou mecânica',
        'nao_classificada',
        '119.86',
        '20.52',
    ),
    (
        '84000058',
        'Aplicação de selante - técnica invasiva - Empresa Hypera',
        'nao_classificada',
        '210.28',
        '36.00',
    ),
    (
        '84000112',
        'Aplicação tópica de verniz fluoretado - Empresa Hypera',
        'nao_classificada',
        '200.00',
        '34.24',
    ),
    ('85100137', 'Restauração em ionômero de vidro - 1 face', 'dentistica', '175.23', '30.00'),
    ('85100145', 'Restauração em ionômero de vidro - 2 faces', 'dentistica', '123.77', '21.19'),
    ('85100153', 'Restauração em ionômero de vidro - 3 faces', 'dentistica', '123.77', '21.19'),
    ('85100161', 'Restauração em ionômero de vidro - 4 faces', 'dentistica', '123.77', '21.19'),
    ('85200085', 'Restauração temporária / tratamento expectante', 'dentistica', '100.00', '17.12'),
    ('85100099', 'Restauração de amálgama - 1 face', 'dentistica', '115.01', '19.69'),
    ('85100102', 'Restauração de amálgama - 2 faces', 'dentistica', '200.00', '34.24'),
    ('85100110', 'Restauração de amálgama - 3 faces', 'dentistica', '250.00', '42.80'),
    ('85100129', 'Restauração de amálgama - 4 faces', 'dentistica', '275.00', '47.08'),
    ('85100196', 'Restauração em resina fotopolimerizável 1 face', 'dentistica', '233.64', '40.00'),
    ('85100200', 'Restauração em resina fotopolimerizável 2 faces', 'dentistica', '321.26', '55.00'),
    ('85100218', 'Restauração em resina fotopolimerizável 3 faces', 'dentistica', '449.77', '77.00'),
    ('85100226', 'Restauração em resina fotopolimerizável 4 faces', 'dentistica', '578.27', '99.00'),
    ('85100064', 'Faceta direta em resina fotopolimerizável', 'dentistica', '525.70', '90.00'),
    ('85400211', 'Núcleo de preenchimento', 'dentistica', '280.37', '48.00'),
    (
        '85100021',
        'Clareamento dentário caseiro - por Arcada = Planos específicos com Rol Ampliado e Empresa APEG',
        'dentistica',
        '937.50',
        '160.50',
    ),
    ('85200042', 'Pulpotomia em dentes permanentes', 'endodontia', '250.00', '42.80'),
    (
        '85200166',
        'Tratamento endodôntico unirradicular (Radiografias de diagnóstico e final inclusas)',
        'endodontia',
        '835.28',
        '143.00',
    ),
    (
        '85200140',
        'Tratamento endodôntico birradicular (Radiografias de diagnóstico e final inclusas)',
        'endodontia',
        '1028.04',
        '176.00',
    ),
    (
        '85200158',
        'Tratamento endodôntico multirradicular (Radiografias de diagnóstico e final inclusas)',
        'endodontia',
        '2056.07',
        '352.00',
    ),
    (
        '85200115',
        'Retratamento endodôntico unirradicular (Radiografias de diagnóstico e final inclusas)',
        'endodontia',
        '1185.75',
        '203.00',
    ),
    (
        '85200093',
        'Retratamento endodôntico birradicular (Radiografias de diagnóstico e final inclusas)',
        'endodontia',
        '1869.16',
        '320.00',
    ),
    (
        '85200107',
        'Retratamento endodôntico multirradicular (Radiografias de diagnóstico e final inclusas)',
        'endodontia',
        '2686.92',
        '460.00',
    ),
    ('85200123', 'Tratamento de perfuração endodôntica', 'endodontia', '876.17', '150.00'),
    ('85200077', 'Remoção de núcleo intrarradicular', 'endodontia', '584.11', '100.00'),
    ('85200050', 'Remoção de corpo estranho intracanal', 'endodontia', '467.29', '80.00'),
    (
        '85200131',
        'Tratamento endodôntico de dente com rizogênese incompleta',
        'endodontia',
        '199.30',
        '34.12',
    ),
    ('85200026', 'Preparo para núcleo intrarradicular', 'endodontia', '233.64', '40.00'),
    ('85300047', 'Raspagem supra gengival', 'periodontia', '120.04', '20.55'),
    ('85300039', 'Raspagem sub-gengival/alisamento radicular', 'periodontia', '250.00', '42.80'),
    ('85300012', 'Dessensibilização dentária', 'periodontia', '60.00', '10.27'),
    ('82000921', 'Gengivectomia', 'periodontia', '563.00', '96.39'),
    ('82000948', 'Gengivoplastia', 'periodontia', '563.00', '96.39'),
    ('82000212', 'Cirurgia para aumento de coroa clínica', 'periodontia', '899.53', '154.00'),
    ('82000417', 'Cirurgia periodontal a retalho', 'periodontia', '583.00', '99.81'),
    ('82000557', 'Cunha proximal', 'periodontia', '344.00', '58.89'),
    ('82001464', 'Sepultamento radicular', 'periodontia', '383.00', '65.57'),
)


def popular_convenio_e_tabela(convenio_model, procedimento_model):
    convenio, _ = convenio_model.objects.get_or_create(
        nome=NOME_CONVENIO_UNIODONTO,
        defaults={
            'ativo': True,
            'usa_tabela_oficial': True,
        },
    )
    if not getattr(convenio, 'usa_tabela_oficial', False):
        convenio.usa_tabela_oficial = True
        convenio.save(update_fields=['usa_tabela_oficial'])
    for codigo, nome, categoria, valor_us, valor_reais in LOTE_PROCEDIMENTOS_UNIODONTO:
        procedimento_model.objects.update_or_create(
            codigo=codigo,
            defaults={
                'nome': nome,
                'categoria': categoria,
                'valor_us': Decimal(valor_us),
                'valor_reais': Decimal(valor_reais),
                'fator_us': FATOR_US_UNIODONTO,
                'ativo': True,
            },
        )
    return convenio
