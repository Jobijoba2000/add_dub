"""Petites commandes communes à l'interface, utilisant l'adaptateur existant."""


class Playback:
    def __init__(self, player):
        self.player = player
        self.path = None

    def open(self, path):
        self.player.play(path)
        self.path = path

    def toggle_pause(self):
        if not self.path:
            return
        if self.player.is_playing():
            self.player.pause()
        else:
            self.player.play_current()

    def seek(self, fraction):
        if self.path:
            self.player.set_position(max(0., min(.9999, fraction)))

    def skip(self, seconds):
        total = self.player.get_length()
        if self.path and total > 0:
            self.seek((self.player.get_time() + seconds * 1000) / total)
