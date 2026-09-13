"""Petit adaptateur de LibVLC 3 Windows, chargé uniquement depuis la distribution."""
import ctypes as c
import os
from pathlib import Path
import sys


class TrackDescription(c.Structure):
    pass


TrackDescription._fields_ = [('id', c.c_int), ('name', c.c_char_p),
                            ('next', c.POINTER(TrackDescription))]


class Player:
    def __init__(self, hwnd):
        if sys.platform != 'win32':
            raise RuntimeError('Le lecteur intégré est disponible sous Windows.')
        root = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[2]
        directory = root / 'tools' / 'vlc'
        if not (directory / 'libvlc.dll').is_file():
            raise RuntimeError('Moteur vidéo embarqué absent : relancez start_add_dub.bat ou recompiléz la distribution.')
        self.dll_directory = os.add_dll_directory(str(directory))
        self.core = c.CDLL(str(directory / 'libvlccore.dll'))
        self.lib = c.CDLL(str(directory / 'libvlc.dll'))
        signatures = {
            'libvlc_video_get_spu_description': (c.POINTER(TrackDescription), [c.c_void_p]),
            'libvlc_track_description_list_release': (None, [c.POINTER(TrackDescription)]),
            'libvlc_video_get_spu': (c.c_int, [c.c_void_p]),
            'libvlc_video_set_spu': (c.c_int, [c.c_void_p, c.c_int]),
            'libvlc_new': (c.c_void_p, [c.c_int, c.POINTER(c.c_char_p)]),
            'libvlc_release': (None, [c.c_void_p]),
            'libvlc_media_player_new': (c.c_void_p, [c.c_void_p]),
            'libvlc_media_player_release': (None, [c.c_void_p]),
            'libvlc_media_new_path': (c.c_void_p, [c.c_void_p, c.c_char_p]),
            'libvlc_media_release': (None, [c.c_void_p]),
            'libvlc_media_player_set_media': (None, [c.c_void_p, c.c_void_p]),
            'libvlc_media_player_set_hwnd': (None, [c.c_void_p, c.c_void_p]),
            'libvlc_media_player_play': (c.c_int, [c.c_void_p]),
            'libvlc_media_player_pause': (None, [c.c_void_p]),
            'libvlc_media_player_stop': (None, [c.c_void_p]),
            'libvlc_media_player_get_position': (c.c_float, [c.c_void_p]),
            'libvlc_media_player_set_position': (None, [c.c_void_p, c.c_float]),
            'libvlc_media_player_get_time': (c.c_int64, [c.c_void_p]),
            'libvlc_media_player_get_length': (c.c_int64, [c.c_void_p]),
            'libvlc_audio_set_volume': (c.c_int, [c.c_void_p, c.c_int]),
            'libvlc_audio_toggle_mute': (None, [c.c_void_p]),
            'libvlc_audio_get_mute': (c.c_int, [c.c_void_p]),
            'libvlc_media_player_is_playing': (c.c_int, [c.c_void_p]),
        }
        for name, (result, args) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, args
        os.environ['VLC_PLUGIN_PATH'] = str(directory / 'plugins')
        args = [b'--no-video-title-show', b'--no-snapshot-preview', b'--no-osd']
        self.instance = self.lib.libvlc_new(len(args), (c.c_char_p * len(args))(*args))
        if not self.instance:
            raise RuntimeError('Initialisation du lecteur impossible.')
        self.player = self.lib.libvlc_media_player_new(self.instance)
        self.lib.libvlc_media_player_set_hwnd(self.player, int(hwnd))

    def play(self, path):
        self.lib.libvlc_media_player_stop(self.player)
        media = self.lib.libvlc_media_new_path(self.instance, os.fsencode(path).decode('utf-8').encode('utf-8'))
        self.lib.libvlc_media_player_set_media(self.player, media)
        self.lib.libvlc_media_release(media)
        if self.lib.libvlc_media_player_play(self.player) == -1:
            raise RuntimeError('Lecture de l’extrait impossible.')

    def play_current(self):
        if self.lib.libvlc_media_player_play(self.player) == -1:
            raise RuntimeError('Lecture de l’extrait impossible.')

    def pause(self):
        self.lib.libvlc_media_player_pause(self.player)

    def stop(self):
        self.lib.libvlc_media_player_stop(self.player)

    def is_playing(self):
        return bool(self.lib.libvlc_media_player_is_playing(self.player))

    def get_time(self):
        return int(self.lib.libvlc_media_player_get_time(self.player))

    def get_length(self):
        return int(self.lib.libvlc_media_player_get_length(self.player))

    def set_volume(self, value):
        self.lib.libvlc_audio_set_volume(self.player, int(value))

    def set_mute(self, muted):
        # LibVLC 3 exposes a toggle API, so only toggle when the current state differs.
        current = bool(self.lib.libvlc_audio_get_mute(self.player)) if hasattr(self.lib, 'libvlc_audio_get_mute') else False
        if current != bool(muted):
            self.lib.libvlc_audio_toggle_mute(self.player)

    def close(self):
        self.lib.libvlc_media_player_stop(self.player)
        self.lib.libvlc_media_player_release(self.player)
        self.lib.libvlc_release(self.instance)
        self.dll_directory.close()

    def subtitle_tracks(self):
        head = self.lib.libvlc_video_get_spu_description(self.player)
        tracks = []
        try:
            item = head
            while item:
                if item.contents.id >= 0:
                    tracks.append(item.contents.id)
                item = item.contents.next
        finally:
            if head:
                self.lib.libvlc_track_description_list_release(head)
        return tracks

    def subtitles_enabled(self):
        return self.lib.libvlc_video_get_spu(self.player) >= 0

    def set_subtitles(self, enabled):
        tracks = self.subtitle_tracks() if enabled else []
        if enabled and not tracks:
            return False
        return self.lib.libvlc_video_set_spu(self.player, tracks[0] if enabled else -1) == 0
