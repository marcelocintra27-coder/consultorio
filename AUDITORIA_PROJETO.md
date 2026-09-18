# AUDITORIA DO PROJETO — Sistema de Gestão para Consultório Odontológico

## 1. Finalidade deste documento

Este arquivo é o REGISTRO OFICIAL das auditorias técnicas realizadas no projeto consultorio.

Ele NÃO substitui:
- PLANO_MESTRE.md — define para onde o sistema deve evoluir.
- CHECKLIST_PROJETO.md — controla atividades e pendências.
- .cursorrules — estabelece regras permanentes de trabalho.

Este documento registra O QUE FOI EFETIVAMENTE VERIFICADO no código, Django, banco, migrations, telas, permissões, testes e demais componentes.

Nenhuma funcionalidade deve ser considerada certificada apenas porque aparece no Plano Mestre, Checklist ou documentação.

---

## 2. Regra obrigatória para qualquer IA

Antes de propor ou executar alterações relevantes no projeto, GPT, Claude, Cursor, Codex ou outro agente deve consultar:

1. .cursorrules
2. PLANO_MESTRE.md
3. CHECKLIST_PROJETO.md
4. AUDITORIA_PROJETO.md

A IA deve distinguir claramente:

- planejamento;
- implementação existente;
- implementação ainda não verificada;
- problema comprovado;
- hipótese que ainda precisa de evidência.

É proibido declarar uma etapa como CERTIFICADA sem evidência técnica.

Alteração posterior em código relacionado a uma etapa certificada pode exigir REVALIDAÇÃO dessa certificação.

---

## 3. Estados oficiais da auditoria

### NÃO AUDITADO
Ainda não houve verificação técnica suficiente.

### EM AUDITORIA
Verificação iniciada, mas ainda incompleta.

### PARCIAL
Parte da implementação foi comprovada, mas faltam componentes relevantes.

### CERTIFICADO
A afirmação registrada foi comprovada por evidência técnica.

### PROBLEMA IDENTIFICADO
Foi encontrada evidência concreta de problema, inconsistência ou risco.

### REVALIDAÇÃO NECESSÁRIA
Uma certificação anterior pode ter sido afetada por alteração posterior no sistema.

---

# REGISTRO DAS AUDITORIAS

## A-001 — Integridade Django / System Check

*Estado:* PARCIAL

### Evidência executada

Foi executado:

python manage.py check

O Django concluiu a verificação e apresentou 1 warning:

core.PrecoProcedimento: (models.W047) SQLite does not support UniqueConstraint.nulls_distinct.

### Resultado certificado

O manage.py check não apresentou erro impeditivo na execução observada.

Existe, entretanto, o warning models.W047.

### Pendência

Ainda deve ser analisado qual regra de integridade de PrecoProcedimento depende de nulls_distinct e quais consequências existem no SQLite.

NÃO silenciar o warning apenas para fazê-lo desaparecer antes dessa análise.

---

## A-002 — Sincronização Models / Migrations

*Estado:* CERTIFICADO para a verificação realizada

### Evidência executada

Foi executado:

python manage.py makemigrations --check --dry-run

Resultado observado:

No changes detected

Também foi executado:

python manage.py showmigrations

As migrations exibidas estavam marcadas como aplicadas [X], incluindo migrations observadas dos apps ia_seguranca, locacao e sessions.

### Resultado certificado

Na verificação realizada, o Django não detectou alterações de models exigindo nova migration.

Não foi observada migration pendente no resultado apresentado.

### Limite da certificação

Esta certificação representa o estado do projeto no momento da auditoria.

Alterações posteriores em models ou migrations exigem nova verificação.

---

## A-003 — Modelo Consulta

*Estado:* PARCIAL

### Evidência executada

O próprio Django foi utilizado para inspecionar Consulta._meta.fields.

Foram observados, entre outros, os seguintes campos:

- id — BigAutoField
- paciente — ForeignKey
- data — DateField
- hora_inicio — TimeField
- hora_fim — TimeField
- status — CharField
- pago — BooleanField
- forma_pagamento — CharField
- observacoes — TextField
- dentista — ForeignKey
- eh_legado — BooleanField
- valor_historico — DecimalField
- dentista_complementado_em — DateTimeField
- dentista_complementado_por — ForeignKey
- cadastrado_em — DateTimeField

### Status de Consulta certificados pelo Django

Foi consultado diretamente o campo status.

