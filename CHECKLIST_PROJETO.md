# Checklist do projeto — Consultório Odontológico

## Regra de uso permanente

Antes de iniciar trabalho novo, consultar este checklist e o
[`PLANO_MESTRE.md`](PLANO_MESTRE.md). Não pular etapas, não mudar decisões
aprovadas sem avisar e não marcar item concluído sem atender seus critérios e
executar as validações listadas.

Legenda:

- `[ ]` Pendente
- `[~]` Em andamento
- `[x]` Concluído
- `[!]` Bloqueado

## Base atual e segurança

- [x] Correções A1–A8 implementadas.
  - Critérios: autorização clínica e vínculo de consulta; consentimento de IA;
    proteção de assinatura; menor privilégio do prontuário; settings seguros;
    `registro_id` validado; dependências/deploy documentados; evolução por voz
    com assinatura e auditoria oficiais.
  - Validação registrada: testes de segurança, migração
    `ia_seguranca.0002_registroauditoriaia_consulta`, `check` e
    `makemigrations --check --dry-run`.

- [x] Correções pós-auditoria de alto risco implementadas.
  - Critérios: `is_staff` não é administrador global; status de agenda é
    autorizado e auditado; upload de áudio tem limite/timeout/validação;
    `testar_whisper.py` não executa durante descoberta de testes.
  - Validação registrada: suíte completa com **62 testes aprovados**;
    `manage.py check` e `makemigrations --check --dry-run` sem erro de schema.

- [x] Documentação mestre criada.
  - Critérios: `PLANO_MESTRE.md` e este arquivo registram estado real,
    segurança, perfis, planejamento e bloqueios de produção.

## Planejamento de interface e permissões

- [x] Aprovar formalmente dashboards e menu lateral por perfil.
  - Critérios: confirmação explícita do usuário para o menu de Secretária,
    Dentista e Administrador descrito no Plano Mestre, incluindo o Design
    System único: tipografia, paleta, ícones, botões, cards, tabelas,
    formulários, modais, alertas, grade de espaçamento, menu lateral,
    cabeçalho, responsividade e acessibilidade.
  - Validação registrada: aprovação explícita do usuário em 11/09/2026.
  - A aprovação não autoriza iniciar implementação visual antes da conclusão
    da próxima etapa oficial.

- [x] Consolidar matriz final de permissões de agenda, pacientes e financeiro.
  - Critérios: documentar cada ação por perfil (ver, criar, editar, cancelar,
    registrar, assinar, financeiro), incluindo o perfil auxiliar existente;
    resolver explicitamente o acesso atual de dentistas ao financeiro antes de
    removê-lo; criar testes de permitido e negado.
  - Decisão aprovada em 11/09/2026: dentista pode visualizar valores e materiais
    e registrar lançamentos operacionais somente em consultas próprias e
    pacientes vinculados. É negado para financeiro administrativo geral, contas
    a pagar, contas a receber gerais, caixa, fechamento, conciliação,
    inadimplência, relatórios financeiros e movimentações de outros dentistas.
    Secretária continua sem financeiro administrativo nem acesso clínico;
    administrador mantém financeiro completo; auxiliar mantém as restrições
    clínicas, financeiras e de status já aprovadas.
  - Decisões aprovadas em 11/09/2026: dentista pode cadastrar e editar somente
    dados cadastrais de pacientes vinculados às suas consultas; auxiliar tem
    somente leitura da agenda relacionada ao seu trabalho e de identificação e
    dados cadastrais básicos de pacientes vinculados. Auxiliar não pode criar ou
    editar pacientes, nem criar/remarcar/cancelar consulta ou alterar status.
  - Matriz completa registrada no Plano Mestre e aplicada nas rotas existentes
    de agenda, pacientes, consulta e operação financeira. Validação registrada
    em 11/09/2026: testes de permitido/negado por perfil, `manage.py check`,
    `makemigrations --check --dry-run` e suíte completa com 67 testes aprovados.

- [x] Criar navegação comum por perfil.
  - Critérios: menu lateral/recolhível, cabeçalho e rotas visíveis somente ao
    perfil correto; nenhum link clínico para secretária; nenhum financeiro
    administrativo para dentista; aplicar os tokens e padrões de Design System
    aprovados; testes de renderização, responsividade básica e autorização
    passam.
  - Validação registrada em 11/09/2026: menu lateral responsivo e cabeçalho
    comum implementados; 6 testes específicos de navegação aprovados;
    `manage.py check`, `makemigrations --check --dry-run` e suíte completa com
    68 testes aprovados.

