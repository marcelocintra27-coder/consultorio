from django.core.management.base import BaseCommand
from django.db import transaction

from locacao.models import Dentista, Sala

CADASTRO = (
    ("Simone", "Consultório 1"),
    ("Claudia", "Consultório 2"),
    ("Adriana Nasser", "Consultório 3"),
)


def achar_sala(nome_alvo):
    alvo = nome_alvo.casefold().strip()
    for sala in Sala.objects.all():
        if sala.nome.casefold().strip() == alvo:
            return sala
    return None


class Command(BaseCommand):
    help = "Cadastra as 3 dentistas nos consultórios 1, 2 e 3 e remove a sala Simone."

    def handle(self, *args, **options):
        with transaction.atomic():
            for nome_dentista, nome_sala in CADASTRO:
                sala = achar_sala(nome_sala)
                if sala is None:
                    sala = Sala.objects.create(nome=nome_sala, ativa=True)
                    self.stdout.write(f"Sala criada: {sala.nome}")
                else:
                    sala.ativa = True
                    sala.save(update_fields=["ativa"])

                ocupante = Dentista.objects.filter(sala=sala).exclude(
                    nome_completo=nome_dentista
                ).first()
                if ocupante:
                    self.stderr.write(
                        self.style.ERROR(
                            f"A sala {sala.nome} já está com {ocupante.nome_completo}."
                        )
                    )
                    raise SystemExit(1)

                dentista, created = Dentista.objects.update_or_create(
                    nome_completo=nome_dentista,
                    defaults={"sala": sala, "ativo": True},
                )
                acao = "cadastrada" if created else "atualizada"
                self.stdout.write(
                    f"Dentista {acao}: {dentista.nome_completo} -> {sala.nome}"
                )

            removidas = 0
            for sala in list(Sala.objects.filter(nome__iexact="Simone")):
                if Dentista.objects.filter(sala=sala).exists():
                    self.stderr.write(
                        self.style.ERROR(
                            f"Não foi possível apagar a sala {sala.nome}: ainda há dentista vinculada."
                        )
                    )
                    raise SystemExit(1)
                sala.delete()
                removidas += 1
            if removidas:
                self.stdout.write(self.style.SUCCESS(f"Salas 'Simone' removidas: {removidas}"))
            else:
                self.stdout.write("Nenhuma sala 'Simone' para remover.")

        self.stdout.write(self.style.SUCCESS("Cadastro das dentistas concluído."))
