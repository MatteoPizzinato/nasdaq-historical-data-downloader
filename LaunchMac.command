#!/bin/bash
# =============================================================================
# LaunchMac.command - lanciatore di Nasdaq Historical Data Downloader
# =============================================================================
# I file ".command" sono script di shell che macOS esegue con un doppio clic,
# aprendoli nel Terminale.
#
# Cosa fa:
#   1. Cerca un Python 3 che abbia tkinter (serve per la finestra).
#   2. Se non lo trova, chiede all'utente se installarlo; in caso affermativo
#      scarica il pacchetto ufficiale da python.org, ne verifica il checksum,
#      lo installa (macOS chiede la password) e installa "certifi".
#   3. Avvia NasdaqHistoricalDataDownloader.pyw in background e prova a
#      chiudere la finestra del Terminale.
#
# Requisiti del file: fine riga Unix (LF) e permesso di esecuzione (chmod +x).
# Lo zip li conserva; se li perdi: chmod +x "LaunchMac.command"
#
# PER AGGIORNARE LA VERSIONE DI PYTHON: cambia PY_VER e PKG_SHA256,
# copiandoli dalla pagina di rilascio su python.org (sezione "Files").
# =============================================================================

# Si sposta nella cartella dello script: con il doppio clic la cartella
# corrente sarebbe la home dell'utente. Se non ci riesce, esce.
cd "$(dirname "$0")" || exit 1

# Versione di Python da installare e checksum SHA-256 ufficiale del pacchetto.
PY_VER="3.13.16"
PKG_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-macos11.pkg"
PKG_SHA256="30666509020b4da0dd8bc2e773255f34d76b7bb80b66960a928d5f6daa0192d7"


# -----------------------------------------------------------------------------
# find_python: stampa il percorso del primo python3 utilizzabile e ritorna 0;
# ritorna 1 se non ne trova. "Utilizzabile" = esiste, è eseguibile e
# "import tkinter" funziona.
# Ordine di ricerca:
#   1. Python di python.org     /Library/Frameworks/Python.framework/...
#   2. Homebrew su Apple Silicon /opt/homebrew/bin/python3
#   3. Homebrew su Intel        /usr/local/bin/python3 (qui finiscono anche i
#                               collegamenti creati dall'installer di python.org)
# /usr/bin/python3 di Apple NON viene usato: se mancano i Command Line Tools
# apre un popup di installazione, e comunque ha una versione di Tk vecchia.
# -----------------------------------------------------------------------------
find_python() {
  local p
  for p in /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
           /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if [ -x "$p" ] && "$p" -c "import tkinter" >/dev/null 2>&1; then
      echo "$p"; return 0
    fi
  done
  return 1
}


# -----------------------------------------------------------------------------
# install_python: scarica, verifica e installa il pacchetto di python.org.
# Ritorna 0 se riuscito, 1 in caso di errore o annullamento.
# -----------------------------------------------------------------------------
install_python() {
  # File temporaneo nella cartella temporanea dell'utente.
  local tmp="${TMPDIR:-/tmp}/python-${PY_VER}-macos11.pkg"

  # curl: -f fallisce sugli errori HTTP, -L segue i reindirizzamenti.
  echo "Download di Python ${PY_VER} da python.org (circa 67 MB)..."
  curl -fL --progress-bar -o "$tmp" "$PKG_URL" || { echo "Download fallito."; return 1; }

  # Confronto del checksum: se non coincide, il file viene cancellato.
  echo "Verifica del checksum SHA-256..."
  if [ "$(shasum -a 256 "$tmp" | awk '{print $1}')" != "$PKG_SHA256" ]; then
    rm -f "$tmp"; echo "Checksum non corrispondente: installazione annullata."; return 1
  fi

  # "installer" richiede i permessi di amministratore: osascript mostra la
  # normale finestra di macOS che chiede la password.
  echo "Installazione (macOS chiedera' la password del Mac)..."
  osascript -e "do shell script \"installer -pkg '$tmp' -target /\" with administrator privileges" \
    || { rm -f "$tmp"; echo "Installazione annullata o non riuscita."; return 1; }

  rm -f "$tmp"
  return 0
}


# -----------------------------------------------------------------------------
# Flusso principale
# -----------------------------------------------------------------------------
PY="$(find_python)"

if [ -z "$PY" ]; then
  # Python non trovato: dialogo nativo di macOS con due pulsanti.
  # "button returned of" restituisce il testo del pulsante premuto.
  answer=$(osascript -e 'button returned of (display dialog "Python 3 non è installato su questo Mac.\n\nVuoi scaricarlo e installarlo ora da python.org? (circa 67 MB, verrà chiesta la password del Mac)" buttons {"Annulla", "Installa"} default button "Installa" with title "Nasdaq Historical Data Downloader")' 2>/dev/null)
  if [ "$answer" != "Installa" ]; then exit 0; fi

  if ! install_python; then
    osascript -e 'display alert "Installazione di Python non riuscita" message "Installalo a mano da https://www.python.org/downloads/ e riprova."'
    # Lascia il Terminale aperto per poter leggere l'errore.
    read -n 1 -s -r -p "Premi un tasto per chiudere..."; exit 1
  fi

  # Dopo l'installazione cerca di nuovo.
  PY="$(find_python)"
  if [ -z "$PY" ]; then
    osascript -e 'display alert "Python installato ma non trovato" message "Riprova con un nuovo doppio clic su LaunchMac."'
    exit 1
  fi

  # Il Python di python.org non usa i certificati di sistema di macOS.
  # certifi fornisce i certificati necessari per le connessioni HTTPS;
  # il programma lo usa automaticamente se presente (vedi _ssl_context).
  echo "Installazione dei certificati SSL (certifi)..."
  "$PY" -m pip install --quiet --upgrade certifi || echo "Attenzione: certifi non installato."
fi

# Avvia il programma in background (&). nohup lo rende indipendente dal
# Terminale, così resta aperto anche dopo la chiusura della finestra del
# Terminale. L'output viene scartato (/dev/null).
nohup "$PY" NasdaqHistoricalDataDownloader.pyw >/dev/null 2>&1 &

# Prova a chiudere la finestra del Terminale aperta dal doppio clic.
# Può non funzionare, a seconda delle impostazioni del Terminale: è solo
# estetica e non influisce sul programma.
osascript -e 'tell application "Terminal" to close (every window whose name contains "LaunchMac")' >/dev/null 2>&1 &
exit 0
