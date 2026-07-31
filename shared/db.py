import os
import sqlite3

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "football.db")


def get_connection():
    # connect to db with WAL mode for concurrency
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # create tables if they do not exist
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_team_id INTEGER NOT NULL,
            away_team_id INTEGER NOT NULL,
            league_id INTEGER NOT NULL,
            league_name TEXT,
            match_date TEXT NOT NULL,
            match_time TEXT NOT NULL,
            start_timestamp_utc INTEGER NOT NULL,
            detail_fetched INTEGER DEFAULT 0,
            analysis_done INTEGER DEFAULT 0,
            scraped_at TEXT NOT NULL,
            postponed INTEGER DEFAULT 0,
            home_score INTEGER,
            away_score INTEGER
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_details (
            match_id INTEGER PRIMARY KEY REFERENCES matches(match_id),
            referee_name TEXT,
            referee_country TEXT,
            home_formation TEXT,
            away_formation TEXT,
            home_lineup_json TEXT,
            away_lineup_json TEXT,
            home_coach TEXT,
            away_coach TEXT,
            home_missing_players_json TEXT,
            away_missing_players_json TEXT,
            home_style_tag TEXT,
            away_style_tag TEXT,
            home_news_json TEXT,
            away_news_json TEXT,
            rich_data_json TEXT,
            data_quality_score INTEGER DEFAULT 0,
            fetched_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS team_id_map (
            sofascore_team_id INTEGER PRIMARY KEY,
            team_name TEXT NOT NULL,
            transfermarkt_club_id INTEGER,
            verified_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS match_analysis (
            match_id INTEGER PRIMARY KEY REFERENCES matches(match_id),
            analysis_text TEXT NOT NULL,
            model_used TEXT NOT NULL,
            generated_at TEXT NOT NULL
        )
    """)

    conn.commit()

    _schema_migration(cursor)
    conn.commit()
    conn.close()


def update_results(match_id, home_score, away_score):
    # update match scores in database
    conn = get_connection()
    conn.execute(
        "UPDATE matches SET analysis_done = 2, home_score = ?, away_score = ? WHERE match_id = ?",
        (home_score, away_score, match_id)
    )
    conn.commit()
    conn.close()


def _schema_migration(cursor):
    # add missing columns to db if needed
    new_columns = {
        "match_details": [
            ("rich_data_json", "TEXT"),
            ("data_quality_score", "INTEGER"),
        ],
        "matches": [
            ("postponed", "INTEGER DEFAULT 0"),
        ],
    }

    for table, columns in new_columns.items():
        try:
            cursor.execute(f"PRAGMA table_info({table})")
            existing = {r[1] for r in cursor.fetchall()}
        except Exception:
            continue

        for name, col_type in columns:
            if name not in existing:
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")
                except Exception:
                    pass
