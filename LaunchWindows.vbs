' =============================================================================
' LaunchWindows.vbs - lanciatore di Nasdaq Historical Data Downloader
' =============================================================================
' Perche' un file .vbs (VBScript) e non un .bat:
'   un .bat aprirebbe sempre una finestra nera del Prompt dei comandi.
'   VBScript, eseguito con doppio clic da Windows Script Host (wscript.exe),
'   puo' avviare programmi senza mostrare nessuna finestra.
'
' Cosa fa:
'   1. Cerca un Python installato da python.org (pythonw.exe).
'   2. Se lo trova, avvia NasdaqHistoricalDataDownloader.pyw in modo
'      invisibile (si vede solo la finestra del programma).
'   3. Se non lo trova, chiede all'utente se installarlo; in caso di Si'
'      esegue "Installa Python\installa_python_windows.ps1" e poi ritenta.
'
' pythonw.exe e' la versione di Python che NON apre la console: e' quella
' giusta per i programmi con finestra grafica.
'
' NOTA: questo file deve avere fine riga Windows (CRLF) e solo caratteri
' ASCII (niente lettere accentate), altrimenti wscript.exe puo' leggerlo male.
' =============================================================================

' Obbliga a dichiarare ogni variabile con Dim (evita errori di battitura).
Option Explicit

Dim fso, sh, folder, prog, py
Set fso = CreateObject("Scripting.FileSystemObject")   ' accesso a file e cartelle
Set sh = CreateObject("WScript.Shell")                 ' avvio di programmi, variabili d'ambiente

' Cartella in cui si trova questo .vbs (= cartella del programma).
folder = fso.GetParentFolderName(WScript.ScriptFullName)
' Percorso completo del programma Python da avviare.
prog = folder & "\NasdaqHistoricalDataDownloader.pyw"
' Imposta la cartella di lavoro, per coerenza con il programma.
sh.CurrentDirectory = folder


' -----------------------------------------------------------------------------
' FindPythonw: cerca pythonw.exe nelle cartelle in cui l'installer di
' python.org mette Python:
'   %LOCALAPPDATA%\Programs\Python\Python3xx\   installazione per l'utente
'                                               (quella usata dal nostro script)
'   %ProgramFiles%\Python3xx\                   installazione per tutti gli utenti
'   %ProgramFiles(x86)%\Python3xx\              versioni a 32 bit
' Restituisce il percorso trovato (l'ultimo trovato, se ce ne sono piu'
' d'uno) oppure "" se non trova nulla.
'
' Il "python" del Microsoft Store NON viene usato di proposito: su molti PC
' esiste un finto python.exe che apre lo Store invece di eseguire Python.
' -----------------------------------------------------------------------------
Function FindPythonw()
  Dim bases, b, sub1, cand
  FindPythonw = ""
  bases = Array(sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\Programs\Python"), _
                sh.ExpandEnvironmentStrings("%ProgramFiles%"), _
                sh.ExpandEnvironmentStrings("%ProgramFiles(x86)%"))
  For Each b In bases
    If fso.FolderExists(b) Then
      ' Scorre le sottocartelle e considera solo quelle che iniziano per
      ' "python3" (Python313, Python312, ...).
      For Each sub1 In fso.GetFolder(b).SubFolders
        If LCase(Left(sub1.Name, 7)) = "python3" Then
          cand = sub1.Path & "\pythonw.exe"
          If fso.FileExists(cand) Then FindPythonw = cand
        End If
      Next
    End If
  Next
End Function


' -----------------------------------------------------------------------------
' TryLaunch: prova ad avviare il programma. Restituisce True se ci riesce.
'   1. prima con il pythonw.exe trovato da FindPythonw;
'   2. altrimenti con "pyw -3", il launcher di python.org (copre
'      installazioni in cartelle non standard).
' sh.Run(comando, 0, False):
'   0     = finestra nascosta
'   False = non aspettare la fine del programma
' -----------------------------------------------------------------------------
Function TryLaunch()
  TryLaunch = False
  py = FindPythonw()
  If py <> "" Then
    ' Le doppie virgolette raddoppiate ("""") producono una virgoletta nel
    ' comando: servono perche' i percorsi possono contenere spazi.
    sh.Run """" & py & """ """ & prog & """", 0, False
    TryLaunch = True
    Exit Function
  End If

  ' Se "pyw" non esiste, sh.Run genera un errore: lo intercettiamo invece
  ' di far comparire un messaggio di errore di Windows.
  On Error Resume Next
  sh.Run "pyw -3 """ & prog & """", 0, False
  If Err.Number = 0 Then TryLaunch = True
  Err.Clear
  On Error GoTo 0
End Function


' -----------------------------------------------------------------------------
' Flusso principale
' -----------------------------------------------------------------------------
If Not TryLaunch() Then
  Dim answer, rc

  ' Python non trovato: chiede all'utente (pulsanti Si'/No).
  answer = MsgBox("Python 3 non e' installato su questo computer." & vbCrLf & vbCrLf & _
    "Vuoi scaricarlo e installarlo ora da python.org?" & vbCrLf & _
    "(circa 28 MB, solo per il tuo utente, non servono permessi di amministratore)", _
    vbYesNo + vbQuestion, "Nasdaq Historical Data Downloader")

  If answer = vbYes Then
    ' Esegue lo script PowerShell di installazione:
    '   -NoProfile                non carica le personalizzazioni dell'utente
    '   -ExecutionPolicy Bypass   consente di eseguire questo script, solo per
    '                             questa volta (non modifica le impostazioni)
    '   1, True                   finestra visibile, aspetta che finisca
    ' rc = codice di uscita dello script (0 = installazione riuscita).
    rc = sh.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & _
                folder & "\Installa Python\installa_python_windows.ps1""", 1, True)

    If rc = 0 And TryLaunch() Then
      ' Installato e avviato: niente da fare.
    ElseIf rc = 0 Then
      ' Installato ma non ancora trovato (raro): chiede di riprovare.
      MsgBox "Python e' stato installato. Fai di nuovo doppio clic su 'LaunchWindows'.", 64, "Nasdaq Historical Data Downloader"
    End If
    ' Se rc <> 0 l'errore e' gia' stato mostrato nella finestra di PowerShell.
  End If
End If
