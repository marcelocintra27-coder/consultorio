# Import de planilha de pacientes (migração de fichas físicas)

Já existe o comando `core/management/commands/importar_pacientes.py`, que lê
`planilha_migracao_pacientes.xlsx` (abas `Cadastro_Pacientes` e
`Evolucao_Atendimentos`) e importa pacientes + evoluções para o banco.

Ao reaproveitar ou estender esse padrão (ex.: quando a digitalização das
400-500 fichas terminar):

1. Manter o mesmo nome de abas e colunas já usado, ou documentar claramente
   qualquer mudança de formato antes de rodar.
2. Rodar sempre num banco de teste/backup primeiro, nunca direto em produção.
3. Validar duplicidade por CPF antes de importar (evitar paciente duplicado).
4. Depois da importação, checar manualmente uma amostra de registros
   (nome, CPF, evoluções) para confirmar que os acentos e datas vieram certos.
5. Guardar o `.xlsx` original fora do repositório git (dado sensível — não commitar).
6. Se o volume de fichas crescer muito, considerar rodar a importação em lotes
   menores para facilitar a conferência de erros.
