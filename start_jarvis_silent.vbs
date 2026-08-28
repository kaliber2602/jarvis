Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\ADMIN\Downloads\jarvis-main\jarvis-main"
WshShell.Run """C:\Users\ADMIN\AppData\Local\Programs\Python\Python312\pythonw.exe"" jarvis.py", 0, False