- [x] Implementar dashboard da secretária.
  - Estado: concluído em 11/09/2026. Exibe a agenda diária e os atalhos já
    autorizados para Agenda e Pacientes; a suíte completa teve 70 testes
    aprovados.
  - [x] Agenda diária com contagens dos status já existentes e lista
    operacional de consultas.
  - [x] Atalhos para agendar consulta, consultar agenda, cadastrar e buscar
    pacientes.
  - [x] Sem valores, pagamentos ou dados clínicos; testes de acesso e
    regressão aprovados.
  - [x] Confirmações de consulta com status próprio, transição autorizada e
    auditoria.
  - [x] Chegada/atendimento administrativo com status próprio, transição
    autorizada e auditoria.

- [x] Redesenhar ficha da consulta por contexto.
  - Critérios atendidos: blocos separados de Atendimento, Prontuário e
    documentos, Operação da própria consulta/Financeiro e Auditoria;
    Secretária vê somente Atendimento; Dentista vê o contexto vinculado e
    operação própria; Administrador vê o contexto administrativo autorizado.
  - Validação registrada em 11/09/2026: matriz de permissões com 9 testes,
    `manage.py check`, `makemigrations --check --dry-run` e suíte completa com
    71 testes aprovados.

- [x] Implementar dashboard clínico do dentista.
  - Critérios atendidos: agenda própria, atendimentos com presença registrada,
    anamneses aguardando dentista, autorizações em rascunho das próprias
    consultas e atalhos para rotas clínicas existentes; não há financeiro
    administrativo nem dados de outros dentistas.
  - Observação: `RegistroEvolucaoClinica` não tem vínculo direto com
    `Consulta`; portanto, nenhum indicador de “evolução pendente” foi inferido
    ou criado nesta etapa.
  - Validação registrada em 11/09/2026: teste específico de dashboard e matriz
    de permissões, `manage.py check`, `makemigrations --check --dry-run` e
    suíte completa com 72 testes aprovados.

- [x] Implementar administração própria e dashboard administrativo.
  - Critérios atendidos: painel agregado e portal exclusivo de superusuário
    para usuários/grupos/perfis, profissionais/salas/disponibilidade,
    configurações e auditorias de agenda e IA/voz; não há CRUD paralelo nem
    exposição pelo portal a Secretária, Dentista, Auxiliar ou `is_staff` sem
    superusuário.
  - Validação registrada em 11/09/2026: teste de privilégio por perfil,
    preservação dos atalhos Tabela/Repasse Uniodonto, `manage.py check`,
    `makemigrations --check --dry-run` e suíte completa com 73 testes
    aprovados.

## Agenda e pacientes

- [x] Criar fluxo próprio de remarcação (A-005 / R-002); cancelamento via status preservado.
  - Implementado e certificado em 18/09/2026, após revisão independente do
    Claude e certificação do GPT coordenador: mesma `Consulta` / mesmo `pk`,
    UPDATE de data/hora, paciente/dentista/vínculos preservados e auditoria
    antes/depois com usuário, timestamp e motivo opcional.
  - Somente `agendada` e `confirmada` podem ser remarcadas; `confirmada` volta
    a `agendada`. Presente, realizada, faltou e cancelada são bloqueadas.
    Permissões no servidor: secretária, administrador e dentista responsável;
    auxiliar e dentista alheio recebem 403. Sem alteração de prontuário.
- [x] Auditar criação no fluxo web `agendar_consulta` (A-005 / R-003).
  - Implementada e certificada: `AuditoriaConsulta` registra usuário,
    timestamp, paciente, dentista, data/horários e origem, atomicamente com
    a criação. Nenhuma auditoria histórica artificial foi criada.
- [x] Testar alteração HTTP válida para `faltou` (A-005 / R-004).
  - Implementado e certificado, incluindo permissões e auditoria.
- [x] Validar conflito compartilhado na criação e remarcação (A-005).
  - Mesmo dentista/data; bloqueia sobreposição, permite consecutivos,
    ignora cancelada, exclui a própria consulta e exige `hora_fim > hora_inicio`.
    Conflito de sala e notificações e-mail/WhatsApp permanecem fora do escopo.
