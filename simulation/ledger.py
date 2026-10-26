"""
simulation/ledger.py
Manages the operational lifecycle ledger for continuous data simulation.
Supports:
  - Appending LedgerRow entries
  - Querying history (as pandas DataFrame)
  - Exporting to SQLite, Parquet, and CSV
  - Computing a deterministic cryptographic ledger hash for reproducibility checks
"""
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import List, Optional
import pandas as pd

from simulation.schema import LEDGER_COLUMNS, LedgerRow


class SimulationLedger:
    def __init__(self, db_path: Optional[str | Path] = None):
        self.rows: List[LedgerRow] = []
        self.db_path = Path(db_path) if db_path else None
        if self.db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_sqlite()

    def _init_sqlite(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cols_sql = [
                "tick INTEGER PRIMARY KEY",
                "scenario_event TEXT",
                "n_lines INTEGER",
                "covariate_drift_score REAL",
                "genotype_drift_score REAL",
                "prediction_drift_score REAL",
                "labels_arrived_for_tick INTEGER",
                "realized_rmse REAL",
                "realized_r REAL",
                "trigger_fired BOOLEAN",
                "trigger_reason TEXT",
                "retrain_run_id TEXT",
                "champion_version TEXT",
                "challenger_version TEXT",
                "gate_result TEXT",
                "promoted BOOLEAN",
                "frozen_baseline_rmse REAL",
            ]
            cursor.execute(f"CREATE TABLE IF NOT EXISTS ledger ({', '.join(cols_sql)})")
            conn.commit()

    def append(self, row: LedgerRow):
        self.rows.append(row)
        if self.db_path:
            self._insert_sqlite(row)

    def _insert_sqlite(self, row: LedgerRow):
        d = row.to_dict()
        placeholders = ", ".join(["?"] * len(LEDGER_COLUMNS))
        cols_str = ", ".join(LEDGER_COLUMNS)
        values = [d.get(c) for c in LEDGER_COLUMNS]
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"INSERT OR REPLACE INTO ledger ({cols_str}) VALUES ({placeholders})",
                values,
            )
            conn.commit()

    def to_dataframe(self) -> pd.DataFrame:
        if not self.rows:
            return pd.DataFrame(columns=LEDGER_COLUMNS)
        data = [r.to_dict() for r in self.rows]
        df = pd.DataFrame(data)
        # Ensure exact column order
        for col in LEDGER_COLUMNS:
            if col not in df.columns:
                df[col] = None
        return df[LEDGER_COLUMNS]

    def export_parquet(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        df = self.to_dataframe()
        df.to_parquet(p, index=False)

    def export_csv(self, path: str | Path):
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        df = self.to_dataframe()
        df.to_csv(p, index=False)

    def export_all(
        self,
        sqlite_path: Optional[str | Path] = None,
        parquet_path: Optional[str | Path] = None,
        csv_path: Optional[str | Path] = None,
    ):
        """Export ledger to all requested storage formats."""
        if sqlite_path:
            p = Path(sqlite_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(p)
            self.to_dataframe().to_sql("ledger", conn, if_exists="replace", index=False)
            conn.close()
        if parquet_path:
            self.export_parquet(parquet_path)
        if csv_path:
            self.export_csv(csv_path)

    def compute_hash(self) -> str:
        """
        Compute deterministic SHA-256 hash of the entire ledger content.
        Used to verify principle 4 (Deterministic reproducibility).
        """
        df = self.to_dataframe()
        # Canonical string representation rounded to stable precision
        canonical_records = []
        for r in self.rows:
            d = r.to_dict()
            clean_d = {}
            for k, v in d.items():
                if isinstance(v, float):
                    clean_d[k] = round(v, 4)
                else:
                    clean_d[k] = v
            canonical_records.append(clean_d)
        json_bytes = json.dumps(canonical_records, sort_keys=True).encode("utf-8")
        return hashlib.sha256(json_bytes).hexdigest()

    def compute_content_hash(self) -> str:
        return self.compute_hash()
