# Plano mestre — Consultório Odontológico

## Regra de uso permanente

Antes de qualquer implementação, leia este documento e o
[`CHECKLIST_PROJETO.md`](CHECKLIST_PROJETO.md). Não pule etapas, não altere
decisões aprovadas sem avisar e não marque uma etapa como concluída sem cumprir
os critérios e executar as validações previstas. Se uma solicitação conflitar
com este plano, o conflito deve ser informado antes de qualquer alteração.

Este plano registra o estado real observado no repositório em
`security/fix-a1-a8`. Ele não autoriza commit, push, deploy ou mudança fora da
etapa solicitada.

## Objetivo e arquitetura

O sistema é um gestor para consultório odontológico, com operação de agenda,
cadastro de pacientes, atendimento clínico, documentos assinados, controles
financeiros e locação/rateio entre dentistas.

- **Backend:** Python e Django 6.1.
- **Banco de desenvolvimento:** SQLite (`db.sqlite3`).
- **Apps:** `core`, `locacao` e `ia_seguranca`.
- **Autenticação:** `LoginRequiredMiddleware` protege as rotas por padrão;
  login e os links públicos temporários de anamnese são exceções intencionais.
  `PerfilUsuario` possui dentista, auxiliar e secretária; superusuário é o
  administrador global de negócio.
- **Produção-alvo:** Render com Docker, Gunicorn, WhiteNoise, PostgreSQL,
  disco persistente para mídia e SMTP externo.
- **IA de voz:** `faster-whisper`, `ffmpeg`, processamento local/síncrono e
  registro de auditoria.

## Módulos existentes

| Módulo | Estado real |
|---|---|
| Agenda | Lista diária, criação de consulta, status, cancelamento via status e ficha de consulta. `Disponibilidade` existe como modelo e no Django Admin, mas não tem telas próprias. Não há fluxo próprio de remarcar ou confirmação. |
| Pacientes | Lista, busca, criação e edição de dados cadastrais. |
| Prontuário | Anamnese, evolução clínica oficial (`RegistroEvolucaoClinica`), plano de tratamento, autorização de itens com custo e assinaturas. O modelo legado `Evolucao` continua no banco/Django Admin e não possui tela própria. |
| Documentos e assinaturas | Assinatura manuscrita PNG, hash de conteúdo/imagem, dados de usuário, IP e user-agent; imagens servidas por endpoint autorizado. `FichaAutorizacaoCusto` tem campo de arquivo no modelo, mas ele ainda não está exposto por formulário/fluxo web. |
| Financeiro atual | Contas a receber e a pagar administrativas, parcelas/baixas, recebimentos, descontos, estornos, recibos, fornecedores, categorias, auditorias e inadimplência; além dos pagamentos simples por consulta, materiais, procedimentos/preços, convênios, Uniodonto, repasses, despesas, dívidas e acerto entre dentistas. Ainda não é financeiro completo. |
| Locação | Salas, dentistas, disponibilidade (admin apenas), despesas, dívidas, pagamentos entre dentistas e acerto mensal. |
| IA/voz | Consentimento, transcrição de voz autorizada, auditoria e gravação de evolução assinada. |
| Administração | Painel administrativo e portal próprio, exclusivos de superusuário, com atalhos autorizados para as telas técnicas já registradas no Django Admin. Não há CRUD administrativo paralelo nem relatórios próprios. |

### Funcionalidades ainda não implementadas

- Confirmações de consulta e fluxo próprio de reagendamento.
- Imagens e exames.
- Financeiro completo descrito neste plano.
- Dashboards por perfil.
- Navegação lateral para áreas ainda não implementadas (prontuário global,
  prescrições, imagens/exames e financeiro ainda pendente).

Não apresentar essas funcionalidades como existentes nem criar links ativos sem
implementação, autorização e testes.

### Fluxos especiais existentes

- **Anamnese pública:** uma ficha em rascunho pode gerar URL com token UUID para
  preenchimento sem login. O token expira em 14 dias, pode ser renovado e deixa
  de aceitar preenchimento após o envio. É um link de posse e deve permanecer
  fora de menus de usuários não clínicos.
- **SMTP:** há validação/configuração condicional para produção, mas ainda não
  existe fluxo de e-mail de confirmação, cobrança ou notificação no sistema.
- **Arquivos clínicos:** assinaturas usam endpoint autorizado. O campo de anexo
  de autorização ainda não constitui um módulo de upload/download disponível.

## Perfis e permissões

### Secretária

**Escopo aprovado:** agenda, cadastro/busca de pacientes, marcação,
reagendamento, cancelamento, confirmações e atendimento administrativo.

**Restrições:** não acessa financeiro e não acessa prontuário clínico,
anamnese, evolução, plano, documentos clínicos, assinaturas, imagens, exames
ou prescrições.

**Estado atual relevante:** pode gerir status de agenda; o backend clínico já
nega prontuário. A interface atual ainda mostra alguns atalhos clínicos na
lista de pacientes e deve ser reorganizada em etapa própria.

### Dentista

**Escopo aprovado:** própria agenda, pacientes vinculados, prontuário,
anamnese, evolução, planos, documentos, autorizações, assinaturas, materiais
usados e prescrições; imagens/exames quando implementados.

**Restrições:** acesso clínico somente quando houver vínculo por consulta com o
paciente; não deve receber o financeiro administrativo completo.

