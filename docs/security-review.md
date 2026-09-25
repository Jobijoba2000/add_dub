# Dépendances : revue du 25 septembre 2026

Le transport utilisé par add_dub impose maintenant la vérification TLS et des délais réseau pour gTTS et GoogleTranslator. Les tests de contrat exécutent les méthodes des bibliothèques installées et vérifient les paramètres effectivement transmis à Requests. Aucun monkey-patch global n'est utilisé.

`requirements.lock.txt` épingle les dépendances directes et transitives avec les SHA-256 des archives Windows x64 / CPython 3.12. Une installation dans une venv neuve depuis ces archives a été vérifiée. `models.lock.json` fixe les révisions des téléchargements OCR, Opus anglais/français et NLLB. Les téléchargements automatiques d'autres dépôts de modèles exigent désormais leur ajout explicite à ce fichier ; NLLB reste le secours multilingue local.

## Résultat de pip-audit

Commande utilisée avec pip-audit 2.10.1 :

```powershell
.cache/audit-venv/Scripts/python.exe -m pip_audit --disable-pip --no-deps -r requirements.lock.txt -f json -o tmp/dependency-audit.json
```

Deux alertes sont encore signalées, sans suppression ni mise à jour forcée incompatible :

| Paquet | Avis renvoyé par le scanner | Analyse et limite |
|---|---|---|
| click 8.1.8 | PYSEC-2026-2132 / CVE-2026-7246, correction annoncée 8.3.3 | Le scanner vise `click.edit()`. add_dub n'appelle pas cette fonction. gTTS 2.5.4 impose `click<8.2`, donc installer 8.3.3 casserait les contraintes déclarées. Une évolution compatible de gTTS ou son remplacement reste nécessaire pour supprimer cette alerte de l'environnement. L'absence d'appel dans add_dub n'est pas une correction de Click. |
| deep-translator 1.11.4 | PYSEC-2022-252 | L'avis historique concerne une prise de contrôle du compte PyPI. La source PyPA liste explicitement 1.8.5 mais contient aussi une plage ouverte à partir de cette version ; le scanner signale donc 1.11.4. Cette alerte ne prouve pas que la version installée contient le code malveillant, et le verrou d'empreintes n'est pas une preuve d'innocuité. Une clarification amont ou une revue de provenance reste nécessaire. |

Source primaire de l'avis historique : [PyPA, PYSEC-2022-252](https://raw.githubusercontent.com/pypa/advisory-database/main/vulns/deep-translator/PYSEC-2022-252.yaml). Pour Click, la description et la version de correction ci-dessus sont celles du résultat local de pip-audit ; le lien d'avis GitHub retourné n'était pas accessible au moment de la revue.

La CI publie le résultat intégral de l'analyse des dépendances comme artefact. Cette étape est informative (`continue-on-error`) pour rendre les alertes visibles sans les ignorer individuellement ; les tests et la compilation restent bloquants. Elle ne doit pas être interprétée comme une certification de sécurité.

## Composants natifs et distribution

La compilation ajoute `THIRD_PARTY.json`, les versions de l'environnement Python, les notices trouvées dans les distributions et les SHA-256 des EXE/DLL de `tools/`. Les licences présentes dans les répertoires des outils sont conservées par leur copie intégrale. L'inventaire n'est pas une conclusion de conformité juridique et ne remplace pas une analyse CVE des binaires natifs ou de Python portable.

Les tests réseau sont simulés pour éviter d'envoyer du contenu utilisateur aux services. La disponibilité future des API Google/Edge, la qualité linguistique des modèles, Windows vierge et les lecteurs d'écran restent à vérifier séparément.
