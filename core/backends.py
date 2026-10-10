"""Entrada no sistema sem exigir acento ou maiúscula iguais no nome de acesso.

"Recepção", "recepcao" e "Recepcao " entram na mesma conta "recepcao".
A senha continua conferida exatamente. Se o nome digitado servir para mais
de uma conta, ninguém entra (não adivinhamos).
"""
import unicodedata

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


def normalizar_usuario(texto):
    sem_acento = unicodedata.normalize('NFKD', (texto or '').strip())
    sem_acento = ''.join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.casefold()


class LoginFlexivelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        usuario = self._encontrar(User, username)
        if usuario is None:
            # Mesmo custo de uma senha errada, para não revelar se o nome existe.
            User().set_password(password)
            return None
        if usuario.check_password(password) and self.user_can_authenticate(usuario):
            return usuario
        return None

    @staticmethod
    def _encontrar(User, digitado):
        gerenciador = User._default_manager
        exato = gerenciador.filter(username=digitado.strip()).first()
        if exato is not None:
            return exato
        alvo = normalizar_usuario(digitado)
        if not alvo:
            return None
        iguais = [
            pk for pk, nome in gerenciador.values_list('pk', 'username')
            if normalizar_usuario(nome) == alvo
        ]
        if len(iguais) != 1:
            return None
        return gerenciador.get(pk=iguais[0])