Resultado observado:

- agendada
- confirmada
- presente — "Paciente chegou"
- realizada
- faltou
- cancelada

Default observado:

agendada

### Resultado certificado

A estrutura acima e os choices acima foram comprovados no model carregado pelo Django durante a auditoria.

### NÃO certificado nesta etapa

Esta auditoria NÃO certifica ainda:

- regras de transição entre status;
- quem pode alterar cada status;
- views;
- forms;
- URLs;
- templates;
- botões disponíveis nas telas;
- comportamento de remarcação;
- permissões de Secretária;
- permissões de Dentista;
- permissões de Administrador;
- logs/auditoria das alterações;
- testes automatizados desse fluxo;
- controles de acesso/LGPD relacionados ao fluxo.

A ausência de remarcada entre os choices NÃO deve ser classificada automaticamente como defeito.

Na A-003, a remarcação ainda precisava ser auditada. A A-005 posteriormente certificou o UPDATE de data/hora na mesma `Consulta` / mesmo `pk`.

---

## A-004 — Fluxo funcional Agenda / Consulta

Registro histórico da revisão inicial. As limitações R-002, R-003 e R-004 abaixo foram posteriormente resolvidas e certificadas na A-005; não representam pendências atuais. As demais limitações do recorte A-004 permanecem com seu alcance original.

*Estado geral:*
- controles de acesso: **CERTIFICADOS**;
- fluxo funcional completo: **PARCIALMENTE CERTIFICADO**.

A auditoria desta etapa foi SOMENTE LEITURA. Nenhuma alteração de código de aplicação foi feita para obter estas evidências.

### Objetivo desta auditoria

Mapear:

AÇÃO → TELA/TEMPLATE → URL → VIEW → PERMISSÃO → ALTERAÇÃO → AUDITORIA → TESTE

Itens examinados: agendamento; confirmação; paciente presente/chegada; realização/conclusão; falta; cancelamento; remarcação; permissões por perfil nos fluxos acima.

### 1. Controles de acesso — CERTIFICADOS

#### Evidências verificadas no código

1. Autenticação global obrigatória configurada por `django.contrib.auth.middleware.LoginRequiredMiddleware` em `consultorio/settings.py` (`MIDDLEWARE`). `LOGIN_URL = 'entrar'`.
2. Visibilidade das consultas controlada no servidor por `consultas_visiveis_para_usuario` (`core/permissoes.py`), usada em `listar_consultas`, no dashboard (`inicio`) e em `listar_materiais_dia`. Administrador vê o queryset completo; Secretária vê a agenda; Dentista e Auxiliar ficam restritos a `dentista_id` do perfil; demais perfis recebem queryset vazio.
3. Acesso pontual à ficha exige `usuario_pode_acessar_consulta` em `ficha_consulta` antes da renderização.
4. Agendamento exige `usuario_pode_agendar_consulta` em `agendar_consulta` (Administrador, Dentista ou Secretária autenticados); Auxiliar não está nessa autorização.
5. Operações financeiras da consulta protegidas no servidor por `@exige_financeiro` e, nas mutações examinadas, `@require_POST`: `marcar_consulta_paga` e `salvar_forma_pagamento`. `exige_financeiro` delega a `usuario_pode_financeiro`, que autoriza somente administrador de negócio (`is_superuser`).
6. Flags de interface (`pode_financeiro`, `pode_visualizar_valores`, `pode_agendar`) são calculadas nas views a partir de `core/permissoes.py` e apenas ocultam ações no template; a autorização efetiva não depende do front-end.
7. Exceções intencionais de `login_not_required` observadas: `sair`, `ficha_anamnese_publica` e `ficha_anamnese_enviada`. Nenhuma dessas rotas é Agenda/Consulta.
8. Não foi identificada, nesta etapa, evidência de acesso anônimo à Agenda/Consulta pelos fluxos examinados (`listar_consultas`, `agendar_consulta`, `ficha_consulta`, `alterar_status_consulta`, `marcar_consulta_paga`).

#### Resultado certificado

Os controles de autenticação, visibilidade e autorização examinados nesta etapa estão certificados com evidência do código.

Esta certificação de acesso **não** equivale, por si só, à certificação do fluxo funcional completo (ver seção 2).

### 2. Fluxo funcional completo — PARCIALMENTE CERTIFICADO

Confirmação, chegada, realização, falta e cancelamento **não** possuem rotas próprias na aplicação: compartilham o mesmo mecanismo de status.

