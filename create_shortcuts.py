import subprocess
import os

def create_shortcuts():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    
    iniciar_bat = os.path.join(current_dir, "iniciar_bot.bat")
    parar_bat = os.path.join(current_dir, "parar_bot.bat")
    
    # PowerShell command to create shortcuts
    # shell32.dll, 76 is a green checkmark/arrow icon
    # shell32.dll, 131 is a red power/stop icon
    ps_script = f"""
    $WshShell = New-Object -ComObject WScript.Shell
    $DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
    
    # Shortcut to start
    $Shortcut = $WshShell.CreateShortcut("$DesktopPath\\Iniciar Bot WhatsApp.lnk")
    $Shortcut.TargetPath = "{iniciar_bat}"
    $Shortcut.WorkingDirectory = "{current_dir}"
    $Shortcut.IconLocation = "shell32.dll,76"
    $Shortcut.Save()
    
    # Shortcut to stop
    $ShortcutStop = $WshShell.CreateShortcut("$DesktopPath\\Parar Bot WhatsApp.lnk")
    $ShortcutStop.TargetPath = "{parar_bat}"
    $ShortcutStop.WorkingDirectory = "{current_dir}"
    $ShortcutStop.IconLocation = "shell32.dll,131"
    $ShortcutStop.Save()
    """
    
    try:
        subprocess.run(["powershell", "-Command", ps_script], check=True)
        print("Atalhos criados com sucesso na Area de Trabalho!")
    except Exception as e:
        print(f"Erro ao criar atalhos: {e}")

if __name__ == "__main__":
    create_shortcuts()