**Decisão financeira aprovada em 11/09/2026:** pode visualizar valores e
materiais e registrar lançamentos operacionais somente das próprias consultas
e pacientes vinculados. Não pode acessar financeiro administrativo geral,
contas a pagar, contas a receber gerais, caixa, fechamento de caixa,
conciliação, inadimplência, relatórios financeiros nem movimentações de outros
dentistas.

**Dados cadastrais aprovados em 11/09/2026:** pode cadastrar e editar dados
cadastrais somente de pacientes que tenham consulta vinculada ao seu perfil de
dentista. Não pode alterar cadastro de paciente sem esse vínculo. Esta decisão
não amplia qualquer acesso financeiro ou administrativo.

**Estado atual relevante:** o backend já exige vínculo clínico para prontuário.
As rotas de valores, materiais e lançamentos operacionais foram alinhadas à
decisão aprovada e validadas por testes; o financeiro administrativo permanece
restrito ao administrador.

### Administrador

**Escopo aprovado:** financeiro, usuários, permissões, relatórios,
configurações gerais e privilégio administrativo sobre os módulos existentes.

**Regra atual:** somente `is_superuser` é administrador global de negócio.
`is_staff` isoladamente não concede acesso clínico ou financeiro na aplicação.

### Auxiliar

O perfil `AUXILIAR` existe no código e precisa de dentista vinculado. Ele é
negado para prontuário, financeiro e alteração de status de agenda. Pela matriz
aprovada em 11/09/2026, recebe somente leitura da agenda relacionada ao seu
trabalho e de identificação/dados cadastrais básicos de pacientes vinculados.
Não cadastra nem edita pacientes, não marca, remarca ou cancela consultas e não
recebe qualquer acesso clínico além do que venha a ser explicitamente aprovado.
Esses limites de leitura e negação foram aplicados e validados por testes em
11/09/2026.

### Matriz final aprovada de agenda, pacientes e financeiro

Nesta matriz, **P** significa permitido, **L** somente leitura, **V** permitido
somente quando houver consulta/paciente vinculado e **N** negado. Administrador
é exclusivamente o usuário `is_superuser`.

| Ação | Secretária | Dentista | Administrador | Auxiliar |
|---|---|---|---|---|
| Ver agenda | P | V | P | L — relacionada ao trabalho |
| Criar, remarcar ou cancelar consulta | P | V — própria agenda | P | N |
| Alterar status, confirmação ou chegada | P | V — própria agenda | P | N |
| Buscar/listar pacientes e ver cadastro | P | V | P | L — dados básicos vinculados |
| Cadastrar/editar dados cadastrais | P | V | P | N |
| Ver, criar ou assinar prontuário/documento clínico | N | V | P | N |
| Visualizar valores e materiais da consulta | N | V | P | N |
| Registrar lançamento operacional | N | V | P | N |
| Financeiro administrativo, contas a receber/pagar, recebimentos gerais, caixa, fechamento, conciliação, inadimplência e relatórios financeiros | N | N | P | N |

A1–A8 continuam prevalecendo sobre esta matriz: em especial, clínica e IA/Voz
exigem vínculo legítimo, consentimento de IA quando aplicável, auditoria e
integridade de assinatura/evolução.

As rotas existentes de agenda, pacientes, consulta e operação financeira foram
alinhadas a esta matriz e validadas em 11/09/2026. Não houve criação de módulo
financeiro, dashboard ou navegação nesta validação.

## Segurança implementada

### A1–A8

- **A1 — Voz/autorização:** transcrição e evolução por voz exigem usuário
  clínico autorizado e, para dentista, vínculo com a consulta.
- **A2 — Consentimento de IA:** transcrição exige `ConsentimentoIA` com
  finalidade `transcricao_voz`, concedido, datado e não revogado.
- **A3 — IDOR de assinatura:** imagem de assinatura exige acesso clínico ao
  paciente; assinatura técnica sem paciente exige administrador.
- **A4 — Prontuário:** secretária e auxiliar são negados; dentista só acessa
  paciente/consulta vinculados; administrador mantém acesso global.
- **A5 — Produção/HTTPS:** settings condicionais de produção para proxy Render,
  cookies seguros, redirect HTTPS, HSTS, hosts/origens CSRF e `DEBUG` seguro.
- **A6 — `registro_id`:** evolução por voz exige registro pendente, da mesma
  transcrição, paciente, consulta e usuário autorizado.
- **A7 — Dependências/deploy:** dependências diretas fixadas, Docker com Python
  por digest e ffmpeg fixado; `.dockerignore` exclui segredos e dados locais.
- **A8 — Integridade da evolução por voz:** reutiliza a evolução clínica e a
  assinatura oficial; exige texto, procedimento, nome profissional, CRO,
  assinatura e vínculo de auditoria.

### Decisões posteriores à auditoria

- Qualquer mudança de status de consulta exige administrador, dentista ou
  secretária e gera `AuditoriaConsulta`.
- Upload de áudio de voz tem tipo permitido, limite de bytes, interrupção no
  upload antes do armazenamento temporário, nome temporário aleatório, limite
  de duração via `ffprobe` e timeout de ffmpeg.
