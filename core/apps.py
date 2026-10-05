from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        from django.db.models import fields as campos

        # Django 6 mostra "- Select an option -" quando o campo não define o texto.
        campos.BLANK_CHOICE_LABEL = 'Escolha uma opção'
        from . import sinais_acesso  # noqa: F401
        from . import sinais_clinicos  # noqa: F401
