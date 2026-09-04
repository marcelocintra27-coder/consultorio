# Tratamento de dados sensíveis de pacientes (LGPD)

O sistema armazena dados pessoais e de saúde (CPF, prontuário, evolução clínica,
convênio, fotos de procedimentos). Seguir sempre:

## Nunca fazer
- Nunca logar CPF, dados de prontuário ou evolução em `print()`, `logger` ou
  mensagens de erro/debug.
- Nunca deixar `DEBUG=True` em produção (evita vazar dados sensíveis em páginas de erro do Django).
- Nunca commitar dados reais de paciente em fixtures, exemplos ou testes —
  usar sempre dados fictícios.
- Nunca expor endpoints de paciente/prontuário sem autenticação.

## Sempre fazer
- Restringir acesso ao admin e às views de paciente por login (`@login_required`
  ou equivalente).
- Ao integrar armazenamento em nuvem (S3/Cloudinary) para imagens/RX, usar
  URLs privadas/assinadas, não bucket público.
- Ao exportar relatórios, evitar incluir mais dados sensíveis do que o necessário
  para a finalidade do relatório.
- Ter em mente que campos como CPF e carteirinha de convênio são dados
  pessoais identificáveis — tratar com o mesmo cuidado que dados de saúde.

Esse cuidado vale tanto para código do dia a dia quanto para o módulo de
locação (que não lida com dados de saúde, mas ainda lida com dados de
profissionais e agendamentos).