- Detalhes internos de falhas de transcrição não são devolvidos ao navegador.
- `testar_whisper.py` é utilitário manual: só executa quando chamado
  diretamente, sem interferir na descoberta de testes Django.
- O aviso SQLite `models.W047` para a unicidade de preço particular é conhecido:
  SQLite não cria essa restrição; PostgreSQL a suporta. Não ocultar o aviso sem
  decisão explícita.

### Melhorias de segurança ainda pendentes (não bloqueiam o desenvolvimento local)

- A ficha da consulta ainda insere JSON em JavaScript com `|safe`; substituir
  por serialização segura antes de ampliar a entrada de catálogo/importações.
- Não há limitação de tentativas de login nem política explícita de rate limit
  para autenticação e links públicos.
- Integridade e imutabilidade foram implementadas no item 9 (14/09/2026),
  descrito abaixo; exportação permanece fora do escopo desta etapa.
- Ainda não há política de logs estruturados, monitoramento ou retenção de logs
  de produção para eventos de segurança e falhas operacionais.

## Interface planejada

**Aprovação registrada em 11/09/2026:** o usuário aprovou formalmente os
dashboards, menus laterais por perfil e o Design System desta seção. Esta
aprovação não inicia automaticamente a implementação da interface; a matriz
final de permissões foi concluída e a próxima etapa depende de autorização
explícita do usuário.

**Navegação comum concluída em 11/09/2026:** o layout autenticado agora tem
menu lateral responsivo e cabeçalho comum. Secretária recebe Agenda e Pacientes;
Dentista recebe Minha agenda, Pacientes e Materiais utilizados; Administrador
recebe Operação, Financeiro atual e Administração; Auxiliar recebe
somente leitura de Agenda e Pacientes. Itens sem rota existente ou sem
autorização aprovada permanecem ocultos. Não foram criados dashboards ou
novos módulos nesta etapa.

**Dashboard da Secretária — concluído em 11/09/2026:** o dashboard inicial da
Secretária entrega a agenda diária e atalhos autorizados de Agenda e Pacientes.
O fluxo administrativo inclui confirmação (`confirmada`) e chegada do paciente
(`presente`), com filtro por situação na agenda e auditoria de cada mudança.
Não exibe dados financeiros, clínicos ou administrativos. Secretária não pode
marcar uma consulta como realizada; somente Dentista vinculado ou Administrador
podem concluir `presente` para `realizada`. A suíte completa com 70 testes foi
aprovada. Remarcação continua em etapa própria e não foi implementada.

**Ficha da consulta por contexto — concluída em 11/09/2026:** a ficha única
foi reorganizada visualmente em Atendimento, Prontuário e documentos, Operação
da própria consulta ou Financeiro da consulta e Auditoria. Os blocos são
renderizados apenas quando o perfil já possui autorização: Secretária vê
somente Atendimento; Dentista vinculado vê clínica e operação própria;
Administrador vê os contextos administrativos autorizados. Não foram criadas
rotas, regras de negócio ou permissões novas; a suíte completa com 71 testes
foi aprovada.

**Dashboard clínico do Dentista — concluído em 11/09/2026:** o início do
Dentista mostra somente a agenda vinculada do dia, atendimentos com presença
registrada, anamneses em `aguardando_dentista` e autorizações de custo em
rascunho vinculadas às próprias consultas, com atalhos para as rotas clínicas
já existentes. O modelo de evolução não possui vínculo direto com consulta;
por isso, não foi criado nem inferido indicador de “evolução pendente”. O
dashboard não mostra financeiro administrativo, nem dados de outros
dentistas. Não houve migration ou mudança de regra de negócio; a suíte
completa com 72 testes foi aprovada.

**Administração própria e dashboard administrativo — concluídos em
11/09/2026:** o Administrador (`is_superuser`) recebe visão agregada de
consultas em andamento, dentistas, salas e perfis configurados, além de um
portal para usuários/grupos/perfis, profissionais/salas/disponibilidade,
auditorias de agenda e IA/voz e demais configurações técnicas já existentes.
O portal não duplica CRUD nem altera permissões do Django Admin e é negado a
Secretária, Dentista, Auxiliar e `is_staff` sem superusuário. Foram preservados
os atalhos administrativos existentes para Tabela e Repasse Uniodonto. Não
houve migration ou mudança de regra de negócio; a suíte completa com 73 testes
foi aprovada.

### Princípios

- Menu lateral fixo/recolhível por perfil e cabeçalho simples.
- Dashboard com no máximo quatro cards e uma lista prioritária de trabalho.
- Detalhes ficam nos módulos; não concentrar clínica e financeiro na mesma
  tela.
- Dados clínicos e financeiros só aparecem quando necessários ao perfil.

### Design System aprovado para implementação após a aprovação da estrutura

A interface deve ter aparência clínica contemporânea: limpa, sóbria,
profissional e consistente entre Agenda, Pacientes, Prontuário, Financeiro,
Documentos, Assinaturas, IA/Voz, Locação e demais módulos. Não criar telas com
aparência de sistema legado, excesso de informações ou padrões visuais
concorrentes.

- **Tipografia:** usar uma única família sans-serif de alta legibilidade (a
  proposta é Inter ou Source Sans 3), com títulos em peso semibold, texto
  corrente entre 14 e 16 px e altura de linha confortável. Hierarquia de título,
  subtítulo, rótulo, dado e texto de ajuda deve ser consistente.
