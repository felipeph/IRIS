import os
from pathlib import Path
from typing import Set

# Arquivos temporários e de cache do sistema operacional que não constituem dados de usuário
OS_JUNK_FILES: Set[str] = {
    ".ds_store",
    "thumbs.db",
    "desktop.ini",
}


def is_dir_empty(dir_path: Path, ignore_junk_files: bool = True) -> bool:
    """
    Verifica se um diretório está vazio.
    Se ignore_junk_files=True, caso o diretório contenha exclusivamente arquivos
    residuais de sistema (ex: Thumbs.db, .DS_Store, desktop.ini), esses arquivos
    são removidos com segurança para permitir que a pasta seja considerada vazia.
    """
    if not dir_path.exists() or not dir_path.is_dir():
        return False

    try:
        entries = list(dir_path.iterdir())
        if not entries:
            return True

        if ignore_junk_files:
            junk_entries = []
            for entry in entries:
                if entry.is_file() and entry.name.lower() in OS_JUNK_FILES:
                    junk_entries.append(entry)
                else:
                    return False

            # Se todos os itens encontrados eram junk files, remove-os
            for junk in junk_entries:
                try:
                    junk.unlink()
                except OSError:
                    return False

            return not any(dir_path.iterdir())

        return False
    except (OSError, PermissionError):
        return False


def clean_empty_parent_dirs(target_path: Path, stop_at_dir: Path, ignore_junk_files: bool = True) -> int:
    """
    Remove diretórios pais vazios de baixo para cima, parando imediatamente
    ao encontrar qualquer pasta com conteúdo ou ao atingir stop_at_dir (que nunca é removido).

    Args:
        target_path: Arquivo ou pasta de início.
        stop_at_dir: Diretório raiz limite (preservado).
        ignore_junk_files: Se True, descarta arquivos como Thumbs.db para desalocar a pasta.

    Retorna:
        Quantidade de pastas vazias removidas.
    """
    removed_count = 0
    try:
        stop_resolved = stop_at_dir.resolve()
    except Exception:
        stop_resolved = stop_at_dir

    try:
        current = target_path if target_path.is_dir() else target_path.parent
    except Exception:
        return 0

    while current:
        try:
            curr_resolved = current.resolve()
            if curr_resolved == stop_resolved:
                break

            if not current.exists() or not current.is_dir():
                parent = current.parent
                if parent.resolve() == stop_resolved or stop_resolved in parent.resolve().parents:
                    current = parent
                    continue
                break

            if is_dir_empty(current, ignore_junk_files=ignore_junk_files):
                current.rmdir()
                removed_count += 1
                parent = current.parent
                if parent.resolve() == stop_resolved or stop_resolved in parent.resolve().parents:
                    current = parent
                else:
                    break
            else:
                break
        except (OSError, PermissionError):
            break

    return removed_count


def prune_empty_dirs_upward(target_dir: Path, stop_at: Path, ignore_junk_files: bool = True) -> int:
    """Alias semântico para clean_empty_parent_dirs."""
    return clean_empty_parent_dirs(target_dir, stop_at, ignore_junk_files=ignore_junk_files)


def clean_empty_directories(root_dir: Path, preserve_root: bool = True, ignore_junk_files: bool = True) -> int:
    """
    Remove pastas vazias recursivamente de baixo para cima dentro de root_dir.

    Args:
        root_dir: Diretório onde a varredura será realizada.
        preserve_root: Se True, o diretório root_dir em si nunca será removido.
        ignore_junk_files: Se True, descarta Thumbs.db, .DS_Store, etc. antes de remover pastas.

    Retorna:
        Quantidade de pastas vazias removidas.
    """
    if not root_dir.exists() or not root_dir.is_dir():
        return 0

    removed_count = 0
    try:
        root_resolved = root_dir.resolve()
    except Exception:
        root_resolved = root_dir

    for dirpath, _, _ in os.walk(str(root_dir), topdown=False):
        p = Path(dirpath)
        try:
            p_resolved = p.resolve()
            if preserve_root and p_resolved == root_resolved:
                continue

            if is_dir_empty(p, ignore_junk_files=ignore_junk_files):
                p.rmdir()
                removed_count += 1
        except (OSError, PermissionError):
            pass

    return removed_count
