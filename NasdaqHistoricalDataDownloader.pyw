#!/usr/bin/env python3
"""
Nasdaq Historical Data Downloader
=================================

Programma con interfaccia grafica (Windows e macOS) che scarica i prezzi
storici giornalieri delle azioni da nasdaq.com e li salva come CSV puliti.

Cosa fa, in breve
-----------------
1. Legge la lista dei ticker da "tickers.txt" (nella stessa cartella del file).
2. Mostra una finestra in cui l'utente sceglie l'orizzonte temporale:
   1 mese, 6 mesi, 1 anno, 5 anni, MAX (10 anni).
3. Per ogni ticker chiama l'API interna di Nasdaq, converte la risposta JSON
   in righe pulite e salva "HistoricalData/{TICKER}_historical_{periodo}.csv".

Dipendenze
----------
Solo la libreria standard di Python (tkinter, urllib, csv, json, ...).
Non serve installare nessun pacchetto con pip. "certifi" viene usato SOLO se
già presente (vedi _ssl_context), non è obbligatorio.

Perché si usa l'API e non la pagina web
---------------------------------------
La pagina pubblica
  https://www.nasdaq.com/market-activity/stocks/{t}/historical
      ?page=1&rows_per_page=10&timeline={m1|m6|y1|y5|y10}
è costruita in JavaScript dal browser: l'HTML scaricato non contiene la
tabella dei prezzi. Il browser, dopo aver caricato la pagina, chiama
un'API interna (non documentata ufficialmente):
  https://api.nasdaq.com/api/quote/{t}/historical
      ?assetclass=stocks&fromdate=AAAA-MM-GG&todate=AAAA-MM-GG&limit=N
Questo programma fa direttamente quella seconda chiamata. Il parametro
"timeline" della pagina (m1, m6, ...) viene comunque usato:
  - nel Referer della richiesta (per sembrare una navigazione normale);
  - nella finestra, per mostrare all'utente il link corrispondente.
L'API però ragiona per date "da/a": l'orizzonte scelto viene quindi tradotto
in un intervallo di date (vedi HORIZONS e date_range).

ATTENZIONE: essendo un'API non documentata, URL, parametri e struttura della
risposta possono cambiare senza preavviso. Il punto da aggiornare in quel
caso è quasi sempre json_to_rows() (ed eventualmente HEADERS / API_URL).

Struttura del file
------------------
  1. Import
  2. Configurazione        -> costanti modificabili (orizzonti, URL, pause...)
  3. Percorsi              -> dove stanno tickers.txt e HistoricalData/
  4. Logica di download    -> funzioni pure, NON dipendono dalla finestra
  5. Utilità di sistema    -> apertura di file/cartelle
  6. Interfaccia grafica   -> main(): crea la finestra con tkinter

La separazione tra (4) e (6) è voluta: la logica di download si può testare
e riusare senza aprire nessuna finestra.
"""

# Permette di scrivere annotazioni di tipo moderne (es. "list[str]",
# "date | None") anche su versioni di Python meno recenti: le annotazioni
# vengono lette come testo e non valutate a runtime.
from __future__ import annotations

# ============================================================================ #
# 1. IMPORT (tutti dalla libreria standard)
# ============================================================================ #
import calendar           # numero di giorni di un mese (per sottrarre mesi)
import csv                # scrittura dei file CSV
import gzip               # decompressione risposte HTTP compresse "gzip"
import json               # lettura della risposta JSON dell'API
import os                 # os.startfile per aprire file/cartelle su Windows
import queue              # coda thread-safe: il thread di download -> finestra
import ssl                # contesto HTTPS (certificati)
import subprocess         # comando "open"/"xdg-open" su Mac/Linux
import sys                # rilevamento del sistema operativo
import threading          # download in un thread separato dalla finestra
import time               # pausa tra una richiesta e l'altra
import urllib.error       # eccezioni HTTP/rete
import urllib.parse       # costruzione dei parametri dell'URL
import urllib.request     # richieste HTTP
import zlib               # decompressione risposte HTTP compresse "deflate"
from datetime import date, datetime
from pathlib import Path

# NB: tkinter NON è importato qui ma dentro main(). Così le funzioni di
# download si possono importare e testare anche su sistemi senza tkinter
# (per esempio un server Linux senza interfaccia grafica).