#### Infraestrutura compartilhada de status (evidência)

- **AÇÃO:** alterar `Consulta.status` para um valor permitido.
- **TELA/TEMPLATE:** `core/templates/core/ficha_consulta.html` — seção Atendimento; formulário `POST` somente se `pode_alterar_status`.
- **URL:** `consultas/<int:pk>/status/` — nome `core:alterar_status_consulta` (`core/urls.py`).
- **VIEW:** `alterar_status_consulta` (`core/views.py`), decorada com `@require_POST`; usa `StatusConsultaForm` (`core/forms.py`) com choices filtrados por `status_permitidos`.
- **PERMISSÃO:** `usuario_pode_gerenciar_agenda` + `status_consulta_permitidos` + `usuario_pode_alterar_status_consulta` (`core/permissoes.py`). Secretária, dentista da consulta e administrador gerenciam agenda; auxiliar não. Dentista não opera consulta de outro dentista (`usuario_pode_acessar_consulta`).
- **ALTERAÇÃO:** `form.save()` em `Consulta.status`.
- **AUDITORIA:** `_registrar_auditoria` grava `AuditoriaConsulta` (consulta, usuário, descrição `status alterado para {get_status_display()}`, `cadastrado_em`). Na ficha, a lista de auditorias só é passada ao template se `pode_financeiro` (administrador).
- **TESTE:** varia por ação (registrado em cada fluxo abaixo).

Transições observadas em `status_consulta_permitidos`:

- `agendada` → `confirmada`, `presente`, `cancelada`, `faltou`
- `confirmada` → `agendada`, `presente`, `cancelada`, `faltou`
- `presente` → `cancelada`, `faltou`; `realizada` somente se administrador ou dentista
- `realizada` / `faltou` / `cancelada` → conjunto vazio neste fluxo (não reabre)

#### Limitações identificadas na A-004 — resolvidas posteriormente na A-005

- **Falta:** na A-004 não havia teste HTTP específico identificado; implementado e certificado na A-005 / R-004.
- **Agendamento:** na A-004 não havia auditoria de criação identificada; implementada e certificada no fluxo web na A-005 / R-003.
- **Remarcação:** ausente na revisão A-004; implementada e certificada na A-005 / R-002, na mesma `Consulta` / mesmo `pk`.

#### Resumo dos sete fluxos

| Fluxo | Classificação |
|---|---|
| Agendamento | CERTIFICADO no fluxo web após A-005 / R-003 |
| Confirmação | CERTIFICADO (fluxo de status na aplicação) |
| Paciente presente / chegada | CERTIFICADO (fluxo de status na aplicação) |
| Realização / conclusão | CERTIFICADO (fluxo de status na aplicação) |
| Falta | CERTIFICADO após A-005 / R-004 |
| Cancelamento | CERTIFICADO (fluxo de status na aplicação) |
| Remarcação | IMPLEMENTADA E CERTIFICADA na A-005 / R-002 |

CERTIFICADO nestes itens refere-se ao fluxo da **aplicação web** examinado, não à reabertura de status finais. A proteção seletiva do Django Admin foi certificada separadamente na A-005.

### 2.1 Agendamento — CERTIFICADO no fluxo web após A-005 / R-003

- **AÇÃO:** criar consulta.
- **TELA/TEMPLATE:** `core/templates/core/listar_consultas.html` (botão se `pode_agendar`); `core/templates/core/inicio.html` (atalho “Agendar consulta” no dashboard da secretária); `core/templates/core/form_consulta.html`.
- **URL:** `consultas/agendar/` — nome `core:agendar_consulta`.
- **VIEW:** `agendar_consulta`; formulário `ConsultaForm` (paciente, data, hora_inicio, hora_fim, dentista, observações; **sem** campo `status`).
- **PERMISSÃO:** `usuario_pode_agendar_consulta` — administrador, dentista ou secretária; auxiliar não. Dentista: queryset de `dentista` restrito ao próprio perfil.
- **ALTERAÇÃO:** `consulta.eh_legado = False`; validação compartilhada de conflito; gravação e auditoria na mesma transação; default do model `Consulta.status` = `agendada`; redirect para a agenda na data criada.
- **AUDITORIA (A-005):** `AuditoriaConsulta` via `_registrar_auditoria`, com usuário, timestamp, paciente, dentista, data/horários e origem `agendar_consulta`.
- **TESTE:** `test_dentista_cadastra_paciente_e_agenda_apenas_para_si` (`core/test_permission_matrix.py`) — POST com outro dentista não cria; POST com o próprio cria (302). `test_agendar_exige_dentista` (`core/tests.py`) — secretária POST sem dentista → 200 e não cria. Auxiliar: lista sem “Agendar”; menu sem URL de agendar. Na A-004 não foi identificado POST 403 de auxiliar nem POST bem-sucedido de secretária/administrador; a A-005 acrescentou cobertura de criação pela secretária.

