# add_dub/core/workset.py
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(slots=True)
class DubWorkset:
    # Fichiers principaux
    video_input: Path
    video_output: Path

    # Arbo tmp dédiée à cette vidéo
    tmp_dir: Path
    canonical_srt: Path
    orig_wav: Path
    bg_wav: Path
    tts_wav: Path

    def __post_init__(self) -> None:
        # Normalise en Path si on t’a passé des str
        for name, value in self.__dict__.items():
            if not isinstance(value, Path):
                try:
                    p = Path(value)
                except Exception as e:
                    raise TypeError(f"{name} doit être un Path (ou convertible): {e}")
                setattr(self, name, p)

        # Garde-fous de base
        if not self.video_input.exists():
            raise FileNotFoundError(f"Fichier vidéo introuvable: {self.video_input}")

        # On crée l’arbo tmp si besoin (mais jamais le dossier source)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        for p in (self.canonical_srt.parent, self.orig_wav.parent,
                  self.bg_wav.parent, self.tts_wav.parent, self.mix_wav.parent):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def stem(self) -> str:
        return self.video_input.stem

    @property
    def suffix(self) -> str:
        return self.video_input.suffix

    @classmethod
    def build(cls, video_input: str | Path, root_tmp: str | Path, root_out: str | Path, out_suffix: str = ".mkv") -> "DubWorkset":
        """
        Fabrique un workset canonique pour une vidéo donnée, avec une arbo standard:
            tmp/<stem>/{in,work,out}/...
        """
        vin = Path(video_input)
        stem = vin.stem

        tmp_dir = Path(root_tmp) / stem
        in_dir  = tmp_dir / "in"
        work    = tmp_dir / "work"
        outdir  = tmp_dir / "out"

        canonical_srt = work / "canonical.srt"
        orig_wav      = work / "orig.wav"
        bg_wav        = work / "bg.wav"
        tts_wav       = work / "tts.wav"
        mix_wav       = outdir / "mix.wav"

        video_output  = Path(root_out) / f"{stem}{out_suffix}"

        return cls(
            video_input=vin,
            video_output=video_output,
            tmp_dir=tmp_dir,
            canonical_srt=canonical_srt,
            orig_wav=orig_wav,
            bg_wav=bg_wav,
            tts_wav=tts_wav,
            mix_wav=mix_wav,
        )
