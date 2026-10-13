"""Vérification de la distribution compilée avec ses outils portables."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
dist = root / 'dist' / 'add_dub'
exe = dist / 'add_dub_console.exe'
ffmpeg = dist / 'tools' / 'ffmpeg' / 'bin' / 'ffmpeg.exe'
ffprobe = ffmpeg.with_name('ffprobe.exe')
with ExitStack() as cleanup, tempfile.TemporaryDirectory(prefix='adddub-distribution-') as directory:
    work = Path(directory)
    source = work / (work.name + '.mkv')
    persistent_srt = dist / 'srt' / source.with_suffix('.srt').name
    cleanup.callback(persistent_srt.unlink, missing_ok=True)
    source.with_suffix('.srt').write_text('1\n00:00:00,100 --> 00:00:01,800\nBonjour tout le monde.\n', encoding='utf-8')
    options = work / 'options.conf'
    options.write_text('', encoding='utf-8')
    env = dict(os.environ, ADD_DUB_OPTIONS=str(options))
    env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    subprocess.run([str(ffmpeg), '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                    'color=c=blue:size=64x64:rate=10:duration=2', '-f', 'lavfi', '-i',
                    'sine=frequency=440:duration=2', '-c:v', 'mpeg4', '-c:a', 'pcm_s16le',
                    str(source)], check=True, timeout=30, env=env)
    subprocess.run([str(exe), '--help'], cwd=work, env=env, check=True, timeout=30)
    command = [str(exe), '--batch', '--input', str(source), '--output-dir', str(work / 'output'),
               '--tts-engine', 'onecore', '--offline', '--no-translate', '--audio-codec', 'pcm_s16le']
    subprocess.run(command, cwd=work, env=env, check=True, timeout=120)
    outputs = list((work / 'output').glob('*.mkv'))
    assert len(outputs) == 1, outputs
    data = json.loads(subprocess.check_output([str(ffprobe), '-v', 'error', '-show_streams',
                      '-show_format', '-of', 'json', str(outputs[0])], env=env, timeout=30))
    audio = [s for s in data['streams'] if s['codec_type'] == 'audio']
    assert len(audio) == 2 and all(s['channels'] == 2 for s in audio), data
    assert all(s['codec_name'] == 'pcm_s16le' for s in audio), data
    assert persistent_srt.is_file(), persistent_srt
    assert any(s['codec_type'] == 'subtitle' for s in data['streams']), data
    assert float(data['format']['duration']) > 1.9, data
    before = outputs[0].read_bytes()
    subprocess.run(command + ['--skip-existing'], cwd=work, env=env, check=True, timeout=30)
    assert outputs[0].read_bytes() == before
    print('OK distribution : aide, outils embarqués, OneCore hors ligne, workers spawn, muxage stéréo, SRT persistant, sortie et skip-existing.')
