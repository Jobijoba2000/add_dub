"""Transport borné et TLS vérifié pour les versions épinglées des clients.

Les bibliothèques historiques passent verify=False ou omettent timeout.
On remplace leur référence requests dans une copie privée de la méthode :
aucun monkey-patch global, y compris pendant des synthèses concurrentes.
Les tests de contrat doivent accompagner toute mise à jour de ces clients.
"""
from types import FunctionType
import requests

TIMEOUT = (10, 30)


class VerifiedSession(requests.Session):
    def send(self, request, **kwargs):
        from add_dub.io.work import is_offline
        if is_offline():
            raise RuntimeError('Accès réseau interdit en mode hors ligne.')
        kwargs['verify'] = True
        kwargs['timeout'] = TIMEOUT
        return super().send(request, **kwargs)


class Transport:
    Session = VerifiedSession

    def __getattr__(self, name):
        return getattr(requests, name)

    def get(self, url, **kwargs):
        with VerifiedSession() as session:
            return session.get(url, **kwargs)


def secured_method(method):
    namespace = dict(method.__globals__, requests=Transport())
    wrapped = FunctionType(method.__code__, namespace, method.__name__,
                           method.__defaults__, method.__closure__)
    wrapped.__kwdefaults__ = method.__kwdefaults__
    return wrapped


def google_translator(**kwargs):
    from deep_translator import GoogleTranslator

    class BoundedGoogleTranslator(GoogleTranslator):
        translate = secured_method(GoogleTranslator.translate)

    return BoundedGoogleTranslator(**kwargs)


def google_speech(**kwargs):
    from gtts import gTTS

    class VerifiedSpeech(gTTS):
        stream = secured_method(gTTS.stream)

    return VerifiedSpeech(timeout=TIMEOUT, lang_check=False, **kwargs)