- **Paleta:** azul-petróleo como cor institucional, azul-claro clínico para
  contexto/seleção, fundo neutro muito claro, superfícies brancas e texto em
  grafite. Verde significa sucesso, âmbar alerta/pendência, vermelho erro ou
  ação destrutiva e azul informação. Os valores exatos devem ser centralizados
  em tokens CSS; a proposta inicial é `#0F5C66`, `#E8F4F5`, `#F7F9FA`,
  `#FFFFFF`, `#1F2933`, `#16803C`, `#B45309`, `#B42318` e `#2563EB`.
- **Ícones:** usar uma única biblioteca de ícones lineares modernos (proposta:
  Lucide) e o mesmo significado em todos os módulos. Ícone não substitui rótulo
  quando o contexto não for inequívoco.
- **Espaçamento e alinhamento:** aplicar grade de 8 px, alinhamentos em coluna
  e espaçamento uniforme entre seções, campos, ações e cards. Evitar blocos
  comprimidos; conteúdo deve ter largura de leitura adequada.
- **Menu lateral:** branco, com ícone e rótulo, grupos de navegação claros,
  estado ativo em azul-claro e indicador azul-petróleo. Em desktop permanece
  fixo; em tablet pode recolher; em celular abre como painel deslizante. Itens
  sem permissão ou ainda não implementados permanecem ocultos, não apenas
  desabilitados.
- **Cabeçalho:** título, contexto/breadcrumb quando necessário e uma única ação
  principal visível. Ações de conta e saída ficam consistentes e separadas do
  conteúdo de trabalho.
- **Cards:** superfície branca, borda sutil, raio de 12 px, sombra discreta,
  dado principal destacado e contexto curto. Dashboards usam no máximo quatro
  indicadores antes da lista prioritária.
- **Botões:** primário em azul-petróleo, secundário branco contornado e ação
  destrutiva em vermelho. Ações irreversíveis ou sensíveis exigem confirmação
  explícita; não usar vermelho para ação comum.
- **Tabelas:** cabeçalho claro, linhas confortáveis, filtros e busca no topo,
  etiquetas de estado e ações secundárias em menu contextual. Em telas menores,
  oferecer visualização resumida sem esconder informação necessária.
- **Formulários:** rótulo sempre visível, ajuda e validação ao lado ou abaixo do
  campo, seções curtas e ordenadas, campos obrigatórios identificados por texto
  e não apenas por cor. Evitar formulários extensos em modal.
- **Modais e alertas:** modal apenas para confirmação ou fluxo breve; alertas
  usam ícone, título, explicação objetiva e ação quando aplicável. Sucesso,
  alerta, erro, pendência e informação precisam de texto e ícone, além da cor.
- **Responsividade:** em desktop usar grade e navegação persistente; em tablet,
  colunas e menu recolhível; em celular, uma coluna, alvos de toque confortáveis
  e navegação em painel. Não sacrificar autorização, contexto ou ação crítica
  em telas menores.
- **Acessibilidade:** contraste suficiente, foco de teclado visível, ordem de
  tabulação coerente, rótulos associados aos campos, mensagens de erro
  compreensíveis e alvos de interação acessíveis. Estado visual nunca pode
  depender exclusivamente de cor.

### Secretária

Menu: **Início**, **Agenda** (hoje, calendário, nova consulta,
remarcar/cancelar), **Pacientes** (buscar, novo, cadastro/contato) e
**Atendimento** (confirmações, chegadas, pendências).

Dashboard: consultas do dia, pendências de confirmação, chegadas e atalhos para
nova consulta/busca. Nunca mostrar financeiro ou prontuário clínico.

### Dentista

Menu: **Início clínico**, **Minha agenda**, **Pacientes**, **Prontuário**
(anamnese, evolução, planos), **Documentos** (autorizações, assinaturas,
prescrições quando existirem), **Imagens e exames** quando existirem e
**Materiais utilizados**.

Dashboard: agenda própria, pendências de anamnese/documentos/evolução e atalhos
clínicos. Nunca mostrar financeiro administrativo.

### Administrador

Menu: **Início administrativo**, **Financeiro**, **Administração** (usuários,
perfis/permissões, profissionais/salas, configurações, auditoria) e
**Relatórios**.

Dashboard: totais agregados, pendências de recebimento/pagamento/conciliação e
caixa; nunca texto clínico, assinaturas ou exames no resumo.

### Tela prioritária de redesign

A **ficha da consulta** é a primeira tela a redesenhar: hoje mistura status de
agenda, clínica, documentos, materiais, lançamentos e auditoria. O destino é
separá-la em contextos de **Atendimento**, **Prontuário/documentos** e
**Financeiro**, exibidos somente ao perfil autorizado.

## Financeiro administrativo planejado

O financeiro atual não cobre estes fluxos integralmente. O módulo planejado do
administrador será organizado assim:

- **Visão geral:** totais agregados e pendências.
- **Contas a receber:** títulos, vencimentos, parcelas, saldo, descontos,
  baixa parcial, estornos e recibos.
- **Recebimentos de pacientes:** valor, data/hora, operador, forma de
  pagamento, comprovante e vínculo com consulta/título.
