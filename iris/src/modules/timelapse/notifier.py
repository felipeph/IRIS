import sys
import urllib.request
import subprocess
import threading

DEFAULT_NTFY_TOPIC = "timelapse-studio-2026"

def send_ntfy_notification(topic=DEFAULT_NTFY_TOPIC, title="IRIS Timelapse", message="", tags=None, priority="default", actions=None):
    """Envia uma notificação push via HTTP POST para o ntfy.sh em background."""
    def _do_send():
        url = f"https://ntfy.sh/{topic}"
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
        }
        if tags:
            if isinstance(tags, list):
                headers["Tags"] = ",".join(tags)
            else:
                headers["Tags"] = str(tags)
                
        if actions:
            if isinstance(actions, list):
                headers["Actions"] = "; ".join(actions)
            else:
                headers["Actions"] = str(actions)
                
        try:
            req = urllib.request.Request(
                url,
                data=message.encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=8):
                pass
        except Exception:
            pass

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()

def send_windows_toast(title: str, message: str, app_id: str = "IRIS"):
    """Emite uma notificação Toast nativa no Windows 10/11 via PowerShell WinRT."""
    if sys.platform != "win32":
        return

    def _do_toast():
        safe_title = title.replace('"', '`"').replace("'", "''")
        safe_msg = message.replace('"', '`"').replace("'", "''")
        safe_app = app_id.replace('"', '`"').replace("'", "''")

        ps_script = f"""
        [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
        $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $textNodes = $template.GetElementsByTagName("text")
        $textNodes.Item(0).AppendChild($template.CreateTextNode("{safe_title}")) > $null
        $textNodes.Item(1).AppendChild($template.CreateTextNode("{safe_msg}")) > $null
        $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
        $notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("{safe_app}")
        $notifier.Show($toast)
        """
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5
            )
        except Exception:
            pass

    t = threading.Thread(target=_do_toast, daemon=True)
    t.start()

def notify_timelapse_render_done(project_name: str, video_name: str, details: str = "", topic: str = DEFAULT_NTFY_TOPIC, enable_toast: bool = True):
    """Notifica conclusão da renderização do timelapse 4K."""
    title = "IRIS - Timelapse 4K Renderizado!"
    msg = f"Projeto: {project_name}\nVídeo: {video_name}\n{details}".strip()
    
    if enable_toast:
        send_windows_toast(title, msg)
        
    if topic:
        send_ntfy_notification(
            topic=topic,
            title=f"🎬 {title}",
            message=f"📁 Projeto: {project_name}\n🎞️ Vídeo: {video_name}\n{details}",
            tags=["film_projector", "white_check_mark"],
            priority="high"
        )
