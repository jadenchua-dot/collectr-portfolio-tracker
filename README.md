# Collectr portfolio tracker

A Python bot that watches a Pokémon card collection on [Collectr](https://getcollectr.com) and sends updates to Telegram (and optionally WhatsApp):

- **Every day:** the 3 cards that went up the most and the 3 that dropped the most
- **Every Sunday:** how much the whole portfolio went up or down that week

It reads your public Collectr showcase page, saves a snapshot each day in `history.json`, and works out the changes from those snapshots. It only uses the Python standard library and runs on a schedule with macOS `launchd`.

## 0. Setup
```
cp config.example.json config.json
```
Set `profile` to your Collectr showcase username (e.g. `@yourname`). Your showcase must be public.

## 1. Telegram (about 2 minutes)
1. In Telegram, message **@BotFather** → `/newbot` → pick a name. Copy the token it gives you.
2. Paste it into `config.json` as `telegram.bot_token`.
3. Open your new bot in Telegram and press **Start** (or send "hi").
4. Run `python3 tracker.py telegram-setup`. This finds your chat id and turns Telegram on.

## 2. WhatsApp (optional, free via CallMeBot)
1. Save **+34 644 51 95 23** in your contacts and send it on WhatsApp: `I allow callmebot to send me messages`
   (check callmebot.com for the current number if that doesn't reply).
2. It replies with an API key. In `config.json` set `whatsapp.phone` (with country code, e.g. `+65...`),
   `whatsapp.apikey`, and `"enabled": true`.

## 3. Try it
```
python3 tracker.py test              # sends a test message
python3 tracker.py run --dry-run     # shows today's report without sending
```

## 4. Schedule it
```
./install.sh          # every day at 09:00
./install.sh 8 30     # or pick a time
./install.sh uninstall
```
The Mac has to be on (or wake up) for the job to run. If it's asleep at that time, the job runs when it wakes.

## Notes
- Movers come from the 30 most valuable items on your showcase (about 78% of the value). The portfolio total covers everything.
- Day 1 uses Collectr's own price-change numbers. After that, changes are worked out from the snapshots saved in `history.json`.
- `weekly_day` in `config.json`: 0 = Monday … 6 = Sunday.