# ============================================================================ #
# 2. CONFIGURAZIONE
#    Tutti i valori che ha senso modificare sono raccolti qui.
# ============================================================================ #

# Orizzonti temporali proposti nella finestra.
#   chiave  = testo mostrato sul pulsante di scelta (e usato come valore interno)
#   valore  = tupla di 3 elementi:
#     [0] codice "timeline" usato dal sito Nasdaq nel link della pagina
#     [1] quanti mesi indietro partire rispetto a oggi (per l'API)
#     [2] suffisso usato nel nome del file CSV
# L'ordine delle chiavi è l'ordine in cui compaiono nella finestra.
# Per aggiungere un orizzonte basta aggiungere una riga (vedi DEVELOPER.md).
HORIZONS = {
    "1 mese":         ("m1", 1, "1m"),
    "6 mesi":         ("m6", 6, "6m"),
    "1 anno":         ("y1", 12, "1y"),
    "5 anni":         ("y5", 60, "5y"),
    "MAX (10 anni)":  ("y10", 120, "max"),
}

# Orizzonte selezionato all'apertura della finestra. Deve essere una chiave
# esistente di HORIZONS, altrimenti nessun pulsante risulta selezionato.
DEFAULT_HORIZON = "1 mese"

# Link della pagina pubblica: usato SOLO come Referer HTTP e come testo
# mostrato nella finestra. {ticker} va in minuscolo, come sul sito.
PAGE_URL = ("https://www.nasdaq.com/market-activity/stocks/{ticker}/historical"
            "?page=1&rows_per_page=10&timeline={timeline}")

# Endpoint dell'API interna da cui arrivano davvero i dati.
API_URL = "https://api.nasdaq.com/api/quote/{ticker}/historical"

# Secondi di attesa tra un ticker e il successivo, per non sovraccaricare il
# server e ridurre il rischio di blocchi anti-bot. Abbassarlo è sconsigliato.
DELAY_SECONDS = 2.5

# Secondi massimi di attesa per una singola risposta HTTP. Se scade, il
# ticker viene segnato come fallito e si passa al successivo.
TIMEOUT_SECONDS = 25

# Nomi del file con i ticker e della cartella di output. Entrambi vengono
# cercati/creati accanto a questo file .pyw (vedi sezione 3).
TICKERS_FILENAME = "tickers.txt"
OUTPUT_DIRNAME = "HistoricalData"

# Header HTTP inviati all'API. Imitano un browser Chrome reale: senza di
# essi l'API tende a rispondere 403 (accesso negato) o a non rispondere.
#   User-Agent       identifica il "browser"
#   Accept           dice che ci aspettiamo JSON
#   Accept-Language  lingua preferita
#   Accept-Encoding  accettiamo risposte compresse (gestite in fetch_json)
#   Origin           il sito da cui parte la richiesta
#   Connection       mantieni la connessione aperta
# Il Referer viene aggiunto per ogni ticker in fetch_json().
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Origin": "https://www.nasdaq.com",
    "Connection": "keep-alive",
}

# Intestazione (e quindi ordine delle colonne) dei CSV prodotti.
# Se la cambi, cambia di pari passo l'ordine dei valori in json_to_rows().
CSV_HEADER = ["ticker", "date", "open", "high", "low", "close", "volume"]


# ============================================================================ #
# 3. PERCORSI
#    I file vengono sempre cercati accanto al programma, NON nella "cartella
#    corrente" del sistema. Con un doppio clic la cartella corrente può essere
#    qualsiasi (es. la home dell'utente), quindi un percorso relativo come
#    "tickers.txt" punterebbe al posto sbagliato.
# ============================================================================ #
def app_dir() -> Path:
    """Restituisce la cartella che contiene questo file .pyw."""
    # __file__ = percorso di questo script; resolve() lo rende assoluto e
    # risolve eventuali collegamenti; parent = la cartella che lo contiene.
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()                          # cartella del programma
TICKERS_FILE = BASE_DIR / TICKERS_FILENAME    # .../tickers.txt
OUTPUT_DIR = BASE_DIR / OUTPUT_DIRNAME        # .../HistoricalData/


# ============================================================================ #
# 4. LOGICA DI DOWNLOAD
#    Nessuna di queste funzioni tocca la finestra: comunicano verso l'esterno
#    solo tramite valori di ritorno, eccezioni FetchError e la funzione "log"
#    passata a run_downloads().
# ============================================================================ #
class FetchError(Exception):
    """Errore "previsto" su un singolo ticker (rete, HTTP, dati mancanti...).

    Il messaggio è già scritto per l'utente finale e viene mostrato così com'è
    nel log. Un FetchError su un ticker NON interrompe gli altri download.
    """


