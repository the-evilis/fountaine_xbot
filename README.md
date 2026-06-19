# Telegram Bot for English School in Bishkek

This bot is designed to collect applications for a trial English lesson at a school in Bishkek. It supports Russian and Kyrgyz languages.

## Features

- Language selection (Russian/Kyrgyz)
- FSM (Finite State Machine) for step-by-step data collection:
  1. Language choice
  2. Name
  3. Phone number (with validation)
  4. English level (or a test to determine it)
  5. Learning goal
  6. Preferred time
  7. Summary and confirmation
- Saves data to Google Sheets
- Sends a notification to the admin Telegram chat

## Requirements

- Python 3.7+
- aiogram 3.x
- gspread
- google-auth

## Installation

1. Clone the repository or copy the files to a directory.
2. Place the service account JSON file (provided by Google Cloud) in the same directory as `main.py`. 
   The filename should match the one in `config.py` (currently `fountain-498904-*.json`). 
   Replace `*` with the actual suffix or update `config.py` with the exact filename.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure the bot:
   - Open `config.py` and ensure the following are set correctly:
     - `BOT_TOKEN`: Your bot token from BotFather.
     - `ADMIN_CHAT_ID`: Your Telegram user ID (or chat ID) to receive notifications.
     - `SHEET_ID`: The ID of your Google Spreadsheet.
     - `SERVICE_ACCOUNT_FILE`: The path to your service account JSON file.
   - The Google Sheet must have a worksheet named "Лист1" (or change the name in `main.py`).
   - Share the Google Sheet with the service account email (found in the JSON file) with edit permissions.

## Running the Bot

```bash
python main.py
```

The bot will start polling for updates.

## Project Structure

```
english_school_bot/
│
├── main.py          # Main bot logic
├── config.py        # Configuration (token, IDs, etc.)
├── requirements.txt # Python dependencies
├── README.md        # This file
└── fountain-498904-*.json   # Google Service Account key (place here)
```

## Notes

- The bot uses `aiogram` version 3.x with `MemoryStorage` for FSM (suitable for small to medium usage).
- Phone validation accepts formats: `+996 XXX XXX XXX` or `0XXX XXX XXX` (spaces optional).
- The English level test consists of 3 questions. Based on the score:
  - 0-1 correct -> Beginner
  - 2 correct -> Elementary
  - 3 correct -> Intermediate
- After confirmation, data is appended to Google Sheets and the admin is notified.
- The bot supports going back at each step (except language selection) and restarting with `/start` at any time.

## Customization

- To change the questionnaire, edit the texts in `TEXTS` dictionary in `main.py`.
- To adjust the test questions or scoring, modify the test handler functions.
- To change the Google Sheet columns, adjust the `save_to_sheets` function.

## License

This project is for educational purposes. Feel free to adapt and use.