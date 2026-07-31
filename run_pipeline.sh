#!/bin/bash
# run daily pipeline

cd "$(dirname "$0")" || exit 1
source venv/bin/activate

LOG="logs/scraper.log"
echo "$(date '+%Y-%m-%d %H:%M:%S') --- Pipeline started ---" >> "$LOG"

# step 0: cleanup yesterday's data
echo "$(date '+%Y-%m-%d %H:%M:%S') [0/4] Cleanup" >> "$LOG"
python3 cleanup_task/main.py >> logs/cleanup.log 2>&1

# step 1: find matches
echo "$(date '+%Y-%m-%d %H:%M:%S') [1/4] Match finder" >> "$LOG"
python3 scraper_matches/main.py >> "$LOG" 2>&1

# step 2: collect details
echo "$(date '+%Y-%m-%d %H:%M:%S') [2/4] Detail collector" >> "$LOG"
python3 scraper_details/main.py >> "$LOG" 2>&1

# step 3: ai analysis
echo "$(date '+%Y-%m-%d %H:%M:%S') [3/4] AI engine" >> "$LOG"
python3 ai_engine/main.py >> logs/ai_engine.log 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') --- Pipeline finished ---" >> "$LOG"
