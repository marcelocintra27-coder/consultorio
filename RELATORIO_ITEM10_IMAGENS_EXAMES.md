# Item 10 — imagens e exames

Data: 16/09/2026. Implementação e testes locais concluídos; ativação operacional
depende das pendências reais explicitadas abaixo. Prescrições permanecem
concluídas, com seus arquivos e comportamento preservados.

## Entrega

App independente `exames`, integrado por atalhos nas telas de paciente e consulta.
Listagem, inclusão, detalhes, download, correção com novo arquivo, invalidação
justificada, reinspeção de quarentena e histórico protegido.

- Paciente obrigatório; consulta opcional validada contra paciente e usuário.
- Dentista ativo vinculado e superusuário podem consultar/anexar; correção e
  invalidação somente por autor ainda autorizado ou superusuário. Secretária,
  auxiliar e staff isolado não recebem acesso. Autoria não é recebida do formulário.
- JPEG/PNG/PDF: um arquivo por envio, até 20 MiB, 40 megapixels ou 100 páginas.
  Tipo declarado pelo navegador não é confiado. PDFs criptografados, malformados,
  ativos, com formulários ou anexos são recusados de forma conservadora.
- Arquivo temporário privado desde o recebimento, limite de bytes no streaming,
  verificação em subprocesso com teto de memória de 512 MiB e timeout de 15s.
- ClamAV INSTREAM por loopback; aprovação permite download, detecção bloqueia,
  falha/ausência mantém quarentena. Sem liberação manual e sem envio a IA.
- Originais e metadados imutáveis via aplicação/ORM/Admin; UUID para armazenamento,
  SHA-256 e tamanho conferidos antes de cada download. Hash não é assinatura clínica.
- Downloads com autorização por objeto, attachment, no-store e nosniff. Originais
  invalidados ficam no histórico e só são baixados se a segurança estiver aprovada.
- Eventos imutáveis de inclusão, inspeção, consulta, download iniciado, negativa,
  correção e invalidação. Não é afirmada conclusão do recebimento pelo navegador.
- Falhas de armazenamento/transação removem somente o arquivo novo não registrado.
  Escrita exclusiva impede sobrescrita. Quedas abruptas são detectáveis pelo inventário
  de órfãos; não existe exclusão automática de originais.

## Migration

`exames/migrations/0001_initial.py`, dependente de `core.0031` e do usuário:

- Cria `Exame` e `EventoExame`.
- Protege vínculos com paciente, consulta, usuário e registro anterior.
- Garante arquivo não vazio e um único evento de invalidação/substituição por original.
- Não tem RunPython, conversão, exclusão ou alteração de tabelas clínicas anteriores.

Aplicada no banco local após testes. Nenhuma migration de prescrições foi alterada.
Foram acrescentados uma migration registrada, dois content types e oito permissões
técnicas. Nenhuma permissão foi atribuída a usuário/grupo existente.

## Arquivos desta entrega

Criados:

- `exames/__init__.py`, `apps.py`, `models.py`, `signals.py`, `admin.py`.
- `exames/config.py`, `permissoes.py`, `antivirus.py`, `worker.py`, `storage.py`, `uploads.py`.
- `exames/forms.py`, `services.py`, `views.py`, `urls.py`, `tests.py`.
- `exames/migrations/__init__.py`, `0001_initial.py`.
- `exames/templates/exames/lista.html`, `form.html`, `detalhe.html`.
- `exames/management/__init__.py`, `commands/__init__.py`,
  `commands/verificar_exames.py`, `commands/limpar_temporarios_exames.py`.
- Este relatório.

Alterados somente para integração/documentação:

- `consultorio/settings.py`: registro do app, sem alterar configurações de ambiente.
- `core/urls.py`: inclusão do namespace/rotas de exames.
- `core/templates/core/form_paciente.html`, `listar_pacientes.html`,
  `ficha_consulta.html`: novos atalhos dentro dos blocos clínicos existentes.
- `requirements.txt`: Pillow 12.3.0 (já instalado) declarado diretamente e pypdf 6.19.0.
- `.gitignore`, `.dockerignore`: exclusão de arquivos privados e evidências locais.
- `CHECKLIST_PROJETO.md`, `PLANO_MESTRE.md`: atualizados somente após validação final.