- [x] Proteger seletivamente `ConsultaAdmin` (A-005).
  - Criação desabilitada; data, hora_inicio, hora_fim, status e dentista
    protegidos; demais campos administrativos preservados.
  - Evidências A-005: 18 testes específicos aprovados; execução conjunta
    anterior com 78 aprovados; `manage.py check` sem erros, somente W047
    conhecido e não silenciado; `makemigrations --check --dry-run`:
    `No changes detected`. Nenhuma migration necessária.
  - A exibição da trilha `AuditoriaConsulta` na ficha permanece condicionada
    a `pode_financeiro` (administrador).

- [x] Criar confirmações e atendimento administrativo.
  - Critérios atendidos: status próprio/documentado, sem dado clínico, filtro
    por situação na agenda, transições autorizadas e testes aprovados.

- [ ] Definir uso da disponibilidade de salas.
  - Critérios: decidir se `Disponibilidade` seguirá apenas no Django Admin ou
    ganhará fluxo web; se ganhar fluxo, validar conflito de horários, perfil
    autorizado, auditoria e testes antes de expor rotas.

- [ ] Revisar a lista de pacientes por perfil.
  - Critérios: secretária recebe apenas ações cadastrais/administrativas;
    dentista recebe atalhos clínicos vinculados; administrador segue matriz
    aprovada; testes passam.

## Prontuário, documentos e mídia

- [ ] Consolidar visão clínica do paciente.
  - Critérios: anamnese, evolução, planos e autorizações navegáveis por
    dentista vinculado; secretária/auxiliar negados; assinaturas autorizadas.

- [x] Definir tratamento do modelo legado `Evolucao`.
  - Decisão aprovada em 14/09/2026: preservar integralmente o histórico,
    sem conversão nem atribuição automática de assinatura. Novos registros
    utilizam `RegistroEvolucaoClinica`; inclusão pelo Admin legado bloqueada.
    Leitura do legado identificada separadamente na ficha clínica e no Admin,
    restrita à autorização clínica existente; edição/exclusão bloqueadas.
  - Inventário local: 0 registros em `Evolucao`, 8 evoluções oficiais,
    20 assinaturas. Testes usam também registros legados não vazios.

- [x] Definir ciclo de vida do anexo de autorização nesta etapa.
  - Decisão aprovada em 14/09/2026: preservar o campo
    `FichaAutorizacaoCusto.arquivo` e dados existentes, sem novo upload,
    armazenamento ou ampliação de exposição. Inventário: 1 anexo preenchido.
    Política completa de armazenamento, acesso, auditoria, backup e retenção
    permanece pendente de etapa específica; não foi implementada aqui.

- [x] Definir verificação e imutabilidade de documentos assinados.
  - Implementado em 14/09/2026: verificação somente leitura com os
    serializadores históricos, alertas de divergência/ausência e bloqueio de
    operações dependentes da integridade; proteção de originais, assinaturas,
    itens e profissionais relacionados, inclusive no Admin e exclusões em
    cascata pelo ORM. Conclusão legítima da anamnese pelo dentista preservada.
  - `RetificacaoDocumento`: anotação complementar assinada pelo profissional,
    com exatamente um vínculo protegido ao original, autoria, data/hora,
    justificativa e conteúdo; imutável, auditável e sem substituir consentimento,
    alterar procedimentos ou movimentar financeiro. Migration aditiva
    `core.0027_retificacao_documento` aplicada, sem conversão de dados.
  - Validação: 25 testes específicos e suíte completa com 150 testes aprovados;
    hashes/conteúdos das 9 tabelas clínicas inventariadas idênticos antes/depois
    da migration. `check` apenas com o warning SQLite conhecido `models.W047`;
    `makemigrations --check --dry-run` sem pendências e `git diff --check` sem erros.
    Senhas de teste usam hasher rápido apenas no processo de testes; configuração
    de autenticação da aplicação preservada.
  - Validação visual manual concluída com sucesso, conforme confirmação do
    usuário: documento clínico original preservado e assinatura original
    visível; retificação registrada separadamente e vinculada ao original,
    contendo justificativa, anotação complementar, profissional/CRO e assinatura;
    informação de integridade pelos hashes registrados e ação
    “Registrar retificação” confirmadas no navegador.

