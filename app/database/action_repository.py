import json
import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from app.database.connection import get_db_connection

class ActionRepository:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path
        
    def _get_conn(self):
        if self.db_path:
            return get_db_connection(self.db_path)
        return get_db_connection()
        
    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
        
    def _safe_json(self, data: Any) -> str:
        if not data:
            return "{}"
        # We assume secrets are stripped before being passed here
        return json.dumps(data)

    def create_action(self, action_id: str, session_id: str, owner_id: str, integration_name: str, action_type: str, risk_level: str, status: str, request_payload: Dict[str, Any]) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO actions 
                (action_id, session_id, owner_id, integration_name, action_type, risk_level, status, request_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                action_id, session_id, owner_id, integration_name, action_type, risk_level, status,
                self._safe_json(request_payload), self._now(), self._now()
            ))
            conn.commit()

    def get_action(self, action_id: str, session_id: str, owner_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM actions 
                WHERE action_id = ? AND session_id = ? AND owner_id = ?
            ''', (action_id, session_id, owner_id))
            row = cursor.fetchone()
            if not row:
                return None
                
            return {
                "action_id": row["action_id"],
                "session_id": row["session_id"],
                "owner_id": row["owner_id"],
                "integration_name": row["integration_name"],
                "action_type": row["action_type"],
                "risk_level": row["risk_level"],
                "status": row["status"],
                "request_payload": json.loads(row["request_payload"]) if row["request_payload"] else {},
                "result_payload": json.loads(row["result_payload"]) if row["result_payload"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "confirmed_at": row["confirmed_at"],
                "completed_at": row["completed_at"]
            }

    def get_pending_action_for_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM actions 
                WHERE session_id = ? AND status = 'PENDING_CONFIRMATION'
                ORDER BY created_at DESC LIMIT 1
            ''', (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
                
            return {
                "action_id": row["action_id"],
                "session_id": row["session_id"],
                "owner_id": row["owner_id"],
                "integration_name": row["integration_name"],
                "action_type": row["action_type"],
                "risk_level": row["risk_level"],
                "status": row["status"],
                "request_payload": json.loads(row["request_payload"]) if row["request_payload"] else {},
                "result_payload": json.loads(row["result_payload"]) if row["result_payload"] else None,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "confirmed_at": row["confirmed_at"],
                "completed_at": row["completed_at"]
            }

    def update_status(self, action_id: str, status: str) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE actions 
                SET status = ?, updated_at = ? 
                WHERE action_id = ?
            ''', (status, self._now(), action_id))
            conn.commit()
            
    def try_transition_to_executing(self, action_id: str, session_id: str, owner_id: str) -> bool:
        """Atomic update to ensure only one execution."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            now = self._now()
            cursor.execute('''
                UPDATE actions 
                SET status = 'EXECUTING', updated_at = ?, confirmed_at = ?
                WHERE action_id = ? AND session_id = ? AND owner_id = ? AND status = 'PENDING_CONFIRMATION'
            ''', (now, now, action_id, session_id, owner_id))
            conn.commit()
            return cursor.rowcount > 0

    def save_result(self, action_id: str, status: str, result_payload: Dict[str, Any]) -> None:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE actions 
                SET status = ?, result_payload = ?, updated_at = ?, completed_at = ?
                WHERE action_id = ?
            ''', (status, self._safe_json(result_payload), self._now(), self._now(), action_id))
            conn.commit()
            
    def get_executing_actions(self) -> list[dict]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM actions WHERE status = 'EXECUTING'
            ''')
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def list_actions(self, session_id: str, owner_id: str, integration_name: Optional[str] = None, 
                     action_type: Optional[str] = None, status: Optional[str] = None, 
                     limit: int = 50, offset: int = 0) -> list[Dict[str, Any]]:
        # Hard cap on limit
        limit = min(max(1, limit), 100)
        
        query = '''
            SELECT * FROM actions 
            WHERE session_id = ? AND owner_id = ?
        '''
        params = [session_id, owner_id]
        
        if integration_name:
            query += ' AND integration_name = ?'
            params.append(integration_name)
        if action_type:
            query += ' AND action_type = ?'
            params.append(action_type)
        if status:
            query += ' AND status = ?'
            params.append(status)
            
        query += ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                results.append({
                    "action_id": row["action_id"],
                    "session_id": row["session_id"],
                    "owner_id": row["owner_id"],
                    "integration_name": row["integration_name"],
                    "action_type": row["action_type"],
                    "risk_level": row["risk_level"],
                    "status": row["status"],
                    "request_payload": json.loads(row["request_payload"]) if row["request_payload"] else {},
                    "result_payload": json.loads(row["result_payload"]) if row["result_payload"] else None,
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "confirmed_at": row["confirmed_at"],
                    "completed_at": row["completed_at"]
                })
            return results

    def get_action_statistics(self, session_id: str, owner_id: str) -> Dict[str, Any]:
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT status, COUNT(*) as count 
                FROM actions 
                WHERE session_id = ? AND owner_id = ?
                GROUP BY status
            ''', (session_id, owner_id))
            status_counts = cursor.fetchall()
            
            cursor.execute('''
                SELECT integration_name, COUNT(*) as count 
                FROM actions 
                WHERE session_id = ? AND owner_id = ?
                GROUP BY integration_name
            ''', (session_id, owner_id))
            integration_counts = cursor.fetchall()

            cursor.execute('''
                SELECT action_type, COUNT(*) as count 
                FROM actions 
                WHERE session_id = ? AND owner_id = ?
                GROUP BY action_type
            ''', (session_id, owner_id))
            type_counts = cursor.fetchall()
            
        stats = {
            "total": 0,
            "status_counts": {},
            "integration_counts": {r["integration_name"]: r["count"] for r in integration_counts},
            "type_counts": {r["action_type"]: r["count"] for r in type_counts}
        }
        
        for r in status_counts:
            count = r["count"]
            stats["status_counts"][r["status"]] = count
            stats["total"] += count
            
        # Calculate rates
        success_count = stats["status_counts"].get("SUCCESS", 0)
        failed_count = stats["status_counts"].get("FAILED", 0)
        completed_count = stats["status_counts"].get("COMPLETED", 0)
        success_total = success_count + completed_count
        
        resolved_total = success_total + failed_count + stats["status_counts"].get("REJECTED", 0)
        
        if resolved_total > 0:
            stats["success_rate"] = round(success_total / resolved_total, 4)
            stats["failure_rate"] = round(failed_count / resolved_total, 4)
        else:
            stats["success_rate"] = 0.0
            stats["failure_rate"] = 0.0
            
        return stats

    def clear(self) -> None:
        """Testing utility to clear all actions."""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM actions')
            conn.commit()

action_repository = ActionRepository()
