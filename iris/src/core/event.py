"""
Modo Evento/Álbum do IRIS.

Projetos marcados como evento carregam o nome do evento e a lista de participantes,
gravados como tags (Keywords, Subject, HierarchicalSubject, Title, Description) apenas em
formatos graváveis (JPEG, PNG, HEIC, TIFF, WEBP). RAWs e vídeos NUNCA são regravados.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from src.core.geo import GEO_WRITABLE_EXTS

# Etapas que não fazem sentido em projetos de álbum (tratados sempre como fotos avulsas).
ALBUM_SKIPPED_STAGE_IDS = frozenset({
    "bird_detect", "bird_id", "bird_organize", "bird_tag",
    "astro_stack", "astro_sharpen",
    "timelapse_denoise", "timelapse",
    "video_edit", "youtube",
})


def normalize_names(names: Iterable[str]) -> List[str]:
    """Remove espaços, vazios e duplicatas (ignorando caixa), preservando acentos e ordem."""
    result: List[str] = []
    seen = set()
    for raw in names:
        name = " ".join(str(raw or "").split())
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def parse_names(text: str) -> List[str]:
    """Converte 'Ana, João; Maria' em lista normalizada."""
    return normalize_names(text.replace(";", ",").split(","))


@dataclass
class EventInfo:
    name: str = ""
    participants: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.name = " ".join(str(self.name or "").split())
        self.participants = normalize_names(self.participants)

    @property
    def keywords(self) -> List[str]:
        return normalize_names([self.name] + self.participants) if self.name else []

    @property
    def hierarchical(self) -> List[str]:
        if not self.name:
            return []
        return [f"Evento|{self.name}"] + [f"Pessoa|{p}" for p in self.participants]

    @property
    def description(self) -> str:
        if not self.name:
            return ""
        text = f"Evento: {self.name}"
        if self.participants:
            text += f". Participantes: {', '.join(self.participants)}"
        return text


def build_exiftool_event_args(event: EventInfo, previous: Optional[EventInfo] = None, ext: str = "") -> List[str]:
    """
    Gera argumentos ExifTool de tags de evento. Se `previous` for informado, remove antes
    os valores antigos para evitar duplicidade ao reaplicar. Retorna [] para formatos
    não graváveis (RAW/vídeo) ou evento sem nome.
    """
    if not event.name or (ext and ext.lower() not in GEO_WRITABLE_EXTS):
        return []

    args: List[str] = [
        "-charset", "UTF8",
        "-charset", "iptc=UTF8",
        "-codedcharacterset=utf8",
        "-IPTC:CodedCharacterSet=UTF8",
    ]
    if previous is not None and previous.name:
        for tag in previous.keywords:
            args += [f"-Keywords-={tag}", f"-Subject-={tag}"]
        for h in previous.hierarchical:
            args.append(f"-XMP-lr:HierarchicalSubject-={h}")
    for tag in event.keywords:
        args += [f"-Keywords+={tag}", f"-Subject+={tag}"]
    for h in event.hierarchical:
        args.append(f"-XMP-lr:HierarchicalSubject+={h}")
    args += [
        f"-XMP-dc:Title={event.name}",
        f"-IPTC:ObjectName={event.name}",
        f"-XMP-dc:Description={event.description}",
        f"-IPTC:Caption-Abstract={event.description}",
    ]
    return args


def project_event(project) -> EventInfo:
    return EventInfo(getattr(project, "event_name", ""), list(getattr(project, "event_participants", []) or []))


class PeopleCatalog:
    """Cadastro global de pessoas frequentes (tabela `people_catalog` no banco central)."""

    @staticmethod
    def _conn():
        import src.core.project as p_mod
        p_mod.init_central_db()
        return p_mod.get_db_connection(p_mod.CENTRAL_DB_PATH)

    @classmethod
    def list(cls, limit: int = 50) -> List[str]:
        with cls._conn() as conn:
            rows = conn.execute(
                "SELECT name FROM people_catalog ORDER BY use_count DESC, name COLLATE NOCASE LIMIT ?", (limit,)
            ).fetchall()
        return [r[0] for r in rows]

    @classmethod
    def register(cls, names: Iterable[str]) -> None:
        with cls._conn() as conn:
            for name in normalize_names(names):
                conn.execute(
                    """INSERT INTO people_catalog (name) VALUES (?)
                       ON CONFLICT(name) DO UPDATE SET use_count = use_count + 1,
                       updated_at = CURRENT_TIMESTAMP""",
                    (name,),
                )
            conn.commit()

    @classmethod
    def rename(cls, old: str, new: str) -> bool:
        new = " ".join(new.split())
        if not new:
            return False
        with cls._conn() as conn:
            cur = conn.execute("UPDATE people_catalog SET name=? WHERE name=?", (new, old))
            conn.commit()
            return cur.rowcount > 0

    @classmethod
    def delete(cls, name: str) -> bool:
        with cls._conn() as conn:
            cur = conn.execute("DELETE FROM people_catalog WHERE name=?", (name,))
            conn.commit()
            return cur.rowcount > 0


def apply_event_tags(project, previous: Optional[EventInfo] = None, console=None) -> int:
    """
    Regrava as tags de evento em todas as fotos graváveis do álbum (2_AlbunsDatas).
    Retorna a quantidade de arquivos processados. RAW e vídeo são ignorados.
    """
    event = project_event(project)
    if not event.name:
        return 0

    env_exif = os.getenv("IRIS_EXIFTOOL_PATH")
    exiftool_bin = env_exif if env_exif and Path(env_exif).exists() else shutil.which("exiftool")
    if not exiftool_bin:
        if console:
            console.print("[yellow]ExifTool não encontrado: tags de evento não aplicadas.[/yellow]")
        return 0

    paths: List[Path] = []
    seen = set()
    for it in project.get_items(status="organized"):
        p_str = it.organized_path or it.staging_path
        if not p_str:
            continue
        p = Path(p_str)
        key = str(p.resolve()) if p.exists() else str(p)
        if key in seen or not p.exists() or p.suffix.lower() not in GEO_WRITABLE_EXTS:
            continue
        seen.add(key)
        paths.append(p)

    if not paths:
        return 0

    args = build_exiftool_event_args(event, previous=previous)
    batch = 500
    done = 0
    for i in range(0, len(paths), batch):
        chunk = paths[i:i + batch]
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            for a in args:
                f.write(f"{a}\n")
            f.write("-overwrite_original\n-P\n-charset\nfilename=UTF8\n")
            for p in chunk:
                f.write(f"{p.resolve()}\n")
            argfile = f.name
        try:
            subprocess.run([exiftool_bin, "-charset", "UTF8", "-@", argfile],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
            done += len(chunk)
        finally:
            try:
                os.unlink(argfile)
            except OSError:
                pass
    return done