- [x] Implementar prescrições — recorte aprovado do Item 10, concluído em 15/09/2026.
  - Paciente/profissional/CRO, múltiplos medicamentos e texto livre, rascunho
    editável, assinatura imutável, histórico/auditoria, hash de conteúdo/imagem,
    retificação vinculada, impressão e PDF com verificação de integridade.
  - Permissões clínicas preservadas; emissão exige dentista ativo vinculado.
    Admin sem perfil prescritor não emite e não altera/exclui documento assinado.
  - Migration `0028_prescricoes` conferida: já estava aplicada no banco local;
    nenhuma migration nova ou conversão histórica foi necessária nesta retomada.
  - Recuperação do trabalho preservado no stash, mantendo as alterações
    posteriores de CPF opcional e digitalização. Ver relatório da retomada em
    `RELATORIO_ITEM10_PRESCRICOES.md` para arquivos e validações finais.
  - Navegador validado com banco separado e dados fictícios: rascunho sem
    assinatura, adição de medicamento, CRO obrigatório, emissão e impressão.
    PDF de múltiplos medicamentos/retificação e texto longo conferido visualmente.
  - Validação final: 28 testes de prescrições e 25 de integridade aprovados;
    suíte completa com 178 testes e zero falhas. Banco real: 64 tabelas com
    linhas idênticas à cópia inicial. `check` somente com `models.W047` conhecido.

- [x] Implementar imagens e exames — implementação e testes locais concluídos em 16/09/2026.
  - Proposta aprovada antes do código: JPEG/PNG/PDF, 20 MiB por arquivo,
    40 megapixels e 100 páginas; paciente obrigatório e consulta opcional
    autorizada do mesmo paciente; acesso clínico por perfil/vínculo.
  - App aditivo `exames`: armazenamento privado fora de `/media/`, validação
    isolada com limites de memória/tempo, inspeção ClamAV local, quarentena
    sem liberação manual, SHA-256 antes de download e auditoria imutável.
  - Original e metadados imutáveis; correção cria novo registro vinculado;
    invalidação exige justificativa. Nenhuma exclusão física de originais.
    Política inicial de retenção preserva arquivos e histórico. Temporários
    de requisições são limpos; comando próprio trata abandonados acima de 24h.
  - Migration aditiva `exames.0001_initial` aplicada localmente: duas tabelas,
    sem conversão de dados anteriores. Prescrições não foram alteradas.
  - Validação: 37 testes específicos e suíte completa de 215 testes aprovados;
    check apenas com `models.W047` conhecido, sem migrations pendentes.
    Navegador conferido em desktop e 390px, exclusivamente com dados fictícios.
    Restauração local de banco e arquivos validada em base separada.
  - Preservação: 64 tabelas preexistentes conferidas, além de `sqlite_sequence`;
    dados anteriores preservados, somente acréscimos técnicos de migration,
    content types e permissões. 1.354 arquivos de mídia preservados byte a byte.
  - Relatório e inventário de arquivos: `RELATORIO_ITEM10_IMAGENS_EXAMES.md`.

- [!] Ativação operacional de imagens/exames depende de infraestrutura validada.
  - Em 19/09/2026, no Windows local, `clamd` foi confirmado Running/Automatic;
    `main.cvd`, `daily.cvd` e `bytecode.cvd` existem e passaram na verificação do
    `sigtool`. A porta 3310 escuta somente em 127.0.0.1; PING, INSTREAM inofensivo
    e a chamada `exames.antivirus.inspecionar` responderam com sucesso.
    A detecção real de amostra de teste, o fluxo HTTP completo e a disponibilidade
    após reinício ainda não foram homologados. Dois processos `clamd` aparecem
    ouvindo na mesma porta; verificar a duplicidade sem interromper o serviço.
    As tarefas agendadas foram informadas pelo usuário, mas sua consulta nesta
    sessão retornou acesso negado. Sem motor disponível, uploads novos permanecem
    em quarentena e sem download.
  - Volume persistente privado, capacidade, backup/restauração em produção,
    prazos definitivos de retenção/quarentena e responsáveis continuam pendentes.
    Nenhum deploy, provisionamento ou mudança de configuração de produção foi feito.

## Melhorias de segurança e operação

- [ ] Eliminar inserção de JSON insegura na ficha da consulta.
  - Critérios: substituir os usos de `json.dumps(... )|safe` por mecanismo de
    serialização seguro no template; cobrir conteúdo com caracteres de escape e
    preservar o preenchimento de valores na tela.

- [ ] Definir proteção contra abuso de autenticação e links públicos.
  - Critérios: aprovar mecanismo de rate limit compatível com o ambiente,
    aplicar a login e endpoints públicos sensíveis sem bloquear operação
    legítima; criar testes ou configuração verificável.

- [ ] Definir logs e monitoramento de produção.
  - Critérios: registrar eventos de segurança/falhas sem dados clínicos ou
    segredos, definir retenção/acesso e testar a emissão de evento relevante.