A dependência preexistente `anthropic==1.6.0` estava declarada, mas ausente no
ambiente virtual; foi instalada para permitir carregar o projeto e testar a
regressão. Não houve edição do módulo de digitalização nem chamada de IA.

## Validação executada

| Verificação | Resultado |
| --- | --- |
| Testes específicos de exames | 37 aprovados |
| Regressão completa, incluindo prescrições | 215 aprovados, zero falhas |
| Django check | Somente `models.W047` preexistente |
| Migrations versus modelos | Nenhuma mudança pendente |
| pip check | Nenhum requisito quebrado |
| git diff --check | Sem erros |
| Navegador | Desktop e 390×844, somente dados fictícios |
| Restauração conjunta local | 67 tabelas iguais; três arquivos íntegros; download/quarentena preservados |

Cobertura: perfis, autor forjado, perda do vínculo, dentista inativo, troca de
IDs de paciente/consulta/arquivo, CSRF válido e inválido, múltiplos arquivos,
limite exato/excesso de bytes, pixels e páginas, arquivo vazio/corrompido,
extensão falsa, MIME não confiado, nome malicioso, escape de HTML, PDF com senha,
JavaScript e anexo, timeout do validador, falta de espaço, falha de gravação,
rollback de auditoria, indisponibilidade/detecção/aprovação do scanner, protocolo
INSTREAM, reinspeção, adulteração/ausência, download autorizado, imutabilidade,
Admin, cascatas, correção sem sobrescrita, invalidacao única, concorrência real
em duas threads, backup de arquivos, limpeza restrita de temporários e integração
dos atalhos. Não foram criados dados fictícios no banco real.

No navegador foram confirmados: login fictício, lista, formulário em desktop e
celular, upload real de PNG fictício para quarentena, ausência de download,
reinspeção permanecendo bloqueada, invalidação justificada e histórico legível.
Os cenários de inspeção aprovada/detectada usam respostas controladas em testes;
não houve homologação de um motor antimalware real.

Comando específico: `.venv/Scripts/python.exe -B manage.py test exames --noinput`.
A suíte completa usou `call_command('test', interactive=False, verbosity=1)` com
hasher rápido somente no processo de teste, sem alterar autenticação da aplicação.

## Preservação

Inventário inicial e cópia SQLite foram criados antes das mudanças, em
`tmp/exames-auditoria/`, excluído de Git e da imagem Docker.

- 65 tabelas inventariadas, incluindo `sqlite_sequence` (64 outras tabelas).
- Todas as linhas anteriores preservadas. Somente acréscimos em metadados Django
  citados acima; sequências técnicas ajustadas por essas inclusões.
- 1.560 arquivos anteriores conferidos por SHA-256: 1.555 inalterados e cinco
  arquivos de integração modificados, enumerados acima.
- Todos os 1.354 arquivos da pasta media preservados byte a byte.
- Arquivos próprios de prescrições, assinaturas, digitalização, prontuário,
  financeiro e serializadores históricos inalterados.
- Novas tabelas de exames e auditoria continuam vazias no banco real.

Evidências: `antes.json`, `antes.sqlite3`, `preservacao-final.json`,
`testes-exames-final.txt`, `regressao-final.txt`, `migration-local.txt`,
`restauracao.txt`. A base visual e sua restauração são separadas do banco real.

## Operação local e parâmetros

Por padrão, arquivos novos ficam em `private_exames/`, fora de `/media/`.
Em produção, o módulo recusa uploads sem `EXAMES_ROOT` explicitamente configurado;
essa configuração não foi realizada nesta entrega. A raiz não pode estar dentro
da mídia pública ou dos estáticos, nem conter essas pastas.

Parâmetros aceitam setting ou variável de ambiente, sem alterar defaults globais:

| Parâmetro | Padrão |
| --- | --- |
| EXAMES_ROOT | private_exames local; obrigatório explicitamente em produção |
| EXAMES_MAX_BYTES | 20971520 |
| EXAMES_MAX_PIXELS | 40000000 |
| EXAMES_MAX_PAGES | 100 |
| EXAMES_VALIDATION_TIMEOUT | 15 segundos |
| EXAMES_SCAN_TIMEOUT | 15 segundos |
| EXAMES_CLAMD_PORT | 3310, host fixo 127.0.0.1 |
| EXAMES_RESERVA_BYTES | 104857600 livres além do arquivo |

