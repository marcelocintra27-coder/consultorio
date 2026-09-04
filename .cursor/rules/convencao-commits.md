# Convenção de commits

Só commitar quando o usuário autorizar explicitamente. Quando autorizado, seguir o padrão:

`tipo: descrição curta em português, no imperativo`

Tipos:
- `feat`: nova funcionalidade (ex.: `feat: adiciona cadastro de paciente`)
- `fix`: correção de bug (ex.: `fix: corrige acentuação quebrada no models.py`)
- `refactor`: mudança de código sem alterar comportamento
- `chore`: tarefas de manutenção (dependências, configuração, .gitignore)
- `docs`: documentação

Regras:
- Um commit por mudança lógica (não misturar cadastro de paciente com ajuste de config no mesmo commit).
- Descrição curta na primeira linha; detalhes extras (se necessário) em linhas separadas abaixo.
- Nunca incluir o banco de dados (`db.sqlite3`) no commit.
- Antes de commitar, rodar o checklist de testes.
