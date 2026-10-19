"""
ProjectItemsMixin (RFC 09).
Gerencia operações CRUD e consultas otimizadas da tabela 'items' no SQLite.
"""

import sqlite3
from typing import List, Optional
from src.core.project import ProjectItem


class ProjectItemsMixin:
    """Mixin com operações relativas aos itens individuais de mídia ingeridos."""

    def get_items(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        verified: Optional[bool] = None,
    ) -> List[ProjectItem]:
        """Recupera itens do banco de dados do projeto, com suporte a filtros diretos no SQLite."""
        if not self._project_db_file.exists() and self._get_active_conn() is None:
            return []

        import src.core.project as p_mod
        sql, params = p_mod._build_items_filter_query(
            "SELECT * FROM items",
            status=status,
            category=category,
            verified=verified,
        )

        items = []
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.row_factory = sqlite3.Row
            cursor = active_conn.cursor()
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                items.append(p_mod._row_to_item(row))
            return items

        with p_mod.get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                items.append(p_mod._row_to_item(row))
        return items

    def get_items_count(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        verified: Optional[bool] = None,
    ) -> int:
        """Retorna a contagem de itens instantaneamente via SELECT COUNT(*) no SQLite."""
        active_conn = self._get_active_conn()
        if active_conn is None and not self._project_db_file.exists():
            return 0

        import src.core.project as p_mod
        sql, params = p_mod._build_items_filter_query(
            "SELECT COUNT(*) FROM items",
            status=status,
            category=category,
            verified=verified,
        )

        if active_conn is not None:
            cursor = active_conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else 0

        with p_mod.get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            return row[0] if row else 0

    def has_items(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        verified: Optional[bool] = None,
    ) -> bool:
        """Verifica se existem itens correspondentes aos critérios com custo O(1) via SELECT 1 ... LIMIT 1."""
        active_conn = self._get_active_conn()
        if active_conn is None and not self._project_db_file.exists():
            return False

        import src.core.project as p_mod
        sql, params = p_mod._build_items_filter_query(
            "SELECT 1 FROM items",
            status=status,
            category=category,
            verified=verified,
            limit=1,
        )

        if active_conn is not None:
            cursor = active_conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone() is not None

        with p_mod.get_db_connection(self._project_db_file) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return cursor.fetchone() is not None

    def get_items_by_category(self, category: str) -> List[ProjectItem]:
        """Busca itens da categoria desejada com filtro direto no banco."""
        return self.get_items(category=category)

    def save_item(self, item: ProjectItem):
        """Salva ou atualiza um item no banco do projeto atomicamente ou na transação ativa."""
        self._ensure_db_initialized()
        import src.core.project as p_mod
        params = p_mod._serialize_item(item)
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.execute(p_mod.ITEMS_UPSERT_SQL, params)
        else:
            with p_mod.get_db_connection(self._project_db_file) as conn:
                conn.execute(p_mod.ITEMS_UPSERT_SQL, params)
                conn.commit()

    def save_items_batch(self, items: List[ProjectItem]):
        """Salva uma coleção de itens via executemany em lote de alta performance."""
        if not items:
            return
        self._ensure_db_initialized()
        import src.core.project as p_mod
        params_list = [p_mod._serialize_item(it) for it in items]
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.executemany(p_mod.ITEMS_UPSERT_SQL, params_list)
        else:
            with self.transaction():
                conn = self._get_active_conn()
                if conn:
                    conn.executemany(p_mod.ITEMS_UPSERT_SQL, params_list)

    def get_item(self, original_path: str) -> Optional[ProjectItem]:
        """Busca um item especifico no banco pelo original_path."""
        if not self._project_db_file.exists():
            return None
        import src.core.project as p_mod
        active_conn = self._get_active_conn()
        if active_conn is not None:
            active_conn.row_factory = sqlite3.Row
            cursor = active_conn.cursor()
            cursor.execute("SELECT * FROM items WHERE original_path=?", (original_path,))
            row = cursor.fetchone()
            return p_mod._row_to_item(row) if row else None

        with p_mod.get_db_connection(self._project_db_file) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM items WHERE original_path=?", (original_path,))
            row = cursor.fetchone()
            if row:
                return p_mod._row_to_item(row)
        return None

    @property
    def items(self) -> List[ProjectItem]:
        return self.get_items()

    @items.setter
    def items(self, value: List[ProjectItem]):
        self.save_items_batch(value)