def read_tickers(path: Path) -> list[str]:
    """Legge tickers.txt e restituisce la lista dei ticker, senza duplicati.

    Regole del file:
      - un ticker per riga, ma sono accettati anche più ticker sulla stessa
        riga separati da spazi, virgole o punti e virgola;
      - tutto ciò che segue "#" è un commento e viene ignorato;
      - maiuscole/minuscole indifferenti (tutto viene convertito in maiuscolo);
      - i duplicati vengono scartati mantenendo l'ordine della prima comparsa.
    Se il file non esiste, ne viene creato uno di esempio con AAPL e MSFT.
    """
    if not path.is_file():
        path.write_text("# Un ticker per riga. Le righe con # sono ignorate.\nAAPL\nMSFT\n",
                        encoding="utf-8")

    tickers: list[str] = []
    # "utf-8-sig" ignora l'eventuale BOM iniziale che il Blocco note di
    # Windows aggiunge a volte ai file salvati in UTF-8.
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.split("#", 1)[0]                     # scarta il commento
        # Virgole e punti e virgola diventano spazi, poi si divide sugli spazi.
        for t in line.replace(",", " ").replace(";", " ").split():
            t = t.strip().upper()
            if t and t not in tickers:                   # niente duplicati
                tickers.append(t)
    return tickers


def subtract_months(d: date, months: int) -> date:
    """Restituisce la data d spostata indietro di "months" mesi.

    Se il giorno non esiste nel mese di arrivo, usa l'ultimo giorno di quel
    mese. Esempi:
      31/03/2026 - 1 mese  -> 28/02/2026
      31/08/2026 - 6 mesi  -> 28/02/2026
      15/10/2026 - 12 mesi -> 15/10/2025
    """
    # Trasforma anno+mese in un unico contatore di mesi (anno*12 + mese da 0),
    # sottrae, poi lo riconverte in anno e mese con divmod.
    y, m = divmod(d.year * 12 + (d.month - 1) - months, 12)
    m += 1                                     # da 0-11 a 1-12
    last_day = calendar.monthrange(y, m)[1]    # giorni del mese di arrivo
    return date(y, m, min(d.day, last_day))


def date_range(months_back: int, today: date | None = None) -> tuple[str, str]:
    """Restituisce (data_inizio, data_fine) come testo "AAAA-MM-GG".

    data_fine è oggi; data_inizio è oggi meno "months_back" mesi.
    Il parametro "today" serve solo nei test, per fissare la data di oggi.
    """
    today = today or date.today()
    return subtract_months(today, months_back).isoformat(), today.isoformat()