Complemento A-005: criação auditada e rollback em falha da auditoria cobertos em `core/test_agenda_a005.py`. A ausência de rastreabilidade registrada na A-004 foi resolvida no fluxo web.

### 2.2 Confirmação — CERTIFICADO (fluxo de status na aplicação)

- **AÇÃO:** `Consulta.status = confirmada`.
- **TELA/TEMPLATE:** `ficha_consulta.html` (infraestrutura compartilhada).
- **URL:** `consultas/<int:pk>/status/` — `core:alterar_status_consulta`.
- **VIEW:** `alterar_status_consulta`.
- **PERMISSÃO:** origem `agendada` em `status_consulta_permitidos`. Secretária, dentista da consulta, administrador.
- **ALTERAÇÃO:** `Consulta.status` persistido como `confirmada`.
- **AUDITORIA:** `AuditoriaConsulta` via `_registrar_auditoria`.
- **TESTE:** `test_status_da_consulta_exige_perfil_de_agenda_e_conclusao_clinica` (`core/test_security.py`) — secretária `AGENDADA` → `CONFIRMADA` (302), status persistido, auditoria com `descricao__contains='confirmada'`.

Não há módulo separado de confirmação; o fluxo certificado é essa transição de status.

### 2.3 Paciente presente / chegada — CERTIFICADO (fluxo de status na aplicação)

- **AÇÃO:** `Consulta.status = presente` (rótulo do model: “Paciente chegou”).
- **TELA/TEMPLATE:** `ficha_consulta.html` (infraestrutura compartilhada).
- **URL:** `consultas/<int:pk>/status/` — `core:alterar_status_consulta`.
- **VIEW:** `alterar_status_consulta`.
- **PERMISSÃO:** origens `agendada` ou `confirmada` em `status_consulta_permitidos`.
- **ALTERAÇÃO:** `Consulta.status` persistido como `presente`.
- **AUDITORIA:** mesmo `_registrar_auditoria`; não foi identificado `assert` específico do texto “Paciente chegou”.
- **TESTE:** `test_security` — após confirmação, secretária POST `PRESENTE` → 302 e persistência. `test_consulta_e_status_exigem_escopo_de_agenda` (`core/test_permission_matrix.py`) — dentista `AGENDADA` → `PRESENTE` (302). Dashboard do dentista conta `PRESENTE` como em atendimento (`inicio`).

### 2.4 Realização / conclusão — CERTIFICADO (fluxo de status na aplicação)

- **AÇÃO:** `Consulta.status = realizada`.
- **TELA/TEMPLATE:** `ficha_consulta.html` (infraestrutura compartilhada).
- **URL:** `consultas/<int:pk>/status/` — `core:alterar_status_consulta`.
- **VIEW:** `alterar_status_consulta`.
- **PERMISSÃO:** somente a partir de `presente`, e somente administrador ou dentista (`pode_concluir`). Secretária não recebe essa opção em `status_consulta_permitidos`.
- **ALTERAÇÃO:** `Consulta.status` persistido como `realizada`.
- **AUDITORIA:** mesmo `_registrar_auditoria`; sem assert específico de “realizada”.
- **TESTE:** secretária POST `REALIZADA` a partir de `agendada` → 403 e status inalterado (`test_security`); secretária POST `REALIZADA` em consulta da matriz → 403; dentista, após `PRESENTE`, POST `REALIZADA` → 302 (`test_security` e `test_consulta_e_status_exigem_escopo_de_agenda`); auxiliar POST `REALIZADA` → 403.

Não foi coberto por teste HTTP a tentativa de `realizada` a partir de `agendada`/`confirmada` pelo dentista (o código não inclui essas origens).

### 2.5 Falta — CERTIFICADO após A-005 / R-004