- [ ] Completar reprodutibilidade das dependências.
  - Critérios: avaliar lock de transitivas e hashes compatíveis com Python e
    Docker atuais; não alterar versões sem teste de build e suíte completa.

## Financeiro administrativo completo

- [x] Estruturar contas a receber e recebimentos de pacientes.
  - Critérios atendidos: título vinculado quando aplicável, vencimento, saldo,
    parcelas, baixa parcial/total, desconto, estorno compensatório, operador,
    forma de pagamento, recibo único e auditoria; testes de integridade e
    autorização. Validação registrada: migration aditiva
    `core.0021_contareceber_parcelacontareceber_recebimentopaciente_and_more`,
    `manage.py check`, `makemigrations --check --dry-run` e suíte completa com
    **80 testes aprovados**.
  - Comprovante por upload permanece intencionalmente bloqueado até existir
    política aprovada de armazenamento persistente, autorização, tipos,
    tamanho e retenção; nenhum arquivo de comprovante foi aceito nesta etapa.

- [x] Estruturar inadimplência.
  - Critérios atendidos: parcelas vencidas com saldo efetivamente aberto após
    recebimentos, descontos e estornos; cálculo de atraso por vencimento,
    filtros por texto/faixa e histórico financeiro existente sem exposição de
    dados clínicos. Acesso exclusivo de administrador e isolamento dos demais
    financeiros foram validados. Não foi criado modelo nem migration, pois
    `AuditoriaFinanceira` representa o histórico necessário.
  - Validação registrada: 10 testes específicos (vencida, parcial, liquidada,
    descontada, estornada, atraso, filtros, histórico e permissões),
    `manage.py check`, `makemigrations --check --dry-run` e suíte completa com
    **90 testes aprovados**.

- [x] Estruturar contas a pagar e fornecedores.
  - Critérios atendidos: fornecedor, categoria, competência, vencimento,
    recorrência informativa, situação, responsável, aprovação, baixa
    transacional com saldo e chave única, e auditoria. Migration aditiva
    `core.0022_contas_pagar_fornecedores` aplicada, sem alterar dados de
    locação. Comprovante por upload permanece bloqueado até política segura.
  - Validação registrada: 12 testes específicos para criação, aprovação,
    baixa parcial/total, excesso, duplicidade, auditoria, permissões,
    recorrência, ausência de upload e preservação de locação; `check`,
    `makemigrations --check --dry-run` e suíte completa com **102 testes
    aprovados**.

- [x] Evoluir despesas para fluxo financeiro completo.
  - Critérios: diferenciar competência de pagamento, integrar a contas a pagar
    e preservar rateio existente entre dentistas sem regressão.
  - Validação: vínculo opcional e auditável para despesas novas, históricos sem
    vínculo preservados, migration aditiva `locacao.0009_despesa_conta_pagar`,
    5 testes específicos e suíte completa com **107 testes aprovados**.

- [x] Implementar fluxo e fechamento de caixa.
  - Critérios atendidos: abertura única diária, saldo inicial, entradas e
    saídas automáticas de recebimentos, estornos e baixas válidas, ajustes e
    compensações manuais com motivo, saldo esperado/contado, diferença com
    justificativa obrigatória, responsável, fechamento imutável e trilha de
    auditoria exclusiva do administrador.
  - Validação: migration aditiva `core.0023_fluxo_caixa` aplicada; 4 testes
    específicos (abertura, ajustes, recebimento/estorno/baixa automáticos,
    imutabilidade e permissões); `manage.py check`,
    `makemigrations --check --dry-run` e suíte completa com **111 testes
    aprovados**.

- [x] Implementar conciliação.
  - Critérios atendidos: origem manual de extrato, modelos e serviços
    preparados para CSV/OFX sem API bancária, vínculos totais/parciais,
    sugestões não automáticas, bloqueio de duplicidade, taxas/divergências
    separadas, cancelamento lógico e auditoria. Nenhum registro financeiro
    original é alterado ou apagado; acesso exclusivo de administrador.
  - Validação: migrations aditivas `core.0024_conciliacao` e
    `core.0025_integridade_conciliacao` aplicadas; 5 testes
    específicos (total, parcial, duplicidade, CSV/OFX, taxa/divergência,
    cancelamento e permissões), `manage.py check`,
    `makemigrations --check --dry-run` e suíte completa com **116 testes
    aprovados**.

