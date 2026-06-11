# Smart Money SMC Bot

Telegram bot that scans Bybit futures symbols and sends simple SMC-style LONG/SHORT alerts.

## Setup

```powershell
& "C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe" -m pip install --target .deps -r requirements.txt
Copy-Item .env.example .env
```

Fill `.env`, then run:

```powershell
$env:PYTHONPATH = "$PWD\.deps"
& "C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe" -m smart_money_bot
```

## Commands

- `/add SYMBOL`
- `/remove SYMBOL`
- `/list`
- `/status`

## Tests

```powershell
$env:PYTHONPATH = "$PWD\.deps"
& "C:\Users\Lenovo\AppData\Local\Programs\Python\Python311\python.exe" -m unittest discover -s tests
```
