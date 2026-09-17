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

*Estado:* NÃO AUDITADO

### Objetivo da próxima auditoria

Mapear:

AÇÃO → TELA/TEMPLATE → URL → VIEW/FORM/SERVIÇO → PERMISSÃO → ALTERAÇÃO → AUDITORIA/LOG → TESTE

Devem ser examinados especialmente:

- agendamento;
- confirmação;
- chegada do paciente;
- realização/conclusão;
- falta;
- cancelamento;
- remarcação;
- permissões por perfil.

A auditoria deverá inicialmente ser SOMENTE LEITURA.

Nenhuma alteração deve ser implementada antes de distinguir claramente:

1. o que já existe;
2. o que funciona;
3. o que existe parcialmente;
4. o que realmente está faltando.

---

# REGISTRO DE RISCOS ABERTOS

## R-001 — SQLite / UniqueConstraint.nulls_distinct

*Origem:* A-001  
*Estado:* ABERTO

O Django informou que SQLite não suporta a constraint indicada.

Necessário determinar a regra de negócio protegida por essa constraint antes de decidir qualquer correção.

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

*A-004 — Auditoria funcional e de permissões da Agenda / Consulta*

Estado atual:

*NÃO AUDITADO — aguardar início da auditoria em modo leitura.*
