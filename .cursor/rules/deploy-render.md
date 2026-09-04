# Deploy no Render

Checklist antes de qualquer deploy:

1. `DEBUG=False` em produção.
2. `ALLOWED_HOSTS` inclui o domínio do Render — sem remover para testar local
   (usar `127.0.0.1`/`localhost` só em ambiente de desenvolvimento).
3. Variáveis sensíveis (SECRET_KEY, credenciais de banco/nuvem) só em variáveis
   de ambiente do Render, nunca hardcoded no código nem commitadas.
4. `db.sqlite3` nunca vai para produção via git — se o Render usar SQLite,
   confirmar que o disco é persistente; caso contrário, planejar migração para
   Postgres antes de ir ao ar de verdade.
5. Rodar `python manage.py check --deploy` para pegar avisos de segurança antes
   de subir.
6. Testar o fluxo principal (cadastro, busca, admin) direto na URL do Render
   depois do deploy, não só localmente.
7. Se o módulo de imagens (S3/Cloudinary) já estiver ativo, confirmar que as
   credenciais de produção estão configuradas e que os buckets não são públicos.
