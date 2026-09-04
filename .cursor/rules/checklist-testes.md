# Checklist de testes antes de fechar uma etapa

Antes de considerar qualquer etapa concluída, verificar:

1. `python manage.py check` sem erros.
2. Migrations geradas e aplicadas sem conflito (`makemigrations` + `migrate`).
3. Funcionalidade testada manualmente no navegador (não só no admin).
4. Se envolve formulário: testar envio válido E envio com campo obrigatório vazio.
5. Se envolve busca/filtro: testar com resultado, sem resultado e campo vazio.
6. Se mexeu em texto com acento: conferir se renderiza certo na tela (evitar bug de encoding).
7. Servidor local sobe sem warning novo (`python manage.py runserver`).
8. Só depois de tudo isso, perguntar ao usuário se pode avançar para a próxima etapa.

Nunca marcar uma etapa como "concluída" sem passar por esse checklist.
