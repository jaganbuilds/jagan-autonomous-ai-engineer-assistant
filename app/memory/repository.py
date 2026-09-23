from typing import Optional, List
from app.database.connection import get_db_connection, DEFAULT_DB_PATH, init_db
from app.memory.models import Memory, MemoryScope

class MemoryRepository:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path

    def create_memory(self, memory: Memory) -> Memory:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO memories (session_id, owner_id, memory_type, content, source, scope, importance, confidence, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                memory.session_id,
                memory.owner_id,
                memory.memory_type.value,
                memory.content,
                memory.source.value,
                memory.scope.value,
                memory.importance.value,
                memory.confidence,
                memory.created_at,
                memory.updated_at
            ))
            conn.commit()
            memory.id = cursor.lastrowid
            return memory

    def get_memory(self, memory_id: int, session_id: str) -> Optional[Memory]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM memories WHERE id = ? AND session_id = ?', (memory_id, session_id))
            row = cursor.fetchone()
            if row:
                return Memory(**dict(row))
            return None

    def list_memories(self, session_id: str, memory_type: Optional[str] = None) -> List[Memory]:
        query = 'SELECT * FROM memories WHERE session_id = ? AND scope = ?'
        params = [session_id, MemoryScope.SESSION.value]
        
        if memory_type:
            query += ' AND memory_type = ?'
            params.append(memory_type)
            
        query += ' ORDER BY created_at ASC'
            
        results = []
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            for row in cursor.fetchall():
                results.append(Memory(**dict(row)))
        return results

    def list_personal_memories(self, owner_id: str, memory_type: Optional[str] = None) -> List[Memory]:
        query = 'SELECT * FROM memories WHERE owner_id = ? AND scope = ?'
        params = [owner_id, MemoryScope.PERSONAL.value]
        
        if memory_type:
            query += ' AND memory_type = ?'
            params.append(memory_type)
            
        query += ' ORDER BY created_at ASC'
            
        results = []
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            for row in cursor.fetchall():
                results.append(Memory(**dict(row)))
        return results

    def get_memory_safe(self, memory_id: int, session_id: str, owner_id: str) -> Optional[Memory]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM memories 
                WHERE id = ? AND (
                    (scope = 'session' AND session_id = ?) OR 
                    (scope = 'personal' AND owner_id = ?)
                )
            ''', (memory_id, session_id, owner_id))
            row = cursor.fetchone()
            if row:
                return Memory(**dict(row))
            return None

    def update_memory(self, memory_id: int, session_id: str, content: str, updated_at: str, importance: Optional[MemoryImportance] = None) -> Optional[Memory]:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            if importance:
                cursor.execute('''
                    UPDATE memories
                    SET content = ?, updated_at = ?, importance = ?
                    WHERE id = ? AND session_id = ?
                ''', (content, updated_at, importance.value, memory_id, session_id))
            else:
                cursor.execute('''
                    UPDATE memories
                    SET content = ?, updated_at = ?
                    WHERE id = ? AND session_id = ?
                ''', (content, updated_at, memory_id, session_id))
            conn.commit()
            if cursor.rowcount > 0:
                return self.get_memory(memory_id, session_id)
            return None

    def delete_memory_safe(self, memory_id: int, session_id: str, owner_id: str) -> bool:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM memories 
                WHERE id = ? AND (
                    (scope = 'session' AND session_id = ?) OR 
                    (scope = 'personal' AND owner_id = ?)
                )
            ''', (memory_id, session_id, owner_id))
            conn.commit()
            return cursor.rowcount > 0

    def delete_memories_atomically(self, memory_ids: List[int], session_id: str, owner_id: str) -> bool:
        """Deletes multiple memories as a single atomic database transaction."""
        if not memory_ids:
            return True
            
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                for mid in memory_ids:
                    cursor.execute('''
                        DELETE FROM memories 
                        WHERE id = ? AND (
                            (scope = 'session' AND session_id = ?) OR 
                            (scope = 'personal' AND owner_id = ?)
                        )
                    ''', (mid, session_id, owner_id))
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False

    def apply_consolidation_group(self, canonical_id: int, redundant_ids: List[int], session_id: str, owner_id: str, content: str, updated_at: str, importance: MemoryImportance) -> bool:
        """Applies a memory consolidation group as a single atomic database transaction."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            try:
                # Update canonical
                cursor.execute('''
                    UPDATE memories
                    SET content = ?, updated_at = ?, importance = ?
                    WHERE id = ? AND (
                        (scope = 'session' AND session_id = ?) OR 
                        (scope = 'personal' AND owner_id = ?)
                    )
                ''', (content, updated_at, importance.value, canonical_id, session_id, owner_id))
                
                # Delete redundant
                for rid in redundant_ids:
                    cursor.execute('''
                        DELETE FROM memories 
                        WHERE id = ? AND (
                            (scope = 'session' AND session_id = ?) OR 
                            (scope = 'personal' AND owner_id = ?)
                        )
                    ''', (rid, session_id, owner_id))
                
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False

    def clear_session_memories(self, session_id: str) -> int:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM memories WHERE session_id = ? AND scope = ?', (session_id, MemoryScope.SESSION.value))
            conn.commit()
            return cursor.rowcount

    def clear_personal_memories(self, owner_id: str) -> int:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM memories WHERE owner_id = ? AND scope = ?', (owner_id, MemoryScope.PERSONAL.value))
            conn.commit()
            return cursor.rowcount
            
    def clear_all_memories(self, owner_id: str) -> int:
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM memories 
                WHERE owner_id = ? OR (scope = 'session' AND owner_id = ?)
            ''', (owner_id, owner_id)) # We can just delete anything where owner_id matches, because owner_id is tied to everything they create
            conn.commit()
            return cursor.rowcount
            
    def get_all_in_scope(self, session_id: str, owner_id: str, scope: MemoryScope) -> List[Memory]:
        """Fetches all memories in the given scope for duplicate/conflict detection."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.cursor()
            if scope == MemoryScope.PERSONAL:
                cursor.execute('SELECT * FROM memories WHERE owner_id = ? AND scope = ?', (owner_id, scope.value))
            else:
                cursor.execute('SELECT * FROM memories WHERE session_id = ? AND scope = ?', (session_id, scope.value))
            return [Memory(**dict(row)) for row in cursor.fetchall()]

_memory_repository_instance = None

def get_memory_repository(db_path: str = DEFAULT_DB_PATH) -> MemoryRepository:
    global _memory_repository_instance
    if _memory_repository_instance is None:
        init_db(db_path)
        _memory_repository_instance = MemoryRepository(db_path)
    return _memory_repository_instance

def set_memory_repository_for_testing(repo: Optional[MemoryRepository]):
    global _memory_repository_instance
    _memory_repository_instance = repo
