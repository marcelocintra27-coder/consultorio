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

A remarcação pode estar implementada por alteração de data/hora e ainda precisa ser auditada.

---

## A-004 — Fluxo funcional Agenda / Consulta

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

#### Limitações mantidas (não corrigidas nesta etapa)

- **Falta** existe no código, porém sem teste HTTP específico identificado.
- **Agendamento** existe e está parcialmente testado, porém sem auditoria/rastreabilidade de criação identificada.
- **Remarcação** não foi encontrada implementada na aplicação.

#### Resumo dos sete fluxos

| Fluxo | Classificação |
|---|---|
| Agendamento | PARCIALMENTE CERTIFICADO |
| Confirmação | CERTIFICADO (fluxo de status na aplicação) |
| Paciente presente / chegada | CERTIFICADO (fluxo de status na aplicação) |
| Realização / conclusão | CERTIFICADO (fluxo de status na aplicação) |
| Falta | PARCIALMENTE CERTIFICADO |
| Cancelamento | CERTIFICADO (fluxo de status na aplicação) |
| Remarcação | NÃO CERTIFICADO (fluxo próprio inexistente na aplicação) |

CERTIFICADO nestes itens refere-se ao fluxo da **aplicação web** examinado, não ao Django Admin nem à reabertura de status finais.

### 2.1 Agendamento — PARCIALMENTE CERTIFICADO

- **AÇÃO:** criar consulta.
- **TELA/TEMPLATE:** `core/templates/core/listar_consultas.html` (botão se `pode_agendar`); `core/templates/core/inicio.html` (atalho “Agendar consulta” no dashboard da secretária); `core/templates/core/form_consulta.html`.
- **URL:** `consultas/agendar/` — nome `core:agendar_consulta`.
- **VIEW:** `agendar_consulta`; formulário `ConsultaForm` (paciente, data, hora_inicio, hora_fim, dentista, observações; **sem** campo `status`).
- **PERMISSÃO:** `usuario_pode_agendar_consulta` — administrador, dentista ou secretária; auxiliar não. Dentista: queryset de `dentista` restrito ao próprio perfil.
- **ALTERAÇÃO:** `consulta.eh_legado = False`; `form.save()`; default do model `Consulta.status` = `agendada`; redirect para a agenda na data criada.
- **AUDITORIA:** não chama `_registrar_auditoria`. Não foi identificada `AuditoriaConsulta` na criação. Há apenas `cadastrado_em` no model.
- **TESTE:** `test_dentista_cadastra_paciente_e_agenda_apenas_para_si` (`core/test_permission_matrix.py`) — POST com outro dentista não cria; POST com o próprio cria (302). `test_agendar_exige_dentista` (`core/tests.py`) — secretária POST sem dentista → 200 e não cria. Auxiliar: lista sem “Agendar”; menu sem URL de agendar. Não foi identificado POST 403 de auxiliar nem POST bem-sucedido de secretária/administrador.

Limitação mantida: agendamento existe e está parcialmente testado, porém sem auditoria/rastreabilidade de criação identificada.

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

### 2.5 Falta — PARCIALMENTE CERTIFICADO

- **AÇÃO:** `Consulta.status = faltou`.
- **TELA/TEMPLATE:** `ficha_consulta.html` (infraestrutura compartilhada); o valor entra nas choices do form quando a origem permite.
- **URL:** `consultas/<int:pk>/status/` — `core:alterar_status_consulta`.
- **VIEW:** `alterar_status_consulta`.
- **PERMISSÃO:** `status_consulta_permitidos` permite `faltou` a partir de `agendada`, `confirmada` e `presente`.
- **ALTERAÇÃO:** `form.save()` em `Consulta.status` (mesmo caminho das demais transições).
- **AUDITORIA:** mesmo `_registrar_auditoria`.
- **TESTE:** não foi identificado `client.post(..., {'status': Consulta.Status.FALTOU})` nos testes rastreados. O choice existe em `Consulta.Status.FALTOU` (`core/models.py`) e na migration `core.0020_alter_consulta_status`.

Limitação mantida: falta existe no código, porém sem teste HTTP específico identificado.

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

### 2.7 Remarcação — NÃO CERTIFICADO

- **AÇÃO:** reagendar consulta (alterar data/hora em fluxo próprio da aplicação) — **não encontrada**.
- **TELA/TEMPLATE:** não há template de remarcar; a ficha exibe data/horário em resumo (`<dl>`), sem formulário de reagendamento.
- **URL:** não há rota `remarcar` em `core/urls.py`.
- **VIEW:** `ConsultaForm` é usado apenas em `agendar_consulta`, não em edição de data/hora.
- **PERMISSÃO:** não há função específica de remarcação.
- **ALTERAÇÃO:** não há mutação de reagendamento na aplicação web auditada. Não existe choice `remarcada` em `Consulta.Status`.
- **AUDITORIA:** não aplicável a fluxo inexistente.
- **TESTE:** não há teste de remarcação identificado.

