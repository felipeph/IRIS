"""
Script de Recuperação: Limpeza de Poluição de Aves em Projetos de Timelapse (IRIS).
Expurga registros acidentais em bird_identifications e recortes gerados indevidamente
para projetos categorizados como timelapse, resetando o estágio para 'sanitization'.
"""

import sys
import shutil
import sqlite3
from pathlib import Path

# Ajusta path para importar módulos do core se executado diretamente
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.core.config import config, PROJECTS_DIR
from src.core.project import get_project, list_open_projects, CENTRAL_DB_PATH
from src.core.lock import ProjectLock


def cleanup_project_bird_pollution(project_name: str, force: bool = False):
    print(f"\n[IRIS RECOVERY] Iniciando análise para o projeto: '{project_name}'")

    lock = ProjectLock(project_name)
    if lock.is_locked():
        lock_info = lock.get_lock_info()
        print(f"\n⚠️  ATENÇÃO: O projeto está BLOQUEADO pelo processo PID {lock_info.get('pid')}.")
        print("Interrompa a execução no outro terminal (pressionando Ctrl+C) antes de prosseguir com a limpeza.")
        if not force:
            return False

    project = get_project(project_name)
    if not project:
        print(f"❌ Erro: Projeto '{project_name}' não encontrado.")
        return False

    db_path = project.db_path
    if not db_path.exists():
        print(f"❌ Erro: Banco de dados do projeto não encontrado em {db_path}.")
        return False

    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("SELECT count(*) FROM bird_identifications")
        bird_count = c.fetchone()[0]

        c.execute("SELECT count(*) FROM items WHERE category IN ('timelapse', 'timelapse_long_exposure')")
        tl_count = c.fetchone()[0]

        print(f"• Total de itens de timelapse no projeto: {tl_count}")
        print(f"• Total de registros em bird_identifications: {bird_count}")

        if bird_count > 0:
            c.execute("DELETE FROM bird_identifications")
            conn.commit()
            print(f"✔ {bird_count} registro(s) de aves removidos com sucesso do banco do projeto.")
        else:
            print("✔ Nenhum registro residual de aves encontrado no banco do projeto.")

    # Remove também registros no banco central se houver
    if CENTRAL_DB_PATH.exists():
        with sqlite3.connect(CENTRAL_DB_PATH) as c_conn:
            c_cursor = c_conn.cursor()
            try:
                c_cursor.execute("DELETE FROM bird_identifications WHERE project_name = ?", (project_name,))
                c_conn.commit()
            except Exception:
                pass

            # Atualiza current_stage_id no banco central para sanitization
            c_cursor.execute("UPDATE projects SET current_stage_id = 'sanitization' WHERE name = ?", (project_name,))
            c_conn.commit()

    # Atualiza current_stage_id no objeto do projeto
    project.current_stage_id = "sanitization"
    project.save()
    print("✔ Status do projeto atualizado para 'sanitization' (pronto para pular aves e rodar timelapse).")

    # Limpeza da pasta física de recortes em 10_Aves/Recortes/{project_name}
    dest_root = Path(config.get("general.destination_root", "C:\\IRIS"))
    crops_dir = dest_root / "10_Aves" / "Recortes" / project_name
    if crops_dir.exists():
        files_deleted = 0
        for f in crops_dir.glob("*"):
            if f.is_file():
                f.unlink()
                files_deleted += 1
        try:
            crops_dir.rmdir()
            print(f"✔ Pasta de recortes removida: {crops_dir} ({files_deleted} arquivo(s) expurgados).")
        except Exception:
            shutil.rmtree(crops_dir, ignore_errors=True)
            print(f"✔ Pasta de recortes removida completamente: {crops_dir}.")
    else:
        print("✔ Nenhuma pasta de recortes residual encontrada no disco.")

    print(f"\n[OK] Recuperação concluída para '{project_name}'! Agora você pode rodar o pipeline com segurança.")
    return True


if __name__ == "__main__":
    target_project = sys.argv[1] if len(sys.argv) > 1 else None
    if not target_project:
        # Busca o projeto mais recente ou com nome Ninho
        projects = list_open_projects()
        ninho_projects = [p for p in projects if "Ninho" in p or "timelapse" in p.lower()]
        target_project = ninho_projects[0] if ninho_projects else (projects[0] if projects else None)

    if not target_project:
        print("Nenhum projeto encontrado para limpeza.")
        sys.exit(1)

    cleanup_project_bird_pollution(target_project)