- **AÇÃO:** `Consulta.status = faltou`.
- **TELA/TEMPLATE:** `ficha_consulta.html` (infraestrutura compartilhada); o valor entra nas choices do form quando a origem permite.
- **URL:** `consultas/<int:pk>/status/` — `core:alterar_status_consulta`.
- **VIEW:** `alterar_status_consulta`.
- **PERMISSÃO:** `status_consulta_permitidos` permite `faltou` a partir de `agendada`, `confirmada` e `presente`.
- **ALTERAÇÃO:** gravação de `Consulta.status` com `update_fields=['status']`, em transação com a auditoria.
- **AUDITORIA:** mesmo `_registrar_auditoria`.
- **TESTE (A-005):** `test_faltou_http_respeita_matriz` em `core/test_agenda_a005.py`: POST para `faltou`, 403 para auxiliar/dentista alheio; 302 para secretária/dentista responsável/admin, com persistência e auditoria do usuário.

A lacuna de teste HTTP registrada na A-004 foi resolvida na A-005 / R-004.

### 2.6 Cancelamento — CERTIFICADO (fluxo de status na aplicação)

- **AÇÃO:** `Consulta.status = cancelada` (não há exclusão da consulta neste fluxo).
- **TELA/TEMPLATE:** `ficha_consulta.html` (infraestrutura compartilhada).
- **URL:** `consultas/<int:pk>/status/` — `core:alterar_status_consulta`.
- **VIEW:** `alterar_status_consulta`.
- **PERMISSÃO:** origens `agendada`, `confirmada` e `presente`. Não a partir de `realizada` neste fluxo.
- **ALTERAÇÃO:** `Consulta.status` persistido como `cancelada`.
- **AUDITORIA:** mesmo `_registrar_auditoria`; sem assert específico de “cancelada”.
- **TESTE:** `test_consulta_e_status_exigem_escopo_de_agenda` — dentista cancela consulta de outro dentista → 403; auxiliar cancela consulta vinculada → 403; secretária cancela → 302.

Este fluxo **não** é o cancelamento lógico de conciliação (`cancelar_conciliacao`).

### 2.7 Remarcação — IMPLEMENTADA E CERTIFICADA na A-005 / R-002

- **AÇÃO:** UPDATE controlado de data/hora na mesma `Consulta` / mesmo `pk`, preservando paciente, dentista e relacionamentos.
- **TELA/TEMPLATE:** botão autorizado na ficha; `RemarcacaoConsultaForm` próprio, renderizado em `core/form_consulta.html`, com data, horários e motivo opcional.
- **URL/VIEW:** `consultas/<pk>/remarcar/`, `core:remarcar_consulta`, view `remarcar_consulta`.
- **PERMISSÃO:** `usuario_pode_gerenciar_agenda` no servidor: secretária, administrador de negócio (`is_superuser`) e dentista responsável; auxiliar e dentista alheio recebem 403.
- **ALTERAÇÃO:** somente `agendada` e `confirmada`; após remarcação, status `agendada`. Presente, realizada, faltou e cancelada bloqueadas. Sem nova Consulta nem model de vínculo original↔nova.
- **AUDITORIA:** `AuditoriaConsulta` na mesma transação, com usuário, timestamp, intervalos anteriores/novos, status e motivo opcional (até 100 caracteres). POST sem mudança efetiva não grava auditoria nem desfaz confirmação.
- **TESTE:** `core/test_agenda_a005.py`, incluindo HTTP, preservação de vínculos, permissões, conflito e rollback.

Proteção seletiva do `ConsultaAdmin` certificada na A-005: criação desabilitada; `data`, `hora_inicio`, `hora_fim`, `status` e `dentista` somente leitura; demais campos administrativos preservados. A ausência de choice `remarcada` não é defeito: a arquitetura usa a mesma Consulta.

### 3. Fora do recorte certificado de A-004

Ainda não certificados por esta etapa:

- LGPD além da visibilidade/autorização já examinada;
- Django Admin: proteção seletiva posteriormente certificada na A-005, sem certificação geral dos demais campos administrativos;
- conflito por dentista: posteriormente certificado na A-005; `Disponibilidade` e conflito de sala permanecem fora do escopo;
- reabertura de status finais;
- GET em `/status/` (405 esperado por `@require_POST`, sem teste explícito identificado);
- formulário de status inválido: redirect sem mensagem ao usuário.

A A-004 não alterou código; os complementos posteriores certificados na A-005 estão indicados acima.

### 4. Bloqueadores identificados na A-004 — resolvidos na A-005