- **Inadimplência:** títulos vencidos, faixas de atraso e histórico de cobrança.
- **Contas a pagar:** fornecedor, categoria, competência, vencimento,
  recorrência, aprovação, baixa e comprovante.
- **Despesas:** evolução do cadastro atual para despesa efetivamente paga e
  classificada.
- **Caixa:** abertura, entradas, saídas, saldo esperado, saldo contado,
  diferença e fechamento.
- **Conciliação:** banco/Pix, cartões, convênios e repasses.
- **Cadastros financeiros:** formas de pagamento, convênios, tabelas e taxas.
- **Relatórios financeiros:** fluxo de caixa, recebimentos por forma, contas
  vencidas, despesas por categoria, fechamento, repasses e resultado por
  período.

O que existe hoje não deve ser tratado como equivalente: `Consulta.pago` não é
recebimento auditável; despesa por competência não é conta a pagar; dívidas
entre dentistas não são inadimplência de paciente; e repasse Uniodonto não é
conciliação bancária geral.

### Contas a receber e recebimentos implementados

O módulo administrativo de contas a receber foi implementado de forma aditiva:
`ContaReceber`, `ParcelaContaReceber`, `RecebimentoPaciente` e
`AuditoriaFinanceira`. O administrador cria títulos por paciente (com consulta
opcional do mesmo paciente), informa uma ou mais parcelas e registra baixas
parciais ou totais com desconto. Os valores usam `Decimal`; o saldo é calculado
pelos eventos e não é sobrescrito. Estorno cria obrigatoriamente um evento
compensatório vinculado ao recebimento original, sem apagar o evento anterior.

As operações são transacionais, bloqueiam a parcela ao conferir saldo e
registram usuário, data/hora, dados da operação e recibo único. As telas, o
recibo e as rotas são exclusivos do administrador autorizado. Nenhum desses
fluxos altera, converte ou reinterpreta `Consulta.pago` ou
`Consulta.forma_pagamento`, nem se mistura a Uniodonto, locação, despesas,
dívidas ou acertos entre dentistas.

Recibo é disponibilizado por rota autorizada e auditável. Upload de comprovante
continua deliberadamente fora do escopo: só poderá existir após política
aprovada de armazenamento persistente, autorização, tipos, limites e retenção.

### Inadimplência implementada

A visão administrativa de inadimplência deriva parcelas de contas a receber
vencidas que ainda possuam saldo positivo, considerando recebimentos,
descontos e estornos. Exibe paciente, título, parcela, vencimento, dias de
atraso, saldo e filtros por texto e faixa de atraso. O histórico financeiro
já existente em `AuditoriaFinanceira` é exibido por título, sem duplicar
informações em novo modelo.

A rota é exclusiva do administrador autorizado e não apresenta conteúdo
clínico. Não modifica saldo, recebimentos, campos legados, Uniodonto, locação,
despesas, dívidas ou acertos entre dentistas.

### Contas a pagar e fornecedores implementados

O módulo administrativo adiciona `Fornecedor`, `CategoriaContaPagar`,
`ContaPagar`, `BaixaContaPagar` e `AuditoriaContaPagar`. Cada título registra
competência, vencimento, valor decimal, recorrência, situação, responsável e
aprovação. A baixa só é permitida após aprovação, é transacional, usa chave de
operação única para impedir duplicidade e muda a situação para paga apenas
quando o saldo calculado chega a zero.

Recorrência é, por enquanto, apenas informativa: não cria títulos futuros sem
regra de negócio aprovada. As novas tabelas e rotas são exclusivas do
administrador e não alteram, convertem ou integram `Despesa`, `DividaAvulsa`,
rateios ou `PagamentoPar`; essa integração continua em etapa futura. Não há
upload de comprovante até que a política segura seja aprovada.

### Despesas integradas sem alterar rateios

`Despesa` mantém competência e regras de rateio intactas. Para despesas novas,
o vínculo opcional e único com `ContaPagar` exige o mesmo valor e é auditado;
despesas históricas permanecem sem vínculo. A data efetiva é obtida das baixas
da conta vinculada, sem substituir a competência.

### Limite financeiro aprovado para dentista

O dentista tem escopo operacional restrito: pode consultar valores e materiais
e registrar lançamentos operacionais somente em consulta própria e paciente
vinculado. Não tem acesso ao financeiro administrativo nem aos módulos de
contas a receber/pagar, recebimentos gerais, inadimplência, caixa, fechamento,
conciliação ou relatórios financeiros. O administrador mantém acesso completo;
secretária e auxiliar não recebem acesso financeiro.

### Fluxo e fechamento de caixa implementados

O caixa administrativo possui abertura única por data, saldo inicial, saldo
esperado calculado por movimentos e fechamento com saldo contado. Recebimentos
de pacientes, seus estornos e baixas de contas a pagar criam movimentos
automáticos somente quando há caixa aberto na data da operação; cada origem é
vinculada uma única vez ao movimento correspondente. Ajustes e compensações
manuais são permitidos exclusivamente ao administrador, exigem motivo e geram
auditoria.

`CaixaDiario`, `MovimentoCaixa` e `AuditoriaCaixa` foram introduzidos pela
migration aditiva `core.0023_fluxo_caixa`, sem conversão, exclusão ou
reinterpretação de dados financeiros legados. O fechamento exige justificativa
para qualquer diferença e impede novos movimentos ou novo fechamento no caixa
fechado. Correções posteriores devem ser registradas como movimento
compensatório auditável em caixa aberto, nunca por alteração ou exclusão do
fechamento. O módulo, suas rotas e sua navegação permanecem exclusivos do
administrador autorizado; dentista, secretária, auxiliar e `is_staff` sem
superusuário não têm acesso.