`manage.py verificar_exames` apresenta integridade, quarentena, bloqueados,
órfãos e temporários sem expor títulos/conteúdo clínico nem modificar registros.
`manage.py limpar_temporarios_exames` apenas conta temporários abandonados acima
de 24h; `--executar` remove exclusivamente esses temporários, com auditoria.
Não remove originais, arquivos em quarentena ou documentos históricos.

## Pendências reais e limites

### Revalidação local em 19/09/2026

Após configuração administrativa manual pelo usuário, o serviço Windows `clamd`
foi observado Running e Automatic (`sc queryex`: PID 13880). Os arquivos
`main.cvd`, `daily.cvd` e `bytecode.cvd` existem em
`C:\Program Files\ClamAV\database`, com horários de gravação em 19/09/2026,
e `sigtool --info` confirmou a integridade das três bases. `daily.cvd` informa
build em 19/09/2026 06:24 UTC, versão 28128. O `netstat` mostrou escuta apenas
em `127.0.0.1:3310`, sem escuta em endereço de rede ou em `0.0.0.0`.

O daemon respondeu `PONG` ao comando local e `stream: OK` ao INSTREAM de texto
inofensivo. A função real `exames.antivirus.inspecionar(BytesIO(...))` retornou
`liberado` para conteúdo inofensivo. Não se usou malware real nem se executou
upload HTTP ou download nesta revalidação. O scan semanal foi informado pelo
usuário como iniciado; as tarefas `ClamAV-Update` e `ClamAV-Scan-Semanal` e seus
resultados não puderam ser consultados nesta sessão (`Acesso negado`). O usuário
informou `ClamAV-Update` com `LastTaskResult = 0`; a presença e integridade das
bases foram verificadas independentemente.

Há dois processos `clamd` (PIDs 13880 e 14784) associados à escuta em
`127.0.0.1:3310`; o primeiro é o PID do serviço. Falta identificar por que o
segundo processo está ativo e confirmar continuidade após reinício, sem alterar
o serviço durante esta auditoria. A ausência de motor antimalware local foi
resolvida; homologação completa do fluxo e implantação em produção permanecem
pendentes.

1. Concluir homologação de detecção e limites com amostra de teste apropriada,
   fluxo HTTP e disponibilidade após reinício; repetir instalação e validação
   de ClamAV/assinaturas no ambiente de produção. A implementação conecta apenas
   a loopback e falha de modo fechado. O teste histórico de upload ocorreu
   antes da instalação local e permaneceu corretamente em quarentena. As respostas
   simuladas de detecção ainda não comprovam capacidade real de detecção.
2. Provisionar volume persistente privado, capacidade e permissões de acesso
   operacional. O disco de 1 GB documentado não foi provisionado nem alterado.
3. Definir responsáveis, tratamento/prazos finais de quarentena e retenção,
   frequência dos backups e metas de recuperação. Política inicial: preservar
   todos os originais e seu histórico, sem expurgo automático.
4. Validar restauração e persistência no ambiente de produção. A prova realizada
   foi local com SQLite e arquivos fictícios; não equivale à homologação de
   PostgreSQL, volume ou backup de produção.

Proteções da aplicação não impedem alteração por quem controla diretamente
banco/sistema de arquivos. Erros de configuração, ameaças não detectadas pelo
antimalware e acesso operacional exigem os controles de infraestrutura citados.
O fluxo preexistente de digitalização não foi refeito; suas lacunas auditadas
anteriormente permanecem fora desta entrega.

Não houve deploy, commit/push, alteração de configuração de produção ou avanço
para outro item. Implementação local concluída não significa produção liberada.

Referências técnicas consultadas: [ClamAV INSTREAM](https://docs.clamav.net/manual/Usage/ClamdProtocol.html)
e [PdfReader](https://pypdf.readthedocs.io/en/6.8.0/modules/PdfReader.html).
