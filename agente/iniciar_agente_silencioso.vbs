' ============================================================
'  ProAutoMax - Lancador silencioso do agente
'  Sobe o iniciar_agente.bat SEM janela de console.
'  Deixe este .vbs NA MESMA PASTA do iniciar_agente.bat.
' ============================================================
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
bat = pasta & "\iniciar_agente.bat"

Set sh = CreateObject("WScript.Shell")
' 0 = janela oculta | False = nao espera terminar
sh.Run "cmd /c """ & bat & """", 0, False