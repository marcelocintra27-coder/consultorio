# Item 10 — Prescrições: relatório final

Concluído em 15/09/2026. Escopo: somente o recorte aprovado de prescrições.

## Ponto de interrupção e recuperação

A tarefa anterior foi interrompida pelo limite de uso depois de gerar
`core/migrations/0028_prescricoes.py` e executar `manage.py check`. Já existiam
modelos, formulários, rotas, templates, assinatura, serializador de hash,
retificação, PDF e dependência ReportLab. Faltavam testes específicos, validação
completa e visual, correções de integração e atualização da documentação.

Na pasta encontrada em 15/09, os novos arquivos continuavam presentes, mas
arquivos rastreados haviam retornado a uma base anterior. O stash `fd514c9`
preservava as integrações de prescrições e das etapas anteriores. Foram
recuperados 43 arquivos dessa cópia, com comparação de três versões: base
`faae50e`, pasta atual e stash. Os quatro conflitos em `core/admin.py`,
`core/models.py`, `core/urls.py` e `core/views.py` foram resolvidos preservando
as duas alterações. O stash não foi aplicado nem descartado; seu conteúdo foi
lido e combinado com os arquivos atuais.

Foram mantidas as alterações posteriores de CPF opcional e digitalização de
fichas, incluindo migrations `0029`, `0030` e `0031`. A recuperação também
recolocou as dependências clínicas, financeiras e de segurança já implementadas.
Não foram criadas novas regras financeiras ou novos fluxos de imagens/exames.

## Resultado funcional

- Prescrição vinculada ao paciente e ao profissional, com identificação/CRO.
- Um ou vários medicamentos, apresentação, quantidade, posologia, via, duração,
  orientações e texto livre.
- Rascunho editável pelo profissional responsável; versão evita sobrescrita
  por formulário antigo.
- Assinatura pelo dentista ativo com vínculo clínico. Usuário criador e usuário
  assinante ficam registrados separadamente; contas do mesmo profissional
  mantêm o acesso permitido pela arquitetura existente.
- Original, medicamentos e assinatura imutáveis após emissão, inclusive no
  Admin e em alterações/exclusões pelo ORM.
- Retificação complementar com autor, CRO, justificativa, conteúdo e assinatura
  próprios, vinculada ao original. O nome do profissional vem da conta
  autenticada. A ação aparece no histórico da prescrição.
- Hashes de conteúdo e imagem verificados, mantendo os serializadores antigos.
- Impressão e PDF incluem original e retificações, bloqueados quando faltam
  assinaturas, arquivos ou integridade.
- Secretária, auxiliar, staff sem autorização e dentista sem vínculo não
  acessam prescrições. Admin sem perfil prescritor não emite/assina.

## Correções concluídas nesta retomada

1. Rascunho pode ser salvo sem assinatura no navegador. Foram alinhadas as duas
   cópias de `assinatura.js`, pois `static/core/js/assinatura.js` tinha prioridade
   sobre a cópia do app. Preservação do desenho após erro e suporte existente a
   quadros dinâmicos também passaram a ser servidos pela cópia correta.
2. IDs de medicamentos de outra prescrição são rejeitados pelo formset.
3. PNG corrompido é rejeitado antes da assinatura, evitando documento emitido
   cuja imagem falharia ao gerar PDF.
4. Retificação de prescrição usa o nome do profissional autenticado e registra
   evento no histórico; não altera o original.
5. Verificação exige uma única assinatura profissional e identificação
   coerente com o documento.
6. PDF com texto longo foi ajustado para aproveitar a primeira página e manter
   títulos e conteúdo legíveis, sem cortes ou sobreposições.
7. Erros do campo de versão são exibidos. A página usa versão explícita do
   JavaScript para evitar a cópia anterior em cache.

## Migration e preservação dos dados

`0028_prescricoes` já estava aplicada no banco local antes desta retomada,
junto com as migrations posteriores até `0031`. Sua definição foi conferida
contra os modelos. Nenhuma nova migration foi necessária.

- `manage.py migrate --noinput`: nenhuma migration a aplicar.
- `makemigrations --check --dry-run`: nenhuma mudança detectada.
- O banco novo de testes executou toda a cadeia de migrations com sucesso.
- Comparação antes/depois: as **64 tabelas** do banco real tinham as mesmas
  linhas, incluindo usuários, documentos, assinaturas, financeiro e migrations.
- Testes e navegação usaram banco/mídia descartáveis e dados exclusivamente
  fictícios. Não foram inseridos dados de teste no banco real.

