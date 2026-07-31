# ⚽ Football Analysis Bot - AI-Powered Match Predictor

An enterprise-grade MVP for football match prediction and analysis. This project automates the entire pipeline of football data gathering, statistical processing, and AI-driven insights generation. It scrapes match data from multiple sources, processes deep statistical models (including Poisson regression and Dixon-Coles adjustments), aggregates real-time news and injury reports, and utilizes Large Language Models (LLMs via NVIDIA NIM / LLaMA) to write highly detailed, professional match analysis summaries.

All final analyses and predictions are served directly to end-users through a streamlined, highly responsive Telegram Bot interface.

---

## ✨ Key Features

- **Automated Daily Pipeline**: A fully autonomous system that cleans old data, finds new fixtures, scrapes deep statistics, and generates AI analyses daily.
- **Deep Statistical Modeling**: Implements advanced mathematical models to calculate expected goals (xG), 1X2 probabilities, Over/Under rates, and BTTS (Both Teams To Score) likelihoods using Poisson distributions.
- **Smart Fallback Scraping**: Utilizes a sophisticated 4-tier HTTP client strategy (Direct TLS Impersonation $\to$ FlareSolverr $\to$ ScrapingAnt $\to$ ScraperAPI) to bypass Cloudflare and rate limits with virtually zero cost.
- **Context-Aware AI Analysis**: Feeds raw statistical data, referee strictness, weather conditions, missing players, and recent team news into an LLM to generate nuanced, human-like match previews.
- **Telegram Bot Interface**: A clean, pagination-supported Telegram UI for users to easily browse upcoming matches and read detailed reports via Telegraph integrations.

---

## 🏗️ System Architecture

The pipeline is fully modular, using SQLite (in WAL mode) to prevent locking issues between independent asynchronous processes.

### Core Modules

1. **`cleanup_task/main.py`** 
   - **Purpose**: Runs daily to archive past matches and clean up stale database records, keeping the system lightweight and fast.
2. **`scraper_matches/main.py`** 
   - **Purpose**: Scrapes daily fixtures and schedules from all supported top-tier leagues.
3. **`scraper_details/main.py`** 
   - **Purpose**: The heavy lifter. Collects deep statistical metrics (xG, team form, referee statistics, bookmaker odds, news, line-ups, and injury reports).
4. **`ai_engine/main.py`** 
   - **Purpose**: Feeds the compiled statistical context into a Large Language Model to generate human-readable, professional match analyses.
5. **`telegram_bot/bot.py`** 
   - **Purpose**: The user-facing Telegram Bot UI offering an easy-to-use menu to browse matches and read full AI analyses.

---

## 🚀 Installation & Setup

### 1. Prerequisites
- **Python 3.10+**
- **pip** package manager
- *(Optional but recommended)* **Docker** (for running `FlareSolverr` locally to bypass Cloudflare challenges).

### 2. Clone and Install

Clone the repository and install the dependencies:

```bash
git clone https://github.com/yourusername/football-bot.git
cd football-bot

# Create and activate virtual environment
python -m venv venv

# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the root directory and configure your API keys:

```env
# AI Models
NVIDIA_API_KEY=your_nvidia_api_key
GEMINI_API_KEY=your_gemini_api_key

# Telegram
TELEGRAM_BOT_TOKEN=your_telegram_bot_token

# Scraping Fallbacks (Optional)
SCRAPINGANT_API_KEY=your_scrapingant_key_optional
SCRAPER_API_KEY=your_scraper_api_key_optional
FLARESOLVERR_URL=http://localhost:8191/v1
```

---

## ⚙️ Running the Project

### The Daily Pipeline

You can run the entire data gathering and analysis pipeline sequentially via the provided shell script. It is highly recommended to schedule this script via a cron job (e.g., every morning at 08:00 AM).

```bash
chmod +x run_pipeline.sh
./run_pipeline.sh
```

Alternatively, you can run the modules manually in the correct order:

```bash
python cleanup_task/main.py
python scraper_matches/main.py
python scraper_details/main.py
python ai_engine/main.py
```

### The Telegram Bot

To start the user-facing Telegram Bot, simply run:

```bash
python telegram_bot/bot.py
```

Users can interact with the bot using the `/start` command to view upcoming matches, navigate through pagination, and read detailed analyses.

---

## 🧠 Technical Details

- **HTTP Client Strategy (`shared/http_client.py`)**: Uses a robust fallback system to ensure data is always scraped successfully while keeping API costs to an absolute minimum.
- **Prediction Model (`shared/prediction_model.py`)**: Computes Poisson distributions for match outcomes, taking into account team form, Dixon-Coles correlation, and specific referee strictness for yellow/red card predictions.
- **Data Persistence (`shared/db.py`)**: Uses `sqlite3` for fast, lightweight data storage. Schema auto-migrates and handles concurrent reads/writes safely.

---

## ⚠️ Disclaimer

This is a Minimum Viable Product (MVP) developed for educational, research, and portfolio purposes. Football match predictions and betting odds are highly volatile and subject to unpredictable real-world factors. Do not use this tool for financial advice or real-money betting.
