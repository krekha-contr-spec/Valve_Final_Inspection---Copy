import os
import time
from datetime import datetime
from typing import Optional, Any, List, Dict, Tuple
import pandas as pd
from werkzeug.security import generate_password_hash, check_password_hash
import pyodbc


class DatabaseManager:
    def __init__(self):
        self.conn: Optional[pyodbc.Connection] = None
        self.conn_str = os.environ.get(
            "DATABASE_URL",
            (
                "DRIVER={ODBC Driver 18 for SQL Server};"
                "SERVER=REVLGNDYSQL;"
                "DATABASE=inspection_db;"
                "UID=sa;"
                "PWD=Password@123;"
                "Encrypt=no;"
                "Trusted_Connection=no;"
                "TrustServerCertificate=yes;"
                "Connection Timeout=30;"
                "MARS_Connection=yes;"
            )
        )

    def get_connection(self) -> Optional[pyodbc.Connection]:
        """Return a live DB connection or None if unable."""
        if self.conn:
            try:
                self.conn.cursor().execute("SELECT 1").fetchone()
                return self.conn
            except:
                self.conn = None

        for attempt in range(3):
            try:
                self.conn = pyodbc.connect(self.conn_str, autocommit=False)
                print("[DB] Connected successfully.")
                return self.conn
            except Exception as e:
                print(f"[DB] Connection failed: {e}")
                time.sleep(1)
        return None

    def check_connection(self) -> Tuple[bool, str]:
        conn = self.get_connection()
        if not conn:
            return False, "Connection Failed"
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT GETDATE()")
            server_time = cursor.fetchone()
            cursor.close()
            if server_time is None:
                return False, "No response from server"
            return True, f"Connected. Server Time: {server_time[0]}"
        except Exception as e:
            return False, f"Check failed: {e}"

    def get_part_name_from_details(self, part_number: str) -> Optional[str]:
        if not part_number:
            return None
        conn = self.get_connection()
        if not conn:
            return None
        try:
            cursor = conn.cursor()
            query = """
                SELECT [Part Name]
                FROM valve_details
                WHERE LTRIM(RTRIM([Part Number])) = ?
            """
            cursor.execute(query, (str(part_number).strip(),))
            row = cursor.fetchone()
            cursor.close()
            return row[0] if row is not None else None
        except Exception as e:
            print(f"[DB] get_part_name_from_details ERROR: {e}")
            return None

    def insert_inspection(self, data: Dict[str, Any]) -> Any:
        conn = self.get_connection()
        if not conn:
            print("[DB] No connection available")
            return False

        part_number = str(data.get("part_number", "")).strip()
        data["part_name"] = self.get_part_name_from_details(part_number) or "Unknown_Part"

        numeric_columns = [
            "ssim_score", "Core_Hardness_stem", "Crown_Face_runout",
            "Datum_to_End", "End_Finish", "End_Radius", "Groove_Diameter",
            "Groove_Chamfer_Angle", "Head_Diameter", "Neck_Diameter",
            "Overall_Length", "Stem_Diameter", "Seat_Angle",
            "Surface_Hardness_Nitriding"
        ]
        for col in numeric_columns:
            val = data.get(col)
            if val is None or val == "":
                continue
            try:
                data[col] = float(val)
            except Exception:
                pass

        query = """
        INSERT INTO inspections (
            Part_number, Part_name, Image_name, ssim_score, Result,
            Best_match, Defect_type, Timestamp, Location, Shifts,
            Core_Hardness_stem, Crown_Face_runout, Datum_to_End,
            End_Finish, End_Radius, Groove_Diameter, Groove_Chamfer_Angle,
            Head_Diameter, Neck_Diameter, Overall_Length, Stem_Diameter,
            Seat_Angle, Surface_Hardness_Nitriding
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            data.get("part_number"),
            data.get("part_name"),
            data.get("image_name"),
            data.get("ssim_score"),
            data.get("result"),
            data.get("best_match"),
            data.get("defect_type"),
            data.get("timestamp") or datetime.now(),
            data.get("location"),
            data.get("shifts"),
            data.get("Core_Hardness_stem"),
            data.get("Crown_Face_runout"),
            data.get("Datum_to_End"),
            data.get("End_Finish"),
            data.get("End_Radius"),
            data.get("Groove_Diameter"),
            data.get("Groove_Chamfer_Angle"),
            data.get("Head_Diameter"),
            data.get("Neck_Diameter"),
            data.get("Overall_Length"),
            data.get("Stem_Diameter"),
            data.get("Seat_Angle"),
            data.get("Surface_Hardness_Nitriding"),
        )

        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            cursor.execute("SELECT SCOPE_IDENTITY()")
            row = cursor.fetchone()
            cursor.close()
            return row[0] if row is not None else True
        except Exception as e:
            print(f"[DB] insert_inspection ERROR: {e}")
            try:
                conn.rollback()
            except Exception:
                pass
            return False

    def fetch_inspections(self, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None) -> pd.DataFrame:
        conn = self.get_connection()
        if not conn:
            return pd.DataFrame()

        query = "SELECT * FROM inspections WHERE 1=1"
        params: List[Any] = []
        if date_from:
            query += " AND [Timestamp] >= ?"
            params.append(date_from)
        if date_to:
            query += " AND [Timestamp] <= ?"
            params.append(date_to)
        query += " ORDER BY [Timestamp] DESC"

        try:
            return pd.read_sql_query(query, conn, params=params)  # type: ignore
        except Exception as e:
            print(f"[DB] fetch_inspections ERROR: {e}")
            return pd.DataFrame()

    def get_recent_inspections(self, limit: int = 10) -> List[Tuple[Any, ...]]:
        conn = self.get_connection()
        if not conn:
            return []
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT TOP {limit} * FROM inspections ORDER BY [Timestamp] DESC")
            rows = cursor.fetchall()
            cursor.close()
            return [tuple(row) for row in rows]
        except Exception as e:
            print(f"[DB] get_recent_inspections ERROR: {e}")
            return []

    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        conn = self.get_connection()
        if not conn:
            return None
        cur = conn.cursor()
        cur.execute("SELECT * FROM Users WHERE username=?", (username,))
        row = cur.fetchone()
        if not row:
            cur.close()
            return None
        cols = [c[0] for c in cur.description]
        cur.close()
        return dict(zip(cols, row))

    def create_user(self, username: str, password: str, role: str, location: str, ip: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO Users (username,password_hash,role,location,allowed_ip) VALUES (?,?,?,?,?)",
            (username, generate_password_hash(password), role, location, ip)
        )
        conn.commit()
        cur.close()
        return True

    def approve_user(self, username: str) -> bool:
        conn = self.get_connection()
        if not conn:
            return False
        cur = conn.cursor()
        cur.execute("UPDATE Users SET is_active=1 WHERE username=?", (username,))
        conn.commit()
        cur.close()
        return True

    def get_pending_users(self) -> List[Tuple[Any, Any, Any]]:
        conn = self.get_connection()
        if not conn:
            return []
        cur = conn.cursor()
        cur.execute("SELECT username, location, role FROM Users WHERE is_active=0")
        rows = cur.fetchall()
        cur.close()
        return [tuple(row) for row in rows]

    def fetch_filtered_inspections(
        self,
        start_time: datetime,
        location: Optional[str] = None,
        shift: Optional[str] = None,
        part_number: Optional[str] = None
    ) -> pd.DataFrame:
        conn = self.get_connection()
        if not conn:
            return pd.DataFrame()

        cursor = conn.cursor()
        query = "SELECT * FROM inspections WHERE [timestamp] >= ?"
        params: List[Any] = [start_time]

        if location:
            query += " AND Location = ?"
            params.append(location)
        if shift:
            query += " AND Shifts = ?"
            params.append(shift)
        if part_number:
            query += " AND Part_number = ?"
            params.append(part_number)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description]

        data = [dict(zip(columns, row)) for row in rows]
        df = pd.DataFrame(data)
        cursor.close()
        return df

db_manager = DatabaseManager()
connected, message = db_manager.check_connection()
print("[Connection Check]", message)