Uma cópia do banco anterior e evidências locais estão em
`tmp/prescricoes-auditoria/`, caminho excluído do Git. O PDF é gerado em memória
na aplicação; não introduz armazenamento persistente de PDFs.

## Validação final

| Verificação | Resultado |
| --- | --- |
| Prescrições | 28 testes aprovados |
| Integridade documental anterior | 25 testes aprovados |
| Execução específica conjunta | 53 testes, zero falhas |
| Suíte completa | 178 testes, zero falhas |
| Django `check` | Sem erros; somente `models.W047` conhecido |
| Migrations | Sem pendências ou diferenças de modelos |
| `git diff --check` | Sem erros |
| UTF-8 | 108 arquivos verificados antes deste relatório, sem caracteres de substituição |
| Banco real | 64 tabelas idênticas à cópia inicial |

Comando específico:

```powershell
.venv/Scripts/python.exe manage.py test core.test_prescricoes core.test_documentos_integridade --noinput
```

A suíte completa usou `call_command('test', interactive=False, verbosity=1)`
com hasher rápido somente no processo de testes. As configurações de senha da
aplicação não foram alteradas para essa aceleração.

Os testes cobrem permissões, autoria forjada, IDs de outro documento, CSRF,
assinatura obrigatória, conteúdo/CRO/posologia, rascunho, versões antigas,
reenvio, falha de assinatura com rollback, Admin, ORM/cascatas, retificação,
hash ausente, imagem ausente/adulterada, conteúdo adulterado, PDF, texto longo,
escape de HTML e contas distintas do mesmo profissional.

### Conferência no navegador e PDF

Confirmados no navegador: login, rascunho sem assinatura, edição, botão de
adicionar medicamento, bloqueio de assinatura vazia, erro de CRO obrigatório,
emissão com traço fictício, assinatura visível, integridade, retificação
vinculada e página para impressão. A visualização ocorreu em janela estreita,
com campos e ações acessíveis.

Os PDFs de exemplo foram renderizados com Poppler e inspecionados: prescrição
com múltiplos medicamentos e retificação em páginas separadas, além de texto
longo em cinco páginas. Não houve cortes ou sobreposição de conteúdo.
Impressão em impressora física não foi executada.

## Arquivos do recorte de prescrições

Já existentes e reaproveitados, com integrações recuperadas quando necessário:

- `core/models.py`, `core/admin.py`, `core/admin_clinico.py`, `core/apps.py`.
- `core/permissoes.py`, `core/urls.py`, `core/assinatura.py`.
- `core/protecao_clinica.py`, `core/sinais_clinicos.py`.
- `core/prescricoes.py`, `core/prescricao_conteudo.py`, `core/prescricao_pdf.py`.
- `core/integridade_documentos.py`, `core/retificacoes.py`.
- `core/migrations/0028_prescricoes.py` — preservada, não regenerada.
- `core/templates/core/listar_prescricoes.html`, `form_prescricao.html`,
  `ver_prescricao.html`, `imprimir_prescricao.html`.
- `core/templates/core/includes/item_prescricao_form.html`,
  `prescricao_conteudo.html`, `integridade_documento.html`.
- Atalhos em `core/templates/core/ficha_consulta.html`, `form_paciente.html`
  e `listar_pacientes.html`.
- `core/static/core/js/prescricao.js` e `requirements.txt` (`reportlab==4.4.9`).

Alterados especificamente para fechar as pendências nesta retomada:

- `core/prescricoes.py`, `core/retificacoes.py`,
  `core/integridade_documentos.py`, `core/prescricao_pdf.py`.
- `core/templates/core/form_prescricao.html`.
- `core/static/core/js/assinatura.js` e `static/core/js/assinatura.js`.
- `.gitignore`, `CHECKLIST_PROJETO.md` e `PLANO_MESTRE.md`.

Criados nesta retomada:

- `core/test_prescricoes.py`.
- `RELATORIO_ITEM10_PRESCRICOES.md`.

O inventário da recuperação está em `tmp/prescricoes-auditoria/recuperacao.json`;
os quatro conflitos indicados no inventário foram resolvidos conforme descrito
acima. Logs finais: `especificos-final.txt` e `suite-final.txt` na mesma pasta.

## Limites e encerramento

Permanece o warning conhecido `models.W047`: SQLite não implementa
`UniqueConstraint.nulls_distinct` do modelo `PrecoProcedimento`, sem relação
com o recorte de prescrições. PostgreSQL, mídia persistente, SMTP e backups de
produção continuam nas pendências já documentadas.

Nenhum commit, push ou deploy foi executado. Não houve `git add`, mudança de
branch, descarte de stash ou alteração de dados clínicos históricos.