def _ssl_context() -> ssl.SSLContext:
    """Crea il contesto HTTPS con cui verificare il certificato del server.

    Se è installato "certifi" usa i suoi certificati: su macOS il Python di
    python.org non usa i certificati di sistema, e senza certifi (o senza
    aver eseguito "Install Certificates.command") ogni richiesta fallirebbe
    con CERTIFICATE_VERIFY_FAILED. Se certifi manca usa i certificati di
    sistema, che su Windows funzionano senza fare nulla.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


# Creato una sola volta all'avvio e riusato per tutte le richieste.
SSL_CTX = _ssl_context()


def fetch_json(ticker: str, timeline: str, fromdate: str, todate: str) -> dict:
    """Scarica dall'API i dati storici di un ticker e restituisce il JSON.

    Parametri:
      ticker    es. "AAPL"
      timeline  codice del sito (m1, m6, y1, y5, y10), usato solo nel Referer
      fromdate  data di inizio "AAAA-MM-GG"
      todate    data di fine    "AAAA-MM-GG"

    Ritorna il JSON già decodificato (dizionario Python).
    Solleva FetchError con un messaggio leggibile in caso di problemi.
    """
    # Parametri dell'API. limit=9999 basta anche per MAX: 10 anni sono
    # circa 2.500 sedute di borsa.
    params = urllib.parse.urlencode({"assetclass": "stocks", "fromdate": fromdate,
                                     "todate": todate, "limit": 9999})
    # quote() protegge eventuali caratteri speciali nel ticker.
    url = API_URL.format(ticker=urllib.parse.quote(ticker)) + "?" + params

    # Agli header fissi si aggiunge il Referer: la pagina da cui
    # "proverrebbe" la richiesta, con la coda timeline scelta.
    headers = dict(HEADERS, Referer=PAGE_URL.format(ticker=ticker.lower(), timeline=timeline))
    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=SSL_CTX) as r:
            raw = r.read()                                         # byte grezzi
            enc = (r.headers.get("Content-Encoding") or "").lower()
    except urllib.error.HTTPError as e:
        # Il server ha risposto con un errore (es. 403 bloccato, 404, 500).
        # NB: HTTPError va intercettato PRIMA di URLError, di cui è sottoclasse.
        raise FetchError(f"HTTP {e.code}")
    except urllib.error.URLError as e:
        # Nessuna risposta valida: rete assente, DNS, problemi di certificati...
        reason = str(e.reason)
        if "CERTIFICATE_VERIFY_FAILED" in reason:
            raise FetchError("certificati SSL mancanti (su Mac: esegui 'Install Certificates.command' "
                             "nella cartella Applicazioni > Python 3.x)")
        raise FetchError(f"errore di rete: {reason}")
    except TimeoutError:
        # Il server non ha risposto entro TIMEOUT_SECONDS.
        raise FetchError("timeout (il server non risponde: possibile blocco anti-bot)")

    # Abbiamo dichiarato di accettare risposte compresse (Accept-Encoding):
    # se il server ha compresso, decomprimiamo prima di leggere il JSON.
    if enc == "gzip":
        raw = gzip.decompress(raw)
    elif enc == "deflate":
        raw = zlib.decompress(raw)

    try:
        return json.loads(raw.decode("utf-8"))
    except ValueError:
        # Risposta non JSON: di solito una pagina HTML di blocco anti-bot.
        raise FetchError("risposta non JSON (probabile pagina anti-bot)")


def _num(value) -> str:
    """Pulisce un valore numerico dell'API e lo restituisce come testo.

    "$227.50"    -> "227.50"
    "45,123,456" -> "45123456"
    "N/A", "--", "" o valori non numerici -> "" (cella vuota nel CSV)

    Restituisce testo e non float per non introdurre arrotondamenti:
    il numero viene scritto nel CSV esattamente come lo fornisce Nasdaq.
    """
    s = str(value or "").replace("$", "").replace(",", "").strip()
    if s in ("", "N/A", "--"):
        return ""
    try:
        float(s)          # verifica soltanto che sia un numero valido
        return s
    except ValueError:
        return ""


def json_to_rows(payload: dict, ticker: str) -> list[list[str]]:
    """Converte il JSON dell'API in righe pronte per il CSV.

    Struttura attesa del JSON (osservata, NON garantita da Nasdaq):
      {
        "data": {
          "tradesTable": {
            "rows": [
              {"date": "10/08/2026", "close": "$227.50", "volume": "45,123,456",
               "open": "$226.10", "high": "$228.00", "low": "$225.40"},
              ...
            ]
          }
        },
        "status": {"rCode": 200, "bCodeMessage": null}
      }
    Con un ticker inesistente "data" è null e il motivo è in
    status.bCodeMessage (lista di {"code":..., "errorMessage":...}).

    Ogni riga restituita ha l'ordine di CSV_HEADER:
      [ticker, data AAAA-MM-GG, open, high, low, close, volume]
    Le righe sono ordinate dalla data più recente alla meno recente.

    Se Nasdaq cambia formato, questa è la funzione da aggiornare.
    """
    # --- 1) controllo che ci siano dati -------------------------------------
    data = payload.get("data")
    if not data:
        # Cerca un messaggio di errore utile da mostrare all'utente.
        status = payload.get("status") or {}
        msg = status.get("bCodeMessage") or payload.get("message") or "nessun dato"
        if isinstance(msg, list) and msg and isinstance(msg[0], dict):
            msg = msg[0].get("errorMessage", msg)
        raise FetchError(f"ticker non valido o nessun dato ({msg})")

    rows = (data.get("tradesTable") or {}).get("rows")
    if not rows:
        raise FetchError("nessuna riga nella risposta (struttura cambiata o periodo vuoto)")

    # --- 2) conversione riga per riga ---------------------------------------
    # Ogni elemento di "out" è (data_iso, riga): la data è tenuta a parte
    # solo per poter ordinare le righe.
    out: list[tuple[str, list[str]]] = []
    for r in rows:
        # Nomi dei campi in minuscolo e senza spazi, per tollerare piccole
        # variazioni dell'API (es. "Close" invece di "close").
        r = {str(k).strip().lower(): v for k, v in r.items()}

        # Data: da formato americano MM/GG/AAAA a ISO AAAA-MM-GG.
        # Se il formato è diverso da quello atteso, la data resta com'è.
        try:
            d = datetime.strptime(str(r.get("date", "")).strip(), "%m/%d/%Y").date().isoformat()
        except ValueError:
            d = str(r.get("date", ""))

        # Ordine OHLC (open, high, low, close): diverso dall'ordine del sito.
        out.append((d, [ticker, d,
                        _num(r.get("open")), _num(r.get("high")),
                        _num(r.get("low")), _num(r.get("close")),
                        _num(r.get("volume"))]))

    # --- 3) ordinamento -----------------------------------------------------
    # Le date ISO si ordinano correttamente anche come testo.
    # reverse=True = dalla più recente; metti False per l'ordine cronologico.
    out.sort(key=lambda x: x[0], reverse=True)
    return [row for _, row in out]


def save_csv(rows: list[list[str]], path: Path) -> None:
    """Scrive le righe in un file CSV (UTF-8, separatore virgola).

    newline="" è richiesto dal modulo csv: evita righe vuote in più su Windows.
    Un file con lo stesso nome viene sovrascritto.
    """
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(CSV_HEADER)
        w.writerows(rows)


def run_downloads(tickers: list[str], horizon: str, log, stop_event: threading.Event) -> None:
    """Scarica tutti i ticker uno dopo l'altro. Gira nel thread di download.

    Parametri:
      tickers     lista di ticker da scaricare
      horizon     chiave di HORIZONS scelta dall'utente (es. "5 anni")
      log         funzione chiamata per comunicare con l'esterno:
                    log(testo)              -> aggiunge una riga al log
                    log(None, progress=n)   -> aggiorna la barra (n completati)
                  Nella finestra è thread_log(); nei test può essere print.
      stop_event  se impostato (pulsante "Ferma"), interrompe il ciclo prima
                  del ticker successivo. Il ticker in corso viene completato.

    Gli errori di un ticker vengono scritti nel log e NON fermano gli altri.
    """
    # Dall'orizzonte ricava codice timeline, mesi e suffisso del file.
    timeline, months, suffix = HORIZONS[horizon]
    fromdate, todate = date_range(months)

    OUTPUT_DIR.mkdir(exist_ok=True)       # crea HistoricalData/ se manca
    log(f"Orizzonte: {horizon}  (timeline={timeline}, dal {fromdate} al {todate})")
    log(f"Ticker: {len(tickers)}  |  Cartella: {OUTPUT_DIR}\n")

    ok, failed = 0, []
    for i, t in enumerate(tickers, 1):    # i parte da 1 (per "[1/35]")
        if stop_event.is_set():
            log("Interrotto dall'utente.")
            break

        prefix = f"[{i}/{len(tickers)}] {t}"
        try:
            # download -> conversione -> salvataggio
            rows = json_to_rows(fetch_json(t, timeline, fromdate, todate), t)
            out = OUTPUT_DIR / f"{t}_historical_{suffix}.csv"
            save_csv(rows, out)
            log(f"{prefix}: Download completato ({len(rows)} righe)")
            ok += 1
        except FetchError as e:
            # Errore previsto: messaggio già pensato per l'utente.
            log(f"{prefix}: Errore: {e}")
            failed.append(t)
        except Exception as e:
            # Errore imprevisto (bug, disco pieno, file aperto in Excel...):
            # lo mostriamo con il tipo di eccezione, ma andiamo avanti.
            log(f"{prefix}: Errore imprevisto: {type(e).__name__}: {e}")
            failed.append(t)

        log(None, progress=i)             # avanza la barra di progresso

        # Pausa tra un ticker e l'altro (non dopo l'ultimo, né se fermato).
        if i < len(tickers) and not stop_event.is_set():
            time.sleep(DELAY_SECONDS)

    log(f"\nCompletati: {ok}/{len(tickers)}" + (f"  |  Falliti: {', '.join(failed)}" if failed else ""))


# ============================================================================ #
# 5. UTILITÀ DI SISTEMA
# ============================================================================ #
def open_path(path: Path) -> None:
    """Apre un file o una cartella con il programma predefinito del sistema.

    Windows: os.startfile (Blocco note per .txt, Esplora file per le cartelle)
    macOS:   comando "open"   (TextEdit / Finder)
    Linux:   comando "xdg-open" (non ufficialmente supportato, ma funziona)
    """
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]  (esiste solo su Windows)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


# ============================================================================ #
# 6. INTERFACCIA GRAFICA
#
#    Regola fondamentale di tkinter: la finestra va toccata SOLO dal thread
#    principale. Il download gira in un thread separato (altrimenti la
#    finestra si bloccherebbe per tutta la durata), quindi il thread di
#    download NON scrive mai direttamente nella finestra: mette i messaggi in
#    una coda (queue.Queue), e il thread principale la svuota ogni 150 ms
#    con poll().
#
#        thread download --thread_log()--> [coda msgs] --poll()--> finestra
#
#    Disposizione (griglia del frame principale "frm"):
#      riga 0  etichetta "Orizzonte temporale:"
#      riga 1  pulsanti di scelta degli orizzonti
#      riga 2  link corrispondente all'orizzonte (testo grigio)
#      riga 3  pulsanti: Scarica, Ferma | Apri HistoricalData, Modifica tickers.txt
#      riga 4  barra di avanzamento
#      riga 5  area di log (si allarga con la finestra)
# ============================================================================ #
def main() -> None:
    """Crea la finestra e avvia il ciclo degli eventi di tkinter."""
    import tkinter as tk
    from tkinter import ttk                        # widget con stile nativo del sistema
    from tkinter.scrolledtext import ScrolledText  # area di testo con barra di scorrimento

    # --- finestra principale ------------------------------------------------
    root = tk.Tk()
    root.title("Nasdaq Historical Data Downloader")
    root.geometry("560x470")      # dimensione iniziale (larghezza x altezza)
    root.minsize(460, 380)        # dimensione minima consentita

    # --- stato condiviso ----------------------------------------------------
    msgs: queue.Queue = queue.Queue()   # messaggi dal thread di download
    stop_event = threading.Event()      # impostato dal pulsante "Ferma"
    # Riferimento al thread in corso. È un dizionario e non una semplice
    # variabile perché le funzioni interne (start, poll) devono poterlo
    # modificare senza usare "nonlocal".
    worker: dict = {"thread": None}

    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)

    # --- righe 0-1: scelta dell'orizzonte -----------------------------------
    ttk.Label(frm, text="Orizzonte temporale:").grid(row=0, column=0, sticky="w")
    # StringVar contiene la chiave di HORIZONS selezionata.
    horizon = tk.StringVar(value=DEFAULT_HORIZON)
    hz = ttk.Frame(frm)
    hz.grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))
    # Un pulsante di scelta per ogni orizzonte; tutti legati alla stessa
    # variabile, quindi se ne può selezionare uno solo alla volta.
    for label in HORIZONS:
        ttk.Radiobutton(hz, text=label, value=label, variable=horizon).pack(side="left", padx=(0, 10))

    # --- riga 2: link dell'orizzonte selezionato ----------------------------
    link_var = tk.StringVar()
    ttk.Label(frm, textvariable=link_var, foreground="gray").grid(row=2, column=0, columnspan=3,
                                                                  sticky="w")

    def update_link(*_):
        """Aggiorna il testo del link con la coda timeline= dell'orizzonte."""
        link_var.set("Link: …/historical?page=1&rows_per_page=10&timeline="
                     + HORIZONS[horizon.get()][0])
    # trace_add: chiama update_link ogni volta che cambia l'orizzonte scelto.
    horizon.trace_add("write", update_link)
    update_link()     # prima impostazione all'apertura

    # --- riga 3: pulsanti ---------------------------------------------------
    btns = ttk.Frame(frm)
    btns.grid(row=3, column=0, columnspan=3, sticky="we", pady=8)
    start_btn = ttk.Button(btns, text="Scarica")                    # comando assegnato più sotto
    stop_btn = ttk.Button(btns, text="Ferma", state="disabled")     # attivo solo durante il download
    start_btn.pack(side="left")
    stop_btn.pack(side="left", padx=6)
    # "Modifica tickers.txt": read_tickers crea il file se manca, poi lo apre.
    ttk.Button(btns, text="Modifica tickers.txt",
               command=lambda: (read_tickers(TICKERS_FILE), open_path(TICKERS_FILE))
               ).pack(side="right")
    # "Apri HistoricalData": crea la cartella se manca, poi la apre.
    ttk.Button(btns, text="Apri HistoricalData",
               command=lambda: (OUTPUT_DIR.mkdir(exist_ok=True), open_path(OUTPUT_DIR))
               ).pack(side="right", padx=6)

    # --- riga 4: barra di avanzamento ---------------------------------------
    # "determinate": va da 0 a maximum (= numero di ticker, impostato in start()).
    progress = ttk.Progressbar(frm, mode="determinate")
    progress.grid(row=4, column=0, columnspan=3, sticky="we")

    # --- riga 5: log --------------------------------------------------------
    # state="disabled" impedisce all'utente di scriverci; il programma la
    # riabilita per un attimo ogni volta che aggiunge testo (write_log).
    log_box = ScrolledText(frm, height=14, state="disabled", wrap="word")
    log_box.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
    # La colonna 0 e la riga 5 si allargano quando si ridimensiona la finestra.
    frm.columnconfigure(0, weight=1)
    frm.rowconfigure(5, weight=1)

    # --- funzioni della finestra --------------------------------------------
    def write_log(text: str) -> None:
        """Aggiunge una riga al log. Da chiamare SOLO nel thread principale."""
        log_box.configure(state="normal")
        log_box.insert("end", text + "\n")
        log_box.see("end")                 # scorre in fondo
        log_box.configure(state="disabled")

    def thread_log(text, progress=None):
        """Versione di "log" passata al thread di download.

        Non tocca la finestra: mette (testo, progresso) nella coda, che
        poll() svuoterà nel thread principale.
        """
        msgs.put((text, progress))

    def poll():
        """Gira ogni 150 ms nel thread principale.

        1. Svuota la coda dei messaggi e aggiorna log e barra.
        2. Se il thread di download è finito, riattiva "Scarica" e
           disattiva "Ferma".
        3. Si riprogramma con root.after per il giro successivo.
        """
        try:
            while True:
                text, prog = msgs.get_nowait()   # solleva queue.Empty se vuota
                if text is not None:
                    write_log(text)
                if prog is not None:
                    progress["value"] = prog
        except queue.Empty:
            pass

        th = worker["thread"]
        if th is not None and not th.is_alive():
            worker["thread"] = None
            start_btn.configure(state="normal")
            stop_btn.configure(state="disabled")

        root.after(150, poll)

    def start():
        """Pulsante "Scarica": legge i ticker e avvia il thread di download."""
        tickers = read_tickers(TICKERS_FILE)   # riletto a ogni clic: vale l'ultima modifica
        if not tickers:
            write_log("tickers.txt è vuoto: aggiungi almeno un ticker.")
            return

        # Pulisce il log e azzera la barra.
        log_box.configure(state="normal")
        log_box.delete("1.0", "end")           # "1.0" = riga 1, carattere 0
        log_box.configure(state="disabled")
        progress.configure(maximum=len(tickers), value=0)

        stop_event.clear()                     # annulla un eventuale "Ferma" precedente
        start_btn.configure(state="disabled")  # evita di avviare due download insieme
        stop_btn.configure(state="normal")

        # daemon=True: se l'utente chiude la finestra durante un download,
        # il programma termina subito senza aspettare il thread.
        th = threading.Thread(target=run_downloads,
                              args=(tickers, horizon.get(), thread_log, stop_event), daemon=True)
        worker["thread"] = th
        th.start()

    start_btn.configure(command=start)
    stop_btn.configure(command=stop_event.set)   # "Ferma" imposta solo il segnale

    # --- avvio --------------------------------------------------------------
    write_log(f"Ticker letti da: {TICKERS_FILE}")
    write_log("Scegli l'orizzonte e premi 'Scarica'.")
    poll()            # avvia il ciclo di controllo della coda
    root.mainloop()   # ciclo degli eventi: resta qui finché la finestra è aperta


# Eseguito solo se il file viene lanciato direttamente (doppio clic o
# "python NasdaqHistoricalDataDownloader.pyw"), non quando viene importato
# da un altro script, per esempio dai test.
if __name__ == "__main__":
    main()