Os itens abaixo eram bloqueadores para uso em produção na A-004. Foram implementados e certificados no escopo aprovado da A-005; isso não certifica infraestrutura nem declara produção pronta.

A A-004 não significava “pronto para produção”; seu registro documental não autorizou correções de código. O tratamento posterior foi a A-005, cujo encerramento não autoriza integração ou deploy.

#### 4.1 Remarcação — IMPLEMENTADA E CERTIFICADA na A-005

*Risco:* R-002  
*Prioridade original:* ALTA — bloqueador resolvido na A-005.

R-002 resolvida: mesma `Consulta` / mesmo `pk`, UPDATE controlado, vínculos preservados e auditoria antes/depois. A prioridade ALTA registra a classificação original do bloqueador.

#### 4.2 Auditoria de criação — IMPLEMENTADA E CERTIFICADA no fluxo web

*Risco:* R-003  
*Prioridade:* ALTA — risco de compliance em dados de saúde.

R-003 implementada e certificada no fluxo web `agendar_consulta`, com usuário, timestamp e dados do agendamento em `AuditoriaConsulta`, na mesma transação.

#### 4.3 Teste HTTP de “faltou” — IMPLEMENTADO E CERTIFICADO

*Risco:* R-004  
*Prioridade:* MÉDIA.

R-004 implementada e certificada: teste HTTP de `faltou` com permissões, persistência e auditoria.

Tratamento concluído: auditoria **A-005**, certificada no escopo aprovado.

---

## A-005 — Remarcação, Auditoria de Criação e Cobertura de Testes

*Estado:* IMPLEMENTADA E CERTIFICADA no escopo aprovado — encerramento documental em 18/09/2026.

*Origem:* bloqueadores identificados na A-004 (R-002, R-003, R-004).

*Certificação:* revisão independente do Claude por leitura e testes HTTP; certificação do GPT coordenador comunicada pelo usuário. Este encerramento altera somente documentação, sem nova execução de testes.

### Escopo implementado e certificado

1. **R-002 — Remarcação:** arquitetura (a), mesma `Consulta` / mesmo `pk`, UPDATE controlado de data/horários, sem nova Consulta nem model de vínculo. Paciente, dentista e relacionamentos preservados. Somente `agendada` e `confirmada` podem ser remarcadas; confirmada volta a agendada. Presente, realizada, faltou e cancelada bloqueadas. Secretária, administrador e dentista responsável autorizados no servidor; auxiliar e dentista alheio bloqueados.
2. **Auditoria da remarcação:** `AuditoriaConsulta` existente, com usuário, timestamp, intervalos anteriores/novos, mudança de status e motivo opcional (até 100 caracteres, sem truncamento). Gravação e auditoria atômicas; falha da auditoria reverte a gravação. Sem alteração efetiva, não há auditoria nem perda de confirmação.
3. **R-003 — Criação:** implementada e certificada no fluxo web `agendar_consulta`; `AuditoriaConsulta` registra usuário, timestamp, paciente, dentista, data/horários e origem, na mesma transação. Sem atribuição artificial de autoria a dados históricos.
4. **R-004 — Falta:** `test_faltou_http_respeita_matriz` certifica POST autorizado para `faltou`, nega auxiliar/dentista alheio e verifica persistência e auditoria.
5. **Conflito compartilhado:** `validar_horario_consulta`, em `core/agenda.py`, usada na criação e remarcação. Mesmo dentista/data; `novo_inicio < existente_fim` e `novo_fim > existente_inicio`; consecutivos permitidos; cancelada não ocupa horário; própria Consulta excluída; `hora_fim > hora_inicio`. Legados sem dentista preservados, sem filtro de conflito por profissional inexistente.
6. **Django Admin — bloqueio seletivo aprovado:** criação de Consulta desabilitada; data, hora_inicio, hora_fim, status e dentista protegidos; demais campos administrativos preservados. Proteção coberta por testes HTTP.

A exibição da trilha `AuditoriaConsulta` na ficha permanece condicionada a `pode_financeiro` (administrador); a certificação do registro não implica acesso da secretária/dentista à lista.

### Evidências de validação já executadas

