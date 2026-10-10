# 📈 Nasdaq Historical Data Downloader

![Python](https://img.shields.io/badge/Python-3-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)
![License](https://img.shields.io/badge/license-MIT-green)
![Fueled by](https://img.shields.io/badge/fueled%20by-beer%20%F0%9F%8D%BA-f28e1c)


> ⚠️ **Progetto indipendente.** Questo software non è affiliato, approvato o sponsorizzato da Nasdaq, Inc. "Nasdaq" è un marchio registrato dei rispettivi proprietari ed è usato qui solo per indicare la fonte dei dati.

---

## Cos'è

Un piccolo programma con interfaccia grafica che scarica i **prezzi storici delle azioni** pubblicati su nasdaq.com e li salva come **file CSV puliti**, uno per titolo, pronti da aprire in Excel, Google Sheets, Python o R.

Si scrivono i ticker in un file di testo, si sceglie il periodo, si preme un pulsante per scaricare. Fine.
 
## Perché esiste

Scaricare a mano lo storico di 30-40 titoli dal sito vuol dire aprire una pagina alla volta, cambiare il periodo, scaricare, rinominare il file, ripulire i dati e ricominciare (una rottura infinita provata sulla mia pelle). Questo programma fa tutto in un colpo solo.

Utile per:
- **studenti** di economia e finanza che devono costruire dataset per esercitazioni e tesi
- **chi analizza un portafoglio** e vuole aggiornare i dati senza copia-incolla
- **chi fa analisi in Excel o Python** e vuole dati già nel formato giusto, senza simboli da togliere e con le date in formato ISO 8601
- **appassionati di trading** che vogliono tenere traccia dei prezzi dei titoli sul mercato USA

## Funzionalità

- 🪟 **Interfaccia grafica minimale**, nessuna riga di comando
- 📋 **Lista di ticker in un file di testo** (`tickers.txt`), uno per riga
- 🗓️ **Cinque orizzonti temporali**: 1 mese, 6 mesi, 1 anno, 5 anni, MAX (10 anni)
- 📁 **Un CSV per titolo** nella cartella `HistoricalData/`, con nome `TICKER_historical_PERIODO.csv` (es. `AAPL_historical_5y.csv`)
- 🐢 **Rispettoso del server**: pausa di 2,5 secondi tra una richiesta e l'altra
- 🧾 **Log chiaro** per ogni titolo: completato o errore, con il motivo
- 🐍 **Nessuna libreria esterna**: usa solo la libreria standard di Python
- 🛠️ **Installazione guidata di Python**: se Python manca, il lanciatore propone di installarlo dalla fonte ufficiale (python.org), verificando l'integrità del file

## Formato dei dati: cosa cambia rispetto al sito

I dati sono gli stessi mostrati su nasdaq.com, ma riorganizzati per essere usati subito, senza pulizia manuale.
Giusto per completezza NHDD = Nasdaq Historical Data Downloader.

| | Sito Nasdaq | NHDD |
|---|---|---|
| **Data** | `10/08/2026` (MM/GG/AAAA, americano) | `2026-10-08` (AAAA-MM-GG, standard ISO 8601) |
| **Ordine colonne** | Date, Close/Last, Volume, Open, High, Low | ticker, date, **open, high, low, close**, volume |
| **Prezzi** | `$227.50` | `227.50` (solo numero) |
| **Ticker** | non presente nella tabella | prima colonna di ogni riga |

Le scelte e il loro motivo:
- **Data ISO 8601**: è lo standard internazionale, non si confonde tra formato americano ed europeo (il 03/04 è marzo o aprile?) e si ordina correttamente anche come testo
- **Ordine OHLC (Open, High, Low, Close)**: è l'ordine convenzionale dei dati finanziari, quello che si aspettano la maggior parte delle librerie di analisi e dei grafici a candele
- **Colonna ticker**: puoi unire più CSV in un unico dataset senza perdere l'informazione su a quale titolo appartiene ogni riga

Le righe sono ordinate dalla data più recente alla meno recente.

Esempio:

```csv
ticker,date,open,high,low,close,volume
AAPL,2026-10-08,227.60,230.00,227.00,229.10,41870000
AAPL,2026-10-07,226.10,228.00,225.40,227.50,45123456
```

*(valori di esempio, non reali)*

## Installazione e uso

1. Scarica lo zip del programma ed estrailo dove vuoi
2. Apri `tickers.txt` e scrivi i ticker (nomi dei titoli secondo il NASDAQ) che ti interessano, uno per riga
3. Doppio clic su:
   - **Se hai un PC Windows** → `LaunchWindows.vbs`
   - **Se hai un Mac** → `LaunchMac.command`
4. Scegli l'orizzonte temporale e premi **Scarica**.
5. Trovi i CSV nella cartella `HistoricalData/`

Serve Python 3: se non è installato, al primo avvio il programma propone di installarlo in automatico. Tutti i dettagli sono nel file `LEGGIMI.txt`.

### Mac: "LaunchMac.command è danneggiato e non può essere aperto"

Il file **non è danneggiato**. macOS blocca così gli script scaricati da internet che non sono firmati da uno sviluppatore Apple registrato. Per sbloccarlo, una volta sola:

1. Apri il **Terminale** (Applicazioni → Utility → Terminale)
2. Scrivi `xattr -cr ` con uno spazio finale, **senza premere Invio**
3. Trascina la cartella **Nasdaq Historical Data Downloader** dentro la finestra del Terminale: il percorso si completa da solo
4. Premi **Invio** (non compare nessun messaggio, è normale) e rifai doppio clic su `LaunchMac.command`

Il comando risulterà simile a questo:

```bash
xattr -cr "/Users/tuonome/Downloads/Nasdaq Historical Data Downloader"
```

`xattr -cr` rimuove dai file della cartella l'attributo di "quarantena" che macOS aggiunge ai download. Non modifica il contenuto dei file e non cambia le impostazioni di sicurezza del Mac.

## Limiti e avvertenze

- Il programma usa un'**interfaccia interna e non documentata** di nasdaq.com. Se Nasdaq la modifica, il programma potrebbe smettere di funzionare finché non viene aggiornato
- I dati sono forniti **così come sono**, senza garanzie di completezza o correttezza. **Non** usarli come unica base per decisioni di investimento
- L'uso dei dati è soggetto ai **Termini d'uso di nasdaq.com**: verificali prima di qualsiasi uso diverso da quello personale o di studio
- I prezzi sono quelli pubblicati su nasdaq.com, **non rettificati per i dividendi**: per calcolare rendimenti totali servono dati rettificati da altre fonti
- "MAX" corrisponde a 10 anni, come sul sito

## Licenza

Distribuito con licenza **MIT**: vedi il file [LICENSE](LICENSE). La licenza riguarda il codice di questo progetto, non i dati scaricati.

## Autore

Fatto da **Matteo** ([@MatteoPizzinato](https://github.com/MatteoPizzinato)), studente universitario e programmatore non proprio bravissimo (sarei un sistemista...).

Se ti è stato utile, lascia una ⭐: è il mio modo di sapere che non ho perso solo io i pomeriggi a scaricare CSV a mano.
