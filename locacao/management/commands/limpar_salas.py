from django.core.management.base import BaseCommand
from django.db import transaction

from locacao.models import Dentista, Disponibilidade, Sala

SALAS_CORRETAS = frozenset(
    ("Consultório 1", "Consultório 2", "Consultório 3")
)


class Command(BaseCommand):
    help = "Apaga salas de teste, mantendo só Consultório 1, 2 e 3."

    def handle(self, *args, **options):
        erradas = [s for s in Sala.objects.all() if s.nome not in SALAS_CORRETAS]
        if not erradas:
            self.stdout.write("Nenhuma sala errada para remover.")
            return

        with transaction.atomic():
            for sala in erradas:
                dentista = Dentista.objects.filter(sala=sala).first()
                if dentista:
                    self.stderr.write(
                        self.style.ERROR(
                            f"Abortado: a sala '{sala.nome}' esta vinculada a {dentista.nome_completo}."
                        )
                    )
                    raise SystemExit(1)
                Disponibilidade.objects.filter(sala=sala).delete()
                nome = sala.nome
                sala.delete()
                self.stdout.write(f"Sala removida: {nome}")

        restantes = list(Sala.objects.order_by("nome").values_list("nome", flat=True))
        self.stdout.write(self.style.SUCCESS(f"Salas restantes: {', '.join(restantes)}"))