Limitação mantida: remarcação não foi encontrada implementada na aplicação.

A transição `confirmada` → `agendada` é desfazer confirmação, não remarcar.

Observação (fora da certificação da aplicação web): `ConsultaAdmin` permite editar `data`, `hora_inicio`, `hora_fim` e `status` no Django Admin, sem passar por `alterar_status_consulta` nem por `_registrar_auditoria`. Isso **não** certifica remarcação na aplicação. A ausência de choice `remarcada` **não** foi classificada automaticamente como defeito (decisão já registrada em A-003).

### 3. Fora do recorte certificado de A-004

Ainda não certificados por esta etapa:

- LGPD além da visibilidade/autorização já examinada;
- Django Admin como canal paralelo de alteração de consulta;
- conflito de horário / `Disponibilidade` no agendamento (`ConsultaForm` sem `clean` de sobreposição identificado);
- reabertura de status finais;
- GET em `/status/` (405 esperado por `@require_POST`, sem teste explícito identificado);
- formulário de status inválido: redirect sem mensagem ao usuário.

Nenhuma pendência acima foi corrigida em código.

### 4. Bloqueadores para produção (A-004)

Os itens abaixo estão classificados como PARCIALMENTE CERTIFICADO ou NÃO CERTIFICADO e são tratados como **bloqueadores para uso em produção**, não apenas como pendências documentais.

Estes itens **não** bloqueiam o registro documental da A-004 nem um eventual commit apenas dessa auditoria documental. **Bloqueiam** a leitura de “A-004 = pronto para produção”. Devem ser tratados em auditoria numerada específica antes de deploy. Nenhuma correção de código foi autorizada ou executada nesta atualização.

#### 4.1 Remarcação — NÃO CERTIFICADO / NÃO IMPLEMENTADO

*Risco:* R-002  
*Prioridade:* ALTA — bloqueia uso real do consultório.

Não existe fluxo de remarcação na aplicação. Cancelar e recriar **não** preserva adequadamente o vínculo/histórico da consulta original. É necessária rastreabilidade administrativa. Prioridade ALTA / bloqueador de produção (R-002). Arquitetura não decidida; implementação não autorizada.

#### 4.2 Agendamento sem auditoria de criação

*Risco:* R-003  
*Prioridade:* ALTA — risco de compliance em dados de saúde.

O fluxo de criação de consulta não registra quem criou o agendamento (usuário, timestamp de criação de forma auditável). Risco de rastreabilidade em caso de disputa sobre autoria do agendamento.

#### 4.3 Falta (“faltou”) sem teste HTTP específico

*Risco:* R-004  
*Prioridade:* MÉDIA.

O fluxo está certificado por leitura de código, mas não há teste via requisição HTTP real cobrindo esse status. Comportamento em produção não deve ser considerado garantido até esse teste existir.

Tratamento previsto: auditoria **A-005** (ainda não iniciada).

---

## A-005 — Remarcação, Auditoria de Criação e Cobertura de Testes

*Estado:* NÃO INICIADA

*Origem:* bloqueadores identificados na A-004 (R-002, R-003, R-004)

Nenhuma certificação, implementação, branch, migration, teste novo ou integração foi executada nesta abertura de etapa.

### Escopo

1. **R-002 — Remarcação de consulta (ALTA)**
   - Definir se remarcação será:
     (a) novo campo/estado na própria `Consulta` (preserva histórico), ou
     (b) novo model de vínculo entre consulta original e nova.
   - Deve manter rastreabilidade: quem remarcou, de qual data/hora para qual, e por quê (campo opcional de motivo).
   - Definir se remarcação dispara notificação (mesmo que só na Etapa 5+/WhatsApp futura, deixar o gancho pronto).

2. **R-003 — Auditoria de criação de agendamento (ALTA)**
   - Registrar, na criação da consulta: usuário responsável, timestamp, e origem (painel admin, formulário, etc.).
   - Decidir se isso é um campo direto no model `Consulta` ou um model de log separado (ex.: `LogAuditoria`) reutilizável para outras ações futuras.

3. **R-004 — Teste HTTP para status “faltou” (MÉDIA)**
   - Escrever teste de integração cobrindo a view que marca falta, validando: permissão, mudança de status, e efeito colateral (se houver).

### Fora de escopo nesta auditoria

- Conflito de horário/sala (dupla marcação) — não foi levantado até agora em nenhuma auditoria anterior; se for prioridade, precisa virar item explícito antes de entrar aqui.
- Qualquer alteração em Locação de Consultórios (módulo pausado).

### Decisões ainda não tomadas (bloqueiam implementação)

A A-005 **não escolhe** as alternativas abaixo até aprovação explícita:

- Remarcação: opção (a) ou (b).
- Auditoria de criação: campos em `Consulta` ou model de log separado reutilizável.
- Notificação na remarcação: gancho apenas vs. disparo imediato (e-mail/WhatsApp permanecem fora até etapa própria).

### Regra de trabalho

Seguir o fluxo já definido:

