"""Lecteur libmpv embarqué, sans configuration ni installation extérieure."""
import ctypes as c
import os
from add_dub.player.io.fs import TOOLS_DIR


class Event(c.Structure):
    _fields_ = [('id', c.c_int), ('error', c.c_int), ('userdata', c.c_uint64), ('data', c.c_void_p)]


class EndFile(c.Structure):
    _fields_ = [('reason', c.c_int), ('error', c.c_int)]


class LogMessage(c.Structure):
    _fields_ = [('prefix', c.c_char_p), ('level', c.c_char_p), ('text', c.c_char_p)]


class Player:
    def __init__(self, hwnd, subtitle_language=''):
        directory = TOOLS_DIR / 'mpv'
        library = directory / 'libmpv-2.dll'
        if not library.is_file():
            raise RuntimeError('Moteur vidéo absent : tools/mpv/libmpv-2.dll est nécessaire.')
        self.dll_directory = os.add_dll_directory(str(directory))
        self.lib = c.CDLL(str(library))
        signatures = {
            'mpv_create': (c.c_void_p, []),
            'mpv_initialize': (c.c_int, [c.c_void_p]),
            'mpv_set_option_string': (c.c_int, [c.c_void_p, c.c_char_p, c.c_char_p]),
            'mpv_set_property_string': (c.c_int, [c.c_void_p, c.c_char_p, c.c_char_p]),
            'mpv_get_property_string': (c.c_void_p, [c.c_void_p, c.c_char_p]),
            'mpv_command': (c.c_int, [c.c_void_p, c.POINTER(c.c_char_p)]),
            'mpv_wait_event': (c.POINTER(Event), [c.c_void_p, c.c_double]),
            'mpv_request_log_messages': (c.c_int, [c.c_void_p, c.c_char_p]),
            'mpv_error_string': (c.c_char_p, [c.c_int]),
            'mpv_free': (None, [c.c_void_p]),
            'mpv_terminate_destroy': (None, [c.c_void_p]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args
        self.handle = self.lib.mpv_create()
        self.error = None
        if not self.handle:
            raise RuntimeError('Création du lecteur mpv impossible.')
        try:
            options = {'wid': str(hwnd & 0xffffffff), 'config': 'no',
                       'load-scripts': 'no', 'osc': 'no', 'osd-level': '0',
                       'input-default-bindings': 'no', 'input-vo-keyboard': 'no',
                       'input-cursor': 'no', 'terminal': 'no', 'keep-open': 'yes',
                       'idle': 'yes', 'hwdec': 'auto-safe', 'demuxer': 'lavf'}
            if subtitle_language:
                options['slang'] = subtitle_language
            for name, value in options.items():
                self._check(self.lib.mpv_set_option_string(self.handle, name.encode(), value.encode()))
            self._check(self.lib.mpv_initialize(self.handle))
            self.debug_log = []
            self.lib.mpv_request_log_messages(self.handle, b'warn')
        except Exception:
            self.close()
            raise

    def _check(self, code):
        if code < 0:
            raise RuntimeError(self.lib.mpv_error_string(code).decode('utf-8', 'replace'))

    def _get(self, name, default=''):
        value = self.lib.mpv_get_property_string(self.handle, name.encode())
        if not value:
            return default
        try:
            return c.string_at(value).decode('utf-8', 'replace')
        finally:
            self.lib.mpv_free(value)

    def _set(self, name, value):
        self._check(self.lib.mpv_set_property_string(self.handle, name.encode(), str(value).encode()))

    def _command(self, *args):
        encoded = [str(arg).encode('utf-8') for arg in args] + [None]
        self._check(self.lib.mpv_command(self.handle, (c.c_char_p * len(encoded))(*encoded)))

    def _drain_events(self):
        while True:
            event = self.lib.mpv_wait_event(self.handle, 0).contents
            if event.id == 0:
                break
            if event.id == 2 and event.data:
                message = c.cast(event.data, c.POINTER(LogMessage)).contents
                text = (message.text or b'').decode('utf-8', 'replace').strip()
                if text:
                    self.debug_log.append(text)
                    self.debug_log = self.debug_log[-20:]
                continue
            if event.id == 6:  # MPV_EVENT_START_FILE
                self.error = None
            elif event.id == 7 and event.data:  # MPV_EVENT_END_FILE
                end = c.cast(event.data, c.POINTER(EndFile)).contents
                if end.reason == 4:
                    self.error = self.lib.mpv_error_string(end.error).decode('utf-8', 'replace')

    def play(self, path):
        self.error = None
        self._set('lavfi-complex', '')
        self._set('pause', 'no')
        self._set('sid', 'auto')
        self._set('aid', 'auto')
        self._command('loadfile', path, 'replace')

    def play_current(self):
        if self._get('eof-reached') == 'yes':
            self._command('seek', 0, 'absolute+exact')
        self._set('pause', 'no')

    def pause(self):
        self.ensure_paused()

    def ensure_paused(self):
        self._set('pause', 'yes')

    def stop(self):
        self._command('stop')

    def get_state(self):
        # Existing UI states: idle=0, playing=3, paused=4, ended=6, error=7.
        self._drain_events()
        if self.error:
            return 7
        if self._get('idle-active') == 'yes':
            return 0
        if self._get('eof-reached') == 'yes':
            return 6
        return 4 if self._get('pause') == 'yes' else 3

    def is_playing(self):
        return self.get_state() == 3

    def get_time(self):
        return round(float(self._get('time-pos', '0')) * 1000)

    def get_length(self):
        return round(float(self._get('duration', '0')) * 1000)

    def set_position(self, fraction):
        self._command('seek', max(0, min(100, fraction * 100)), 'absolute-percent+exact')

    def set_volume(self, value):
        self._set('volume', max(0, min(100, value)))

    def is_muted(self):
        return self._get('mute') == 'yes'

    def set_mute(self, muted):
        self._set('mute', 'yes' if muted else 'no')

    def _tracks(self, kind):
        result = []
        for i in range(int(self._get('track-list/count', '0'))):
            prefix = f'track-list/{i}/'
            if self._get(prefix + 'type') != kind:
                continue
            track_id = int(self._get(prefix + 'id'))
            language = self._get(prefix + 'lang')
            title = self._get(prefix + 'title')
            ff_index = self._get(prefix + 'ff-index')
            result.append({'id': track_id, 'language': language,
                           'name': ' · '.join(s for s in [title or f'Piste {track_id}', language] if s),
                           'external': self._get(prefix + 'external') == 'yes',
                           'ff_index': int(ff_index) if ff_index else None})
        return result

    def audio_tracks(self):
        return [(-1, 'Désactivé')] + [(t['id'], t['name']) for t in self._tracks('audio')]

    def subtitle_track_descriptions(self):
        return [(-1, 'Désactivé')] + [(t['id'], t['name']) for t in self._tracks('sub')]

    def embedded_subtitles(self):
        return [t for t in self._tracks('sub') if not t['external']]

    def _selected(self, name):
        value = self._get(name)
        return int(value) if value.isdigit() else -1

    def current_audio_track(self):
        return self._selected('aid')

    def current_subtitle_track(self):
        return self._selected('sid')

    def _select(self, name, track_id):
        try:
            self._set(name, 'no' if track_id < 0 else track_id)
            return True
        except RuntimeError:
            return False

    def select_audio_track(self, track_id):
        return self._select('aid', track_id)

    def selected_audio_ff_index(self):
        selected = self.current_audio_track()
        for track in self._tracks('audio'):
            if track['id'] == selected and not track['external'] and track['ff_index'] is not None:
                return track['ff_index']
        tracks = [t for t in self._tracks('audio') if not t['external'] and t['ff_index'] is not None]
        return tracks[0]['ff_index'] if tracks else None

    def add_audio_pair(self, original_wav, tts_wav, bg_mix=1.0, tts_mix=1.0):
        """Remplace l'audio intégré par deux WAV préparés séparément."""
        self._command('audio-add', str(original_wav), 'select')
        self._command('audio-add', str(tts_wav), 'select')
        tracks = [t for t in self._tracks('audio') if t['external']]
        if len(tracks) < 2:
            raise RuntimeError('Les deux WAV préparés n’ont pas été ajoutés à mpv.')
        original_id, tts_id = tracks[-2]['id'], tracks[-1]['id']
        self._set('lavfi-complex',
                  f"[aid{original_id}] [aid{tts_id}] amix=inputs=2:duration=longest:normalize=0:weights='{float(bg_mix):.6f} {float(tts_mix):.6f}' [ao]")
        return True

    def select_subtitle_track(self, track_id):
        return self._select('sid', track_id)

    def close(self):
        if self.handle:
            self.lib.mpv_terminate_destroy(self.handle)
            self.handle = None
        self.dll_directory.close()
