# =============================================================================
# installa_python_windows.ps1
# Scarica e installa Python da python.org, solo per l'utente corrente.
# =============================================================================
# Viene lanciato da "LaunchWindows.vbs" quando Python non e' presente.
# Si puo' anche eseguire a mano (tasto destro > "Esegui con PowerShell").
#
# Passi:
#   1. riconosce l'architettura del PC (Intel/AMD a 64 bit oppure ARM64);
#   2. scarica l'installer ufficiale nella cartella temporanea (%TEMP%);
#   3. confronta il checksum SHA-256 con quello pubblicato su python.org:
#      se non coincide, il file viene cancellato e non si installa nulla;
#   4. esegue l'installer in modalita' silenziosa, senza permessi di
#      amministratore;
#   5. cancella l'installer scaricato.
#
# Codice di uscita: 0 = riuscito, 1 = errore (lo legge il .vbs).
#
# PER AGGIORNARE LA VERSIONE DI PYTHON:
#   cambia $ver e i due checksum in $hashes, copiandoli dalla pagina
#   https://www.python.org/downloads/release/python-XXXXX/ (sezione "Files").
#
# NOTA: file volutamente solo ASCII (niente accenti). Windows PowerShell 5.1
# legge i file senza BOM con la codifica locale e storpierebbe gli accenti.
# =============================================================================

# Qualsiasi errore interrompe lo script e passa al blocco "catch".
$ErrorActionPreference = 'Stop'

# Versione da installare e checksum SHA-256 ufficiali degli installer.
$ver = '3.13.16'
$hashes = @{
  'amd64' = 'fb4f9f5d438b2396da0086dc70b935c530cb578e37adc6d354f7ad2037fee83b'
  'arm64' = '696e2226062c6ec3622c13f143d28336a856968518e49cb4f4c62513215a4f5d'
}

try {
  # --- 1) architettura --------------------------------------------------------
  if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { $arch = 'arm64' } else { $arch = 'amd64' }
  $url  = "https://www.python.org/ftp/python/$ver/python-$ver-$arch.exe"
  $dest = Join-Path $env:TEMP "python-$ver-$arch.exe"

  # --- 2) download ------------------------------------------------------------
  Write-Host "Download di Python $ver ($arch) da python.org (circa 28 MB)..."
  # Forza TLS 1.2: le versioni vecchie di Windows PowerShell potrebbero
  # proporre protocolli che python.org non accetta piu'.
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  # Nasconde la barra di avanzamento di Invoke-WebRequest: in PowerShell 5.1
  # rallenta il download in modo enorme.
  $ProgressPreference = 'SilentlyContinue'
  Invoke-WebRequest -Uri $url -OutFile $dest -UseBasicParsing

  # --- 3) verifica integrita' -------------------------------------------------
  Write-Host "Verifica del checksum SHA-256..."
  $h = (Get-FileHash -Path $dest -Algorithm SHA256).Hash.ToLower()
  if ($h -ne $hashes[$arch]) {
    Remove-Item $dest -ErrorAction SilentlyContinue
    throw "Checksum non corrispondente: il file scaricato non e' quello atteso. Installazione annullata."
  }

  # --- 4) installazione silenziosa --------------------------------------------
  # Opzioni documentate dell'installer di python.org:
  #   /quiet                     nessuna finestra
  #   InstallAllUsers=0          solo per l'utente corrente (niente admin)
  #   PrependPath=1              aggiunge Python al PATH dell'utente
  #   Include_launcher=1         installa il launcher "py"/"pyw"
  #   InstallLauncherAllUsers=0  launcher solo per l'utente (niente admin)
  #   Include_tcltk=1            include tkinter (necessario per la finestra)
  #   Include_test=0             salta la suite di test di Python (spazio)
  Write-Host "Installazione in corso (1-2 minuti, nessuna finestra)..."
  $instArgs = @('/quiet', 'InstallAllUsers=0', 'PrependPath=1', 'Include_launcher=1',
            'InstallLauncherAllUsers=0', 'Include_tcltk=1', 'Include_test=0')
  # -Wait aspetta la fine dell'installer; -PassThru restituisce il processo,
  # da cui si legge il codice di uscita (0 = riuscito).
  $p = Start-Process -FilePath $dest -ArgumentList $instArgs -Wait -PassThru

  # --- 5) pulizia -------------------------------------------------------------
  Remove-Item $dest -ErrorAction SilentlyContinue
  if ($p.ExitCode -ne 0) { throw "L'installer di Python ha restituito il codice $($p.ExitCode)." }

  Write-Host ""
  Write-Host "Python $ver installato correttamente."
  exit 0
}
catch {
  # Mostra l'errore e lascia la finestra aperta finche' l'utente non preme Invio,
  # altrimenti si chiuderebbe prima di poter leggere il messaggio.
  Write-Host ""
  Write-Host "ERRORE: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "In alternativa installa Python a mano da https://www.python.org/downloads/"
  Read-Host "Premi Invio per chiudere"
  exit 1
}