### Conciliação implementada sem alterar as origens financeiras

A conciliação administrativa registra origens manuais de extrato e contém a
estrutura de normalização para CSV/OFX, sem integração com APIs bancárias nem
persistência do arquivo bruto. `ImportacaoExtrato` bloqueia o reprocessamento
do mesmo arquivo por hash; `LancamentoExtrato` preserva a referência, data,
descrição, natureza e valor normalizados.

`Conciliacao` e `ItemConciliacao` vinculam, sem modificar, recebimentos de
pacientes, baixas de contas a pagar, movimentos manuais de caixa e repasses
Uniodonto. Vínculos podem ser parciais ou totais, nunca superam o valor da
origem/extrato e sugestões por valor, data e referência exigem confirmação do
administrador. Taxas de cartão/Pix e divergências são `AjusteConciliacao`
separados; não criam despesas nem alteram silenciosamente valores originais.

Correções usam cancelamento lógico dos itens e ajustes, mantendo auditoria de
criação, confirmação, ajuste e cancelamento. A migration aditiva
`core.0024_conciliacao`, complementada por
`core.0025_integridade_conciliacao`, não converte nem altera recebimentos,
contas a pagar, caixa, Uniodonto, locação, despesas, rateios ou acertos. A
segunda migration reforça no banco que cada item possui exatamente uma origem
e que cada auditoria possui exatamente um alvo. Todas as rotas e
telas são exclusivas do administrador autorizado.

### Formas de pagamento configuráveis implementadas

`FormaPagamentoConfiguravel` adiciona as formas iniciais Pix, Dinheiro,
Cartão de Débito, Cartão de Crédito e Transferência, com ativação/inativação,
taxa opcional percentual ou fixa, prazo de recebimento e conta/destino
descritivos. O administrador pode cadastrar novas formas e toda alteração é
registrada em `AuditoriaFormaPagamento`.

A migration aditiva `core.0026_formas_pagamento_configuraveis` não altera nem
converte `Consulta.FormaPagamento`, `Consulta.forma_pagamento` ou registros
financeiros anteriores. Novos recebimentos podem vincular a configuração
ativa em campo adicional; o campo legado é preservado e recebe `outros` quando
o novo código não existir na enum histórica. Forma inativa continua visível no
histórico, mas não pode ser selecionada para um novo recebimento. Taxas são
metadados e não criam automaticamente despesa, baixa, movimento de caixa ou
ajuste de conciliação.

### Relatórios financeiros implementados

A rota administrativa de relatórios consolida exclusivamente dados já
existentes e é somente leitura. A visão principal **Realizado / caixa** usa
`MovimentoCaixa` por data de caixa; a visão **Previsto / competência** usa
vencimentos de parcelas, competências de `ContaPagar` e despesas legadas sem
conta vinculada. Os totais não são misturados nem criam competência onde ela
não existe.

O relatório apresenta recebimentos, estornos e descontos por forma de
pagamento, associando o estorno à forma do recebimento original; taxas e
divergências de conciliação permanecem componentes separados. Despesa ligada a
`ContaPagar` é contabilizada apenas pela conta; a despesa histórica sem vínculo
continua no consolidado em origem própria. Também reúne saldo vencido,
fechamentos de caixa e repasses Uniodonto, sem converter, atualizar ou
reinterpretar `Consulta.pago`, dados legados, locação, dívidas, rateios ou
acertos.

Não há exportação CSV/PDF nesta etapa, nem migration. Acesso permanece
exclusivo a `is_superuser`; Dentista, Secretária, Auxiliar e `is_staff` sem
superusuário são negados. A validação incluiu cinco testes específicos, a
suíte completa com **125 testes aprovados**, `manage.py check`,
`makemigrations --check --dry-run` e `git diff --check`.

## Item 9 — legado, integridade e retificações (14/09/2026)

As decisões aprovadas preservam todos os registros e hashes históricos,
sem conversão automática. `Evolucao` fica somente para leitura clínica
autorizada, identificado como legado na ficha de evolução e protegido no
Django Admin. Novos registros seguem o fluxo `RegistroEvolucaoClinica`.

Originais assinados, assinaturas e itens relacionados são protegidos contra
edição e exclusão nos fluxos da aplicação e no Admin, incluindo operações
usuais de atualização/exclusão do ORM, cascatas e mudanças dos profissionais
dos itens. A anamnese mantém sua conclusão pelo dentista após a assinatura do
paciente, sem alterar o conteúdo já assinado. O código não muda os
serializadores históricos nem regenera hashes.

A leitura clínica verifica hash de conteúdo, hash de imagem, disponibilidade
do arquivo e assinaturas esperadas. Ocorrências são mostradas ao usuário
autorizado; imagens sem integridade confirmada, conclusão complementar e
retificação do original inconsistente são bloqueadas. O conteúdo permanece
consultável, identificado pela ocorrência, sem reparo automático. Rascunhos
continuam editáveis e não são apresentados como documentos íntegros assinados.

