# Validação do PostgreSQL local — 19/09/2026

## Escopo e preservação

- PostgreSQL 17 local, serviço `postgresql-x64-17`, porta 5432 em `127.0.0.1`.
- `DATABASE_URL` mantida no `.env` ignorado pelo Git; credenciais não foram
  registradas neste relatório. O Django usa PostgreSQL quando a variável está
  definida e mantém SQLite como alternativa fora de produção.
- Banco principal de homologação: `consultorio_homolog`; usuário exclusivo
  `consultorio_homolog`, sem privilégios de superusuário ou criação de bancos.
- O `db.sqlite3` original não foi migrado, apagado ou sobrescrito. Hash SHA-256
  antes e depois: `9D28E60EC677B60AEB6612FA47E6F5A2A20CFFBEBA0C58DE6B0FE1F75CFAED45`.
  A cópia anterior em `C:\Users\GERAL\Consultorio-Backups\sqlite-pre-postgres-20260919.sqlite3`
  permaneceu íntegra. Ambos apresentaram 67 tabelas e `PRAGMA integrity_check = ok`.

## Banco e backup

- Conexão Django com `consultorio_homolog` bem-sucedida; 62 migrations
  aplicadas, 66 tabelas criadas e nenhum paciente transferido.
- `manage.py check`: aprovado; `makemigrations --check --dry-run`: nenhuma
  mudança; `migrate --check`: aprovado.
- `pg_dump -Fc --no-owner --no-acl` gerou
  `C:\Users\GERAL\Consultorio-Backups\consultorio-homolog-20260919.dump`
  (289.062 bytes; SHA-256
  `c87a060e6751deae4e441cb7723e601189c9d03c5abc56a7db7dec0f4a7bbc70`).
- `pg_restore --exit-on-error --no-owner --no-acl` no banco separado
  `consultorio_homolog_restore`: aprovado. Origem e restauração tiveram 66
  tabelas idênticas, contagens de linhas iguais em todas elas, 62 registros de
  migration, 262 constraints, 244 índices e zero pacientes.

## Testes no PostgreSQL

- `core.test_agenda_a005 --keepdb --noinput`: 18 testes aprovados.
- `exames.tests.ConcorrenciaTests --keepdb --noinput`: 2 testes aprovados.
- Suíte completa no PostgreSQL, `manage.py test --keepdb --noinput`:
  **241 testes executados, 241 aprovados, 0 falhas e 0 erros**.
- Testes diretamente afetados: 21/21 aprovados no PostgreSQL. Os dois testes
  de retry do SQLite também passaram em banco SQLite temporário (2/2).
- `manage.py check`, `makemigrations --check --dry-run`, `migrate --check` e
  `git diff --check`: aprovados.

## Causas identificadas e correções

- `FileResponse.close()` em testes `TestCase` emitia `request_finished` e
  fechava a conexão PostgreSQL usada pela transação. Os testes agora fecham
  apenas os recursos de arquivo da resposta; as verificações de conteúdo,
  permissão e integridade permanecem ativas.
- Dois testes simulavam `OperationalError("database is locked")` e exigiam as
  cinco tentativas do SQLite também no PostgreSQL. Agora conferem retry limitado
  no SQLite e propagação imediata do erro no PostgreSQL, sem alterar o serviço.
- `--keepdb` após `TransactionTestCase` podia deixar ausentes dados carregados
  por migrations. As classes que dependem da tabela Uniodonto e das formas de
  pagamento preparam esses dados em `setUpTestData`, independentemente do estado
  anterior do banco de testes.

## Estado e próximos ajustes

**PostgreSQL local homologado integralmente para o escopo de desenvolvimento e
testes desta etapa.** A aplicação conectou, criou o schema, passou na
restauração e aprovou a suíte completa sem ajustes temporários em processo.
Nenhuma regra de negócio ou migration foi alterada.

Esta validação não cobre migração de dados clínicos reais, backup de mídia,
política de retenção, execução agendada de backups nem infraestrutura externa.
Não houve commit, push ou deploy.
