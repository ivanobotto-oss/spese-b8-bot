# Bot Telegram – Spese di Famiglia

Traccia le spese familiari: ogni componente invia una foto dello scontrino
con l'importo nella didascalia, il bot lo registra e genera riepiloghi
settimanali/mensili per persona.

**Importante:** usa un **gruppo** Telegram, non un canale. Nei canali solo
gli admin possono postare; in un gruppo tutti possono inviare foto.

---

## 1. Crea il bot con BotFather (5 minuti)

1. Apri Telegram e cerca **@BotFather**
2. Invia il comando `/newbot`
3. Scegli un nome (es. "Spese Famiglia") e uno username che finisca in `bot`
   (es. `spesefamiglia_bot`)
4. BotFather ti darà un **token**, tipo:
   `123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw`
   Tienilo da parte, ti serve dopo.
5. (Consigliato) Manda a BotFather `/setprivacy` → scegli il tuo bot →
   scegli **Disable**. Così il bot può leggere le didascalie delle foto
   anche senza essere menzionato direttamente.

## 2. Crea il gruppo famiglia

1. Crea un nuovo Gruppo Telegram e aggiungi i componenti della famiglia
2. Aggiungi il bot al gruppo cercando il suo username
3. Rendilo admin del gruppo (Impostazioni gruppo → Amministratori →
   aggiungi il bot) — garantisce che legga tutti i messaggi

## 3. Fai girare il bot

Il bot deve rimanere "acceso" per ricevere i messaggi. Due strade:

### Opzione A — Sul tuo PC/Raspberry Pi (gratis, ma deve restare acceso)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="il-tuo-token-di-botfather"
python bot.py
```

Su Windows (PowerShell):
```powershell
pip install -r requirements.txt
$env:TELEGRAM_BOT_TOKEN="il-tuo-token-di-botfather"
python bot.py
```

### Opzione B — Hosting cloud gratuito 24/7 (consigliato)

Il PC di casa spento = bot spento. Per farlo girare sempre, usa un
servizio cloud gratuito, ad esempio **Railway.app** o **Render.com**:

1. Crea un account su https://railway.app (puoi accedere con GitHub)
2. Crea un nuovo progetto → "Deploy from GitHub repo" (carica prima
   questi file su un repository GitHub) oppure "Empty project" e carica
   i file manualmente
3. Nelle variabili d'ambiente del progetto aggiungi:
   `TELEGRAM_BOT_TOKEN = il-tuo-token`
4. Imposta come comando di avvio: `python bot.py`
5. Fai il deploy: il bot resta acceso 24/7 gratuitamente entro le soglie
   del piano free

Se vuoi, posso aiutarti passo passo con Railway quando arrivi a quel punto.

## 4. Come si usa

- Ogni componente della famiglia invia una foto dello scontrino nel gruppo
  **scrivendo l'importo nella didascalia**, es: `23,50` oppure `23,50 spesa`
- Il bot conferma con un messaggio "Registrato: [nome] ha speso 23,50 €"

Comandi disponibili nel gruppo:

| Comando | Cosa fa |
|---|---|
| `/settimana` | Spese della settimana corrente, per persona |
| `/settimana_scorsa` | Spese della settimana scorsa, per persona |
| `/mese` | Spese del mese corrente, per persona |
| `/mese_scorso` | Spese del mese scorso, per persona |
| `/aiuto` | Istruzioni rapide |

## 5. Dati

Le spese sono salvate in un file `spese.db` (SQLite) nella stessa cartella
del bot. È un file locale semplice: se vuoi analizzarlo con Excel/Google
Sheets, puoi aprirlo con un qualsiasi tool SQLite o chiedermi di
esportartelo in un secondo momento.

## 6. Possibili estensioni future

- Categorie di spesa (spesa, benzina, farmacia...)
- Esportazione mensile in Excel
- Grafici delle spese per persona
- OCR automatico dell'importo dallo scontrino (meno affidabile ma zero
  digitazione manuale)
