import os
import sqlite3
import pytest
from unittest.mock import patch

from shared import db

@pytest.fixture
def temp_db_path(tmp_path):
    # Setup an in-memory database for testing
    db_file = tmp_path / "test_football.db"
    return str(db_file)

def test_init_db(temp_db_path):
    with patch("shared.db.DB_PATH", temp_db_path):
        db.init_db()
        
        # Verify the database file was created
        assert os.path.exists(temp_db_path)
        
        # Verify tables were created
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        
        expected_tables = {"matches", "match_details", "team_id_map", "match_analysis"}
        assert expected_tables.issubset(tables)
        
        conn.close()

def test_update_results(temp_db_path):
    with patch("shared.db.DB_PATH", temp_db_path):
        db.init_db()
        
        # Insert a dummy match
        conn = db.get_connection()
        conn.execute("""
            INSERT INTO matches (match_id, home_team, away_team, home_team_id, away_team_id, league_id, match_date, match_time, start_timestamp_utc, scraped_at)
            VALUES (1, 'Home', 'Away', 100, 200, 10, '2026-08-03', '20:00', 123456789, 'now')
        """)
        conn.commit()
        conn.close()
        
        # Update the result
        db.update_results(1, 2, 1)
        
        # Check if the result was updated correctly
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT analysis_done, home_score, away_score FROM matches WHERE match_id = 1")
        row = cursor.fetchone()
        
        assert row["analysis_done"] == 2
        assert row["home_score"] == 2
        assert row["away_score"] == 1
        
        conn.close()