`RetificacaoDocumento` registra exatamente um original por chaves estrangeiras
protegidas para evolução oficial, anamnese, plano ou autorização, mais autor,
nome profissional/CRO, data/hora, justificativa e conteúdo. A gravação e a
assinatura profissional ocorrem juntas em transação, usando
`AssinaturaEletronica` e o novo tipo `retificacao`. A retificação é imutável,
tem hash próprio e aparece junto ao original com todas as anotações anteriores.
Não substitui a assinatura/consentimento do paciente, não altera procedimentos
autorizados, valores, lançamentos financeiros nem o original.

A migration `core.0027_retificacao_documento` cria somente a estrutura aditiva
de retificação e acrescenta uma opção ao tipo de assinatura; não executa
migração de dados. Contagens e resumos SHA-256 do conteúdo de nove tabelas
clínicas foram comparados antes/depois, sem alterações. Inventário local:
0 evoluções legadas, 8 evoluções oficiais, 20 assinaturas e 1 anexo preenchido.

`FichaAutorizacaoCusto.arquivo` e seus dados foram preservados. Nenhum novo
upload ou armazenamento foi implementado, nem ampliado o acesso aos arquivos.
A política completa de armazenamento, acesso, auditoria, backup e retenção
permanece para etapa futura. Proteções da aplicação não substituem controle
de acesso direto ao banco/arquivos, mídia persistente e backups de produção.

Validação: 25 testes específicos e suíte completa de 150 testes, com
regressões de assinatura, anamnese, evolução, IA/voz e financeiro. O processo
da suíte usa hasher de senha rápido somente para testes, sem modificar os
settings da aplicação. `manage.py check` mantém apenas `models.W047`,
`makemigrations --check --dry-run` sem mudanças pendentes e `git diff --check`
sem erros. Nenhum git add, commit, push ou deploy autorizado ou executado.

Validação visual manual concluída com sucesso, conforme confirmação do usuário:
o documento clínico original permanece preservado e sua assinatura visível.
A ação “Registrar retificação” cria uma anotação separada e vinculada ao
original, com justificativa, conteúdo complementar, profissional/CRO e
assinatura própria. A informação de integridade pelos hashes registrados
também foi confirmada no navegador. Esta validação complementa os testes
automatizados já registrados para o item 9.

## Item 10 — prescrições (retomada em 15/09/2026)

Recorte de prescrições concluído conforme aprovação; imagens/exames continuam
pendentes. Fluxo com paciente e profissional/CRO, medicamentos múltiplos,
texto livre, rascunho editável e assinatura imutável. Retificações têm autoria,
assinatura e histórico próprios, vinculados ao original preservado. Impressão
e PDF incluem original e retificações, bloqueados quando a integridade falha.

A emissão exige dentista ativo com vínculo clínico e a edição do rascunho
exige o mesmo profissional responsável. A assinatura registra o usuário que
assinou, mesmo se outra conta do mesmo profissional criou o rascunho. O
administrador sem perfil prescritor pode consultar conforme autorização,
mas não emitir nem alterar/excluir a prescrição assinada. Secretária e auxiliar
permanecem sem acesso clínico. Nenhuma nova política financeira foi introduzida.

A execução anterior parou depois da geração da migration `0028_prescricoes`
e do `check`. Na retomada, as integrações estavam preservadas no stash
`fd514c9`, mas ausentes da pasta ativa. Foram recuperadas e combinadas com
CPF opcional e digitalização de fichas posteriores, preservando o stash.
A `0028` já estava aplicada no banco com as migrations posteriores até `0031`.
Não houve recriação de migrations, conversão de dados, commit, push ou deploy.

Foi corrigido o salvamento de rascunho sem assinatura no JavaScript efetivamente
servido, a validação de IDs de medicamentos de outra prescrição, a identificação
do autor na retificação, a validação do PNG e a paginação de texto longo em PDF.
Os serializadores históricos anteriores continuam preservados.

Ver `RELATORIO_ITEM10_PRESCRICOES.md` para os testes finais, arquivos envolvidos,
recuperação e evidências de preservação das 64 tabelas do banco real. Testes
visuais usaram banco e mídia separados, exclusivamente com dados fictícios.
PDF é gerado em memória; não cria novo armazenamento persistente de documentos.
As pendências externas de produção abaixo permanecem bloqueadoras.

## Item 10 — imagens e exames (implementação local em 16/09/2026)

Implementação e testes locais concluídos após aprovação explícita da proposta.
Esta atualização sucede o registro histórico de 15/09 acima: prescrições
continuam concluídas e não foram alteradas; imagens/exames agora têm módulo
próprio, com ativação operacional condicionada às pendências abaixo.

O app `exames` adiciona registros imutáveis de arquivo e eventos de auditoria.
Paciente é obrigatório; consulta é opcional e deve pertencer ao mesmo paciente
e ao escopo do usuário. Dentista ativo vinculado e administrador podem incluir
e consultar. Correção/invalidação exige autor ainda autorizado ou administrador;
secretária, auxiliar e staff isolado são negados em todas as rotas. Correções
criam novo registro e preservam o original; não há exclusão física de originais.