- [x] Implementar formas de pagamento configuráveis.
  - Critérios atendidos: formas iniciais Pix, Dinheiro, Cartão de Débito,
    Cartão de Crédito e Transferência; cadastro, edição, ativação/inativação,
    taxa opcional percentual/fixa, prazo e conta/destino. Formas inativas
    permanecem no histórico e são bloqueadas em novos recebimentos.
  - Preservação e validação: migration aditiva
    `core.0026_formas_pagamento_configuraveis` aplicada, sem converter
    `Consulta.forma_pagamento` ou dados anteriores. Taxas são apenas
    configuração e não geram movimentos duplicados em caixa/conciliação.
    4 testes específicos, `manage.py check`,
    `makemigrations --check --dry-run`, `git diff --check` e suíte completa
    com **120 testes aprovados**.

- [x] Implementar relatórios financeiros.
  - Critérios atendidos: tela administrativa somente leitura com filtro de
    período; visões separadas de realizado/caixa e previsto/competência;
    fluxo de caixa, recebimentos por forma, estornos, descontos, taxas,
    divergências, vencidos, despesas/categoria, fechamentos e repasses.
    Despesas legadas sem `ContaPagar` são incluídas uma vez e despesas
    vinculadas não duplicam valores.
  - Preservação e validação: nenhuma alteração de modelo, banco ou migration;
    sem exportação CSV/PDF. Acesso exclusivo de `is_superuser`, com negação
    para Dentista, Secretária, Auxiliar e `is_staff` sem superusuário. Cinco
    testes específicos, `manage.py check`, `makemigrations --check --dry-run`,
    `git diff --check` e suíte completa com **125 testes aprovados**.

## Produção e infraestrutura

- [x] Validar PostgreSQL local para homologação, sem migrar dados reais.
  - PostgreSQL 17 local em `127.0.0.1:5432`, com banco e usuário exclusivos;
    migrations aplicadas e conexão Django validada. Backup do banco de
    homologação restaurado em banco separado, com estrutura e contagens
    conferidas. SQLite original e backup preservados.
  - Suíte completa no PostgreSQL com `--keepdb`: 241/241 testes aprovados;
    `check`, `makemigrations --check --dry-run` e `migrate --check` aprovados.
    Testes foram ajustados para fechar arquivos sem encerrar a conexão do
    `TestCase`, conferir o comportamento de cada backend e criar seus próprios
    dados iniciais. Detalhes em
    [`RELATORIO_POSTGRESQL_LOCAL.md`](RELATORIO_POSTGRESQL_LOCAL.md).

- [!] Provisionar PostgreSQL para produção.
  - Bloqueio: decisão atual de não contratar/provisionar recursos Render.
  - Critérios para concluir: banco provisionado, `DATABASE_URL` segura,
    migrations aplicadas e restauração testada.

- [!] Provisionar mídia persistente e backup de assinaturas/documentos.
  - Bloqueio: decisão atual de não contratar/provisionar disco persistente.
  - Critérios para concluir: volume configurado em `RENDER_DISK_PATH`, teste de
    sobrevivência a restart e backup/restauração de mídia.

- [!] Configurar SMTP de produção.
  - Bloqueio: credenciais/serviço externo ainda não configurados.
  - Critérios para concluir: segredos no painel, TLS/SSL coerente, envio de
    teste e nenhuma credencial versionada.

- [!] Definir e testar backups completos.
  - Bloqueio: depende de PostgreSQL e mídia persistente.
  - Critérios para concluir: política documentada, cópia protegida, teste de
    restauração de banco e mídia.

- [ ] Validar pré-deploy no Render.
  - Critérios: todos os bloqueios anteriores concluídos; segredos/hosts/domínio
    configurados; `check --deploy`, migrations, `collectstatic`, testes e teste
    de upload/assinatura concluídos; aprovação explícita antes de deploy.

## Regras de execução contínua

- [x] Sem commit, push ou deploy sem autorização explícita.
  - Critério: qualquer alteração Git remota ou deploy exige pedido inequívoco do
    usuário.

- [x] Migrações somente para alteração real de modelo.
  - Critério: toda mudança de modelo inclui migration, `makemigrations --check
    --dry-run`, testes relevantes e instrução de aplicação quando solicitada.

- [x] Segurança e regressão antes de concluir etapa.
  - Critério: testes relevantes, `manage.py check`, revisão de permissões e
    preservação de A1–A8 antes de marcar qualquer etapa futura como concluída.
