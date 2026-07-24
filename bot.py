"""
Bot Telegram per tracciare le spese di famiglia.

Come funziona:
- Ogni componente della famiglia invia nel gruppo una FOTO dello scontrino
  con l'IMPORTO scritto nella didascalia (es. "23,50" oppure "23.50 spesa").
- Il bot legge la didascalia, estrae l'importo e lo salva in un database
  locale (SQLite) insieme a chi l'ha inviato e quando.
- Con i comandi /settimana e /mese si ottiene il riepilogo delle spese
  per ciascun componente della famiglia.

Comandi disponibili:
  /settimana        -> spese della settimana corrente (lun-oggi), per persona
  /settimana_scorsa -> spese della settimana scorsa (lun-dom), per persona
  /mese             -> spese del mese corrente, per persona
  /mese_scorso      -> spese del mese scorso, per persona
  /aiuto            -> istruzioni rapide,
"""

import re
import sqlite3
import logging
from io import BytesIO
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

# Inserisci qui il token ottenuto da BotFather, oppure impostalo come
# variabile d'ambiente TELEGRAM_BOT_TOKEN (consigliato, più sicuro).
import os
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "INSERISCI_QUI_IL_TUO_TOKEN")

DB_PATH = Path(os.environ.get("DB_DIR", str(Path(__file__).parent))) / "spese.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DATABASE
# ---------------------------------------------------------------------------

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS spese (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            importo REAL NOT NULL,
            descrizione TEXT,
            timestamp TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def salva_spesa(chat_id: int, user_id: int, nome: str, importo: float, descrizione: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO spese (chat_id, user_id, nome, importo, descrizione, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (chat_id, user_id, nome, importo, descrizione, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()


def leggi_spese(chat_id: int, data_inizio: datetime, data_fine: datetime):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT nome, importo, descrizione, timestamp FROM spese "
        "WHERE chat_id = ? AND timestamp >= ? AND timestamp < ? "
        "ORDER BY timestamp",
        (chat_id, data_inizio.isoformat(), data_fine.isoformat()),
    )
    righe = cur.fetchall()
    conn.close()
    return righe


def leggi_ultime_spese(chat_id: int, n: int = 5):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT id, nome, importo, descrizione, timestamp FROM spese "
        "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
        (chat_id, n),
    )
    righe = cur.fetchall()
    conn.close()
    return righe


def elimina_spesa(chat_id: int, spesa_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "DELETE FROM spese WHERE id = ? AND chat_id = ?", (spesa_id, chat_id)
    )
    conn.commit()
    eliminata = cur.rowcount > 0
    conn.close()
    return eliminata


# ---------------------------------------------------------------------------
# ESTRAZIONE IMPORTO DALLA DIDASCALIA
# ---------------------------------------------------------------------------

# Cerca un numero tipo "23,50" - "23.50" - "23" - "1.234,50" nella didascalia
IMPORTO_REGEX = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*|\d+)([.,]\d{1,2})?")


def estrai_importo(testo: str):
    if not testo:
        return None
    match = IMPORTO_REGEX.search(testo.replace("€", "").strip())
    if not match:
        return None
    intero = match.group(1).replace(".", "").replace(" ", "")
    decimale = match.group(2)
    numero_str = intero + (decimale.replace(",", ".") if decimale else "")
    try:
        return round(float(numero_str), 2)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# HANDLER: RICEZIONE FOTO SCONTRINO
# ---------------------------------------------------------------------------

async def gestisci_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messaggio = update.message
    didascalia = messaggio.caption or ""
    importo = estrai_importo(didascalia)

    if importo is None:
        await messaggio.reply_text(
            "Non ho trovato un importo valido nella didascalia.\n"
            "Rimanda la foto scrivendo l'importo nella didascalia, es: 23,50"
        )
        return

    nome = messaggio.from_user.first_name
    salva_spesa(
        chat_id=messaggio.chat_id,
        user_id=messaggio.from_user.id,
        nome=nome,
        importo=importo,
        descrizione=didascalia,
    )

    await messaggio.reply_text(f"Registrato: {nome} ha speso {importo:.2f} €")


# ---------------------------------------------------------------------------
# HANDLER: REPORT SETTIMANA / MESE
# ---------------------------------------------------------------------------

def formatta_report(righe, titolo: str) -> str:
    if not righe:
        return f"{titolo}\n\nNessuna spesa registrata."

    totali_per_persona = {}
    totale_generale = 0.0
    for nome, importo, _descrizione, _timestamp in righe:
        totali_per_persona[nome] = totali_per_persona.get(nome, 0.0) + importo
        totale_generale += importo

    righe_testo = [titolo, ""]
    for nome, tot in sorted(totali_per_persona.items(), key=lambda x: -x[1]):
        righe_testo.append(f"• {nome}: {tot:.2f} €")
    righe_testo.append("")
    righe_testo.append(f"Totale famiglia: {totale_generale:.2f} €")
    return "\n".join(righe_testo)


def inizio_settimana(riferimento: datetime) -> datetime:
    # Lunedì della settimana di "riferimento", a mezzanotte
    giorni_da_lunedi = riferimento.weekday()  # lunedì = 0
    inizio = riferimento - timedelta(days=giorni_da_lunedi)
    return inizio.replace(hour=0, minute=0, second=0, microsecond=0)


def inizio_mese(riferimento: datetime) -> datetime:
    return riferimento.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def cmd_settimana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ora = datetime.now()
    inizio = inizio_settimana(ora)
    fine = ora + timedelta(seconds=1)
    righe = leggi_spese(update.effective_chat.id, inizio, fine)
    titolo = f"Spese settimana corrente ({inizio.strftime('%d/%m')} - {ora.strftime('%d/%m')})"
    await update.message.reply_text(formatta_report(righe, titolo))


async def cmd_settimana_scorsa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ora = datetime.now()
    fine = inizio_settimana(ora)
    inizio = fine - timedelta(days=7)
    righe = leggi_spese(update.effective_chat.id, inizio, fine)
    titolo = f"Spese settimana scorsa ({inizio.strftime('%d/%m')} - {(fine - timedelta(days=1)).strftime('%d/%m')})"
    await update.message.reply_text(formatta_report(righe, titolo))


async def cmd_mese(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ora = datetime.now()
    inizio = inizio_mese(ora)
    fine = ora + timedelta(seconds=1)
    titolo = f"Spese mese corrente ({inizio.strftime('%B %Y')})"
    righe = leggi_spese(update.effective_chat.id, inizio, fine)
    await update.message.reply_text(formatta_report(righe, titolo))


async def cmd_mese_scorso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ora = datetime.now()
    fine = inizio_mese(ora)
    ultimo_giorno_mese_scorso = fine - timedelta(days=1)
    inizio = inizio_mese(ultimo_giorno_mese_scorso)
    titolo = f"Spese mese scorso ({inizio.strftime('%B %Y')})"
    righe = leggi_spese(update.effective_chat.id, inizio, fine)
    await update.message.reply_text(formatta_report(righe, titolo))


async def cmd_ultime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    righe = leggi_ultime_spese(update.effective_chat.id, n=10)
    if not righe:
        await update.message.reply_text("Nessuna spesa registrata.")
        return

    testo = ["Ultime spese registrate:", ""]
    for spesa_id, nome, importo, descrizione, timestamp in righe:
        data = datetime.fromisoformat(timestamp).strftime("%d/%m %H:%M")
        testo.append(f"#{spesa_id} - {nome}: {importo:.2f} € ({data})")
    testo.append("")
    testo.append("Per cancellarne una: /elimina numero  (es: /elimina 12)")
    await update.message.reply_text("\n".join(testo))


async def cmd_elimina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(
            "Specifica il numero della spesa da eliminare.\n"
            "Usa /ultime per vedere i numeri, poi /elimina numero"
        )
        return

    try:
        spesa_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Il numero deve essere un intero, es: /elimina 12")
        return

    if elimina_spesa(update.effective_chat.id, spesa_id):
        await update.message.reply_text(f"Spesa #{spesa_id} eliminata.")
    else:
        await update.message.reply_text(
            f"Non ho trovato nessuna spesa #{spesa_id} in questo gruppo."
        )


def genera_grafico(righe, titolo: str) -> BytesIO:
    totali_per_persona = {}
    for nome, importo, _descrizione, _timestamp in righe:
        totali_per_persona[nome] = totali_per_persona.get(nome, 0.0) + importo

    persone = list(totali_per_persona.keys())
    valori = list(totali_per_persona.values())

    # ordina dal più alto al più basso
    ordine = sorted(range(len(valori)), key=lambda i: -valori[i])
    persone = [persone[i] for i in ordine]
    valori = [valori[i] for i in ordine]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    barre = ax.bar(persone, valori, color="#4C8BF5")
    ax.set_title(titolo)
    ax.set_ylabel("Euro (€)")
    ax.bar_label(barre, fmt="%.2f €", padding=3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    buffer.seek(0)
    return buffer


async def cmd_grafico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    periodo = context.args[0].lower() if context.args else "mese"
    ora = datetime.now()

    if periodo in ("settimana", "settimane"):
        inizio = inizio_settimana(ora)
        fine = ora + timedelta(seconds=1)
        titolo = f"Spese settimana corrente ({inizio.strftime('%d/%m')} - {ora.strftime('%d/%m')})"
    else:
        inizio = inizio_mese(ora)
        fine = ora + timedelta(seconds=1)
        titolo = f"Spese mese corrente ({inizio.strftime('%B %Y')})"

    righe = leggi_spese(update.effective_chat.id, inizio, fine)

    if not righe:
        await update.message.reply_text("Nessuna spesa registrata per questo periodo.")
        return

    grafico = genera_grafico(righe, titolo)
    await update.message.reply_photo(photo=grafico, caption=titolo)

async def cmd_grafico_settimana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    periodo = context.args[0].lower() if context.args else "mese"
    ora = datetime.now()

        inizio = inizio_settimana(ora)
        fine = ora + timedelta(seconds=1) 
        titolo = f"Spese settimana corrente ({inizio.strftime('%d/%m')} - {ora.strftime('%d/%m')})"
   

    righe = leggi_spese(update.effective_chat.id, inizio, fine)

    if not righe:
        await update.message.reply_text("Nessuna spesa registrata per questo periodo.")
        return

    grafico = genera_grafico(righe, titolo)
    await update.message.reply_photo(photo=grafico, caption=titolo)

async def cmd_aiuto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Come usarmi:\n\n"
        "1. Invia una foto dello scontrino nel gruppo\n"
        "2. Scrivi l'importo nella didascalia della foto (es: 23,50)\n\n"
        "Comandi:\n"
        "/settimana - spese della settimana corrente per persona\n"
        "/settimana_scorsa - spese della settimana scorsa\n"
        "/mese - spese del mese corrente per persona\n"
        "/mese_scorso - spese del mese scorso\n"
        "/ultime - ultime 10 spese registrate (con numero)\n"
        "/elimina numero - cancella una spesa sbagliata\n"
        "/grafico - grafico spese del mese corrente per persona\n"
        "/grafico_settimana - grafico spese della settimana corrente"
    )


# ---------------------------------------------------------------------------
# AVVIO BOT
# ---------------------------------------------------------------------------

def main():
    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler(["start", "aiuto", "help"], cmd_aiuto))
    app.add_handler(CommandHandler("settimana", cmd_settimana))
    app.add_handler(CommandHandler("settimana_scorsa", cmd_settimana_scorsa))
    app.add_handler(CommandHandler("mese", cmd_mese))
    app.add_handler(CommandHandler("mese_scorso", cmd_mese_scorso))
    app.add_handler(CommandHandler("ultime", cmd_ultime))
    app.add_handler(CommandHandler("elimina", cmd_elimina))
    app.add_handler(CommandHandler("grafico", cmd_grafico))
    app.add_handler(CommandHandler("grafico_settimana", cmd_grafico_setimana))
    app.add_handler(MessageHandler(filters.PHOTO, gestisci_foto))

    logger.info("Bot avviato. In ascolto...")
    app.run_polling()


if __name__ == "__main__":
    main()