- `manage.py test core.test_agenda_a005 --noinput`: 18 testes aprovados; também aprovados na revisão independente.
- Execução conjunta anterior: `manage.py test core.test_agenda_a005 core.tests core.test_permission_matrix core.test_security --noinput`: 78 aprovados (16 A-005 então existentes + 62 de regressão).
- `manage.py check`: sem erros, mantendo somente o warning conhecido `models.W047` do SQLite, não silenciado.
- `manage.py makemigrations --check --dry-run`: `No changes detected`.
- Nenhuma migration criada ou necessária; nenhum model novo de histórico.

Limite técnico registrado na implementação: SQLite não fornece bloqueio de linha por `select_for_update`; concorrência real não foi validada pela suíte. A certificação acima não amplia essa garantia.

### Fora do escopo certificado

- Conflito de sala e fluxo de `Disponibilidade`.
- Notificações e-mail/WhatsApp e gancho de notificação: não implementados na A-005.
- Alterações em financeiro, prontuário, evolução e Locação de Consultórios.
- Infraestrutura, integração e deploy; a certificação não declara produção pronta.

### Histórico de decisão — OPÇÃO 1 (17/09/2026)

Usuário + GPT aprovaram priorizar remarcação antes das pendências externas; a OPÇÃO 2 foi rejeitada. Naquela reconciliação apenas documental, o checklist não foi alterado e não houve autorização de implementação. A decisão arquitetural e a autorização vieram posteriormente: mesma Consulta / mesmo pk e reutilização de `AuditoriaConsulta`, conforme escopo certificado acima. Prioridades originais: R-002 ALTA/bloqueador, R-003 ALTA e R-004 MÉDIA. Os três itens estão agora resolvidos no escopo da A-005.

---

# REGISTRO DE RISCOS

## R-001 — SQLite / UniqueConstraint.nulls_distinct

*Origem:* A-001  
*Estado:* ABERTO

O Django mantém o warning `models.W047`: SQLite não suporta `UniqueConstraint.nulls_distinct`; a constraint correspondente não é criada. Não silenciar o warning. Permanece necessária a análise da regra de negócio e de suas consequências antes de qualquer correção.

---

## R-002 — Remarcação

*Origem:* A-004  
*Estado:* RESOLVIDO — IMPLEMENTADA E CERTIFICADA na A-005
*Prioridade original:* ALTA — bloqueador de produção

Arquitetura adotada: mesma `Consulta` / mesmo `pk`, UPDATE controlado de data/hora, vínculos preservados, auditoria antes/depois e motivo opcional. Confirmada volta a agendada; status incompatíveis e perfis não autorizados bloqueados no servidor. Não há nova Consulta nem necessidade de choice `remarcada`.

---

## R-003 — Auditoria da criação de agendamento

*Origem:* A-004  
*Estado:* RESOLVIDO NO FLUXO WEB — IMPLEMENTADA E CERTIFICADA na A-005
*Prioridade original:* ALTA — rastreabilidade / dados de saúde

`agendar_consulta` registra `AuditoriaConsulta` atomicamente com a criação: usuário, timestamp, paciente, dentista, data/horários e origem. Inclusão de Consulta pelo Django Admin desabilitada. Sem preenchimento artificial de histórico antigo.

---

## R-004 — Teste HTTP de “faltou”

*Origem:* A-004  
*Estado:* RESOLVIDO — IMPLEMENTADO E CERTIFICADO na A-005
*Prioridade original:* MÉDIA

`test_faltou_http_respeita_matriz`, em `core/test_agenda_a005.py`, verifica POST permitido para secretária, dentista responsável e administrador, 403 para auxiliar/dentista alheio, persistência de `faltou` e auditoria com o usuário.

---

# REGRA DE CONTINUIDADE

Ao encerrar cada auditoria:

1. atualizar este documento;
2. registrar evidências;
3. registrar o estado;
4. registrar pendências;
5. registrar riscos encontrados;
6. indicar exatamente a próxima auditoria;
7. não apagar histórico de auditorias anteriores.

Ao iniciar uma nova sessão, a IA deve usar este documento para descobrir o último ponto certificado e continuar dali.

---

## Próxima etapa oficial

A-005 encerrada documentalmente no escopo implementado e certificado. R-002, R-003 (fluxo web) e R-004 resolvidos; R-001 / W047 permanece aberto.

Devolver este encerramento ao GPT coordenador e aguardar definição explícita da próxima ação. Nenhuma nova auditoria numerada, implementação, branch, migration, commit, push, merge ou deploy está autorizada por este registro. As pendências externas do plano mestre permanecem; não há declaração de produção pronta.