São aceitos JPEG, PNG e PDF, um arquivo por envio, até 20 MiB, 40 megapixels e
100 páginas. Validação estrutural ocorre em processo isolado, com limite de
512 MiB e 15 segundos por padrão. PDFs criptografados, ativos ou com anexos são
recusados. ClamAV é acessado somente por loopback; indisponibilidade/erro gera
quarentena sem download, e detecção bloqueia o arquivo. Não há liberação manual.

Arquivos ficam em diretório privado separado da mídia pública, identificados
por UUID. Downloads exigem autenticação, vínculo, inspeção aprovada e hash/tamanho
íntegros. Auditoria registra inclusão, consultas, download iniciado, bloqueios,
correções e invalidações. Não há envio a IA nem alteração do fluxo de digitalização.

Migration `exames.0001_initial` aplicada localmente, criando somente as novas
tabelas e restrições. Dados anteriores e 1.354 arquivos de mídia foram
preservados. Prescrições, assinaturas, prontuários, digitalizações e financeiro
não foram convertidos nem reescritos. As únicas integrações em código anterior
são registro do app, inclusão de rotas e atalhos nas telas já autorizadas.

Validação: 37 testes específicos, 215 testes na regressão completa, check apenas
com o warning SQLite já conhecido e nenhuma diferença de models/migrations.
Navegador em desktop e tela de 390px, upload real mantido em quarentena,
reinspeção e invalidação conferidos com dados fictícios. Backup/restauração
local testado em cópia separada, com 67 tabelas iguais e três arquivos íntegros.

Retenção inicial: preservar originais e histórico sem expurgo automático.
Temporários de requisição são limpos; há comando para temporários abandonados
acima de 24h e inventário somente leitura de integridade/quarentena/órfãos.

Pendências reais: validar motor antimalware real e atualização de assinaturas;
provisionar armazenamento persistente privado e capacidade adequada; definir
responsáveis e prazos definitivos de retenção/quarentena; validar backup e
restauração no ambiente de produção. Os testes controlados de inspeção não
equivalem a homologar um motor real. Sem inspeção disponível, novos arquivos
ficam bloqueados. Não houve deploy, commit/push nem alteração de ambiente de
produção; não foi iniciada outra etapa.

Ver `RELATORIO_ITEM10_IMAGENS_EXAMES.md` para arquivos, evidências, parâmetros
locais e limites operacionais. A conclusão da implementação do Item 10 não
declara o sistema pronto para uso em produção.

## Infraestrutura atual

- Desenvolvimento/testes em Windows, SQLite, mídia local e `.env` local não
  versionado.
- Dependências diretas atuais: Django, Gunicorn, WhiteNoise, faster-whisper,
  dj-database-url e psycopg.
- Dockerfile e `render.yaml` existem no diretório de trabalho, mas não houve
  deploy nem provisionamento externo nesta etapa.
- A imagem Docker exclui `.env`, chaves/certificados, banco SQLite, mídia,
  ambiente virtual e artefatos locais pelo `.dockerignore`.

## Pendências obrigatórias antes de produção real

Estas pendências são bloqueadoras de produção e não devem ser contornadas em
código:

1. Provisionar PostgreSQL e configurar `DATABASE_URL`.
2. Provisionar armazenamento persistente para `MEDIA_ROOT` e assinaturas,
   configurando `RENDER_DISK_PATH`.
3. Configurar SMTP seguro no ambiente (`SMTP_HOST`, credenciais e remetente).
4. Definir e testar backups/restauração para banco e mídia.
5. Configurar segredos, hosts/domínios e HTTPS no painel do Render.
6. Executar `check --deploy`, migrations e testes no ambiente de produção antes
   do primeiro deploy.

## Ordem oficial das próximas etapas

1. Manter este plano e o checklist atualizados antes de implementação.
2. Obter aprovação explícita do desenho de dashboard/menu por perfil.
3. Definir, sem ambiguidade, a matriz final de autorização de agenda, pacientes,
   clínica e financeiro.
4. Implementar navegação comum e dashboard da secretária, com testes de UI e
   autorização.
5. Redesenhar ficha da consulta em contextos separados e alinhar dashboard do
   dentista.
6. Criar administração própria de usuários/permissões e dashboard do
   administrador.
7. Estruturar contas a receber e recebimentos de pacientes.
8. Estruturar contas a pagar, despesas, caixa, conciliação e relatórios.
9. Definir destino do modelo legado `Evolucao`, política de documentos
   assinados e ciclo de vida do anexo de autorização antes de novos fluxos de
   mídia/documentos.
10. Implementar prescrições e imagens/exames apenas com requisitos, permissões,
    armazenamento e auditoria definidos.
11. Tratar pendências externas de produção e executar validação de deploy.

## Decisões que não podem mudar sem aprovação explícita

- Não reduzir ou contornar A1–A8, a auditoria de voz, consentimento de IA ou
  integridade de assinatura/evolução.
- Não conceder prontuário à secretária ou auxiliar, nem acesso de dentista fora
  de vínculo clínico legítimo.
- Não usar `is_staff` como sinônimo de administrador de negócio.
- Não expor financeiro administrativo ao dentista no desenho futuro aprovado.
- Não colocar segredos no código, Git, imagem Docker ou documentação.
- Não fazer commit, push ou deploy sem solicitação explícita do usuário.
- Não criar/aplicar migration sem alteração real de modelo e validação.
- Não declarar produção pronta sem PostgreSQL, mídia persistente, SMTP e backups.