1. GPT certifica estado real;
2. Claude revisa riscos/lacunas;
3. aprovação;
4. branch isolada;
5. implementação pelo agente definido;
6. testes;
7. nova auditoria antes de integrar.

Não implementar, não criar branch, não criar migration e não integrar enquanto o estado for NÃO INICIADA e as decisões acima não forem aprovadas.

### Reconciliação documental — OPÇÃO 1 (17/09/2026)

**Aprovado por usuário + GPT (coordenação).** A OPÇÃO 2 foi rejeitada.

Remarcação passou a constar do **roteiro ativo** de Agenda/Consulta no `PLANO_MESTRE.md` (A-005 / R-002), **antes** das pendências externas de infraestrutura, sem se misturar a PostgreSQL/SMTP. O `CHECKLIST_PROJETO.md` **não** foi alterado nesta reconciliação.

Registros obrigatórios desta decisão:

- Cancelar e recriar consulta **não** preserva adequadamente o vínculo/histórico da consulta original.
- É necessária **rastreabilidade administrativa** da remarcação (autoria, data/hora de origem e destino, motivo opcional).
- Esta decisão **NÃO autoriza implementar R-002**, abrir branch, criar migration, alterar código ou integrar.
- A **arquitetura da remarcação continua NÃO DECIDIDA** (alternativa (a) ou (b) do escopo).
- Prioridades mantidas: **R-002 = ALTA / bloqueador de produção**; **R-003 = ALTA**; **R-004 = MÉDIA**.
- **A-005 = NÃO INICIADA** quanto à implementação.

---

# REGISTRO DE RISCOS ABERTOS

## R-001 — SQLite / UniqueConstraint.nulls_distinct

*Origem:* A-001  
*Estado:* ABERTO

O Django informou que SQLite não suporta a constraint indicada.

Necessário determinar a regra de negócio protegida por essa constraint antes de decidir qualquer correção.

---

## R-002 — Remarcação inexistente na aplicação

*Origem:* A-004  
*Estado:* ABERTO  
*Classificação A-004:* NÃO CERTIFICADO / NÃO IMPLEMENTADO  
*Prioridade:* ALTA — bloqueador de produção

Não existe fluxo de remarcação na aplicação. Cancelar e recriar **não** preserva adequadamente o vínculo/histórico da consulta original. É necessária rastreabilidade administrativa (quem remarcou, de qual data/hora para qual, motivo opcional).

Não trata a ausência de choice `remarcada` automaticamente como defeito de model (A-003). O bloqueio é a inexistência do fluxo na aplicação para uso real do consultório.

Roteiro: OPÇÃO 1 aprovada (usuário + GPT, 17/09/2026). Arquitetura ainda **não decidida**. Esta classificação **não autoriza** implementar R-002.

*Tratamento previsto:* A-005 (**NÃO INICIADA** quanto à implementação).

---

## R-003 — Agendamento sem auditoria de criação

*Origem:* A-004  
*Estado:* ABERTO  
*Classificação A-004:* PARCIALMENTE CERTIFICADO  
*Prioridade:* ALTA — bloqueador de produção (compliance / dados de saúde)

O fluxo de criação de consulta não registra quem criou o agendamento (usuário, timestamp de criação de forma auditável). Risco de rastreabilidade em caso de disputa sobre autoria do agendamento.

Evidência já registrada em A-004: `agendar_consulta` não chama `_registrar_auditoria`; não foi identificada `AuditoriaConsulta` na criação; há apenas `cadastrado_em` no model.

*Tratamento previsto:* A-005 (NÃO INICIADA).

---

## R-004 — Status “faltou” sem teste HTTP específico

*Origem:* A-004  
*Estado:* ABERTO  
*Classificação A-004:* PARCIALMENTE CERTIFICADO  
*Prioridade:* MÉDIA — bloqueador de produção para considerar o fluxo garantido

O fluxo está certificado por leitura de código, mas não há teste via requisição HTTP real cobrindo esse status. Comportamento em produção não deve ser considerado garantido até esse teste existir.

Evidência já registrada em A-004: não foi identificado `client.post(..., {'status': Consulta.Status.FALTOU})` nos testes rastreados.

*Tratamento previsto:* A-005 (NÃO INICIADA).

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

*A-005 — Remarcação, Auditoria de Criação e Cobertura de Testes*

*Estado:* NÃO INICIADA

*Estado da implementação:* NÃO INICIADA

Origem: R-002 (ALTA / bloqueador), R-003 (ALTA), R-004 (MÉDIA). A-004 permanece encerrada no recorte já certificado e **não** significa pronto para produção.

OPÇÃO 1 aprovada (usuário + GPT, 17/09/2026): remarcação está no roteiro ativo do plano mestre. Isso **não** autoriza implementar R-002 nem abrir branch da A-005.

Não iniciar certificação de estado real, revisão Claude, branch isolada, implementação, testes novos, commit, push, merge ou deploy sem autorização explícita da próxima ação do fluxo de trabalho da A-005.
