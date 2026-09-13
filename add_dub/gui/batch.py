"""Commandes batch copiables et lancement dans un terminal Windows."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def launcher_command(command):
    prefix = [sys.executable] if getattr(sys, 'frozen', False) else [
        str(Path(__file__).resolve().parents[2] / 'start_add_dub.bat')]
    return prefix + command[command.index('--batch'):]


def export_commands(job):
    """Exporte le dossier complet avec les réglages communs du formulaire."""
    if (len(job.sources) == 1 and os.path.isdir(job.sources[0])
            and job.recursive and not job.overrides and not job.folder_configs
            and len(job.selected) == len(job.videos)
            and all(os.path.normcase(os.path.abspath(v.root or '.')) ==
                    os.path.normcase(os.path.abspath(job.sources[0])) for v in job.videos)):
        from add_dub.gui.model import BOOLS, batch_command
        if not job.common.values.get('voice'):
            raise ValueError('Choisissez une voix.')
        flags = dict.fromkeys(BOOLS, False)
        flags.update(translate=job.common.translate, recursive=job.recursive,
                     preserve_tree=job.preserve_tree, skip_existing=job.resume,
                     overwrite=not job.resume, dry_run=job.dry_run)
        return [launcher_command(batch_command(job.common.values, flags, job.sources, job.output))]
    return [launcher_command(command) for _, command in job.commands()]


def command_text(command):
    # Toujours citer les arguments : CMD interprète notamment & et les espaces.
    if any(any(c in arg for c in '\"\r\n\0') for arg in command):
        raise ValueError('La commande contient un caractère incompatible avec CMD.')
    return ' '.join('"' + arg + '"' for arg in command)


def open_terminal(command):
    command_text(command)
    # L’expansion des variables n’est pas récursive : les caractères %, & et
    # autres caractères des chemins restent des données dans la commande CMD.
    environment = os.environ.copy()
    names = [f'ADD_DUB_BATCH_ARG_{i}' for i in range(len(command))]
    environment.update(zip(names, command))
    line = ' '.join('"%' + name + '%"' for name in names)
    return subprocess.Popen(
        f'cmd.exe /d /v:off /s /k "{line}"',
        cwd=str(Path(command[0]).parent), env=environment,
        creationflags=subprocess.CREATE_NEW_CONSOLE)


def batch_text(commands):
    if len(commands) == 1:
        return command_text(commands[0])
    # Chaque lanceur .bat tourne dans son propre CMD afin de revenir au lot.
    # NUL évite que le « pause » du lanceur bloque entre deux vidéos.
    return '\r\n'.join(f'cmd /d /v:off /s /c "{command_text(command)}" <nul'
                       for command in commands)


def write_batch_scripts(commands, directory):
    """Une commande par fichier évite la limite CMD de 8191 caractères par ligne."""
    directory = Path(directory)
    lines = ['@echo off', 'chcp 65001 >nul', 'setlocal DisableDelayedExpansion']
    for index, command in enumerate(commands, 1):
        child = directory / f'video-{index}.cmd'
        child.write_text('@echo off\n' + command_text(command).replace('%', '%%') + '\n',
                         encoding='utf-8')
        lines += [f'echo [BATCH] Video {index}/{len(commands)}',
                  f'cmd /d /v:off /s /c ""%~dp0{child.name}"" <nul',
                  'if errorlevel 1 exit /b 1']
    lines += ['echo [BATCH] Lot termine.', 'endlocal']
    script = directory / 'lot.cmd'
    script.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return script


def open_batch_terminal(commands):
    if len(commands) == 1:
        return open_terminal(commands[0])
    directory = tempfile.mkdtemp(prefix='add-dub-batch-')
    script = write_batch_scripts(commands, directory)
    return open_terminal([str(script)])
