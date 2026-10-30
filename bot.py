#!/usr/bin/env python3
"""Raspberry Pi OS Telegram yönetim botu (sadece Python standart kütüphanesi).

Çalıştırma:  python3 bot.py
(Alternatif: BOT_TOKEN ve CHAT_ID ortam değişkenleri de kullanılabilir.)
"""
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

# ============================================================================
# AYARLAR - SADECE AŞAĞIDAKİ İKİ SATIRI DÜZENLEYİN
# "lütfen bot tokenini buraya yazın" yazısını silip BotFather'dan aldığınız
# token'ı tırnakların içine yazın.
BOT_TOKEN = "lütfen bot tokenini buraya yazın"
# "lütfen telegram chat id buraya yazın" yazısını silip kendi chat id'nizi
# (örn. @userinfobot'tan öğrenilir) tırnakların içine yazın.
CHAT_ID = "lütfen telegram chat id buraya yazın"
# ============================================================================

BOT_TOKEN = os.environ.get("BOT_TOKEN", BOT_TOKEN).strip()
CHAT_ID = os.environ.get("CHAT_ID", CHAT_ID).strip()

SUDO_MARKER = "__SUDO_PAROLA_ISTENDI__"
MAX_MSG = 3900
COMMAND_TIMEOUT = 3600

HELP = """Raspberry Pi OS Yönetim Botu

Herhangi bir düz metin gönderirseniz terminal komutu olarak çalıştırılır
(örn: ls -la, sudo apt update, vcgencmd measure_temp).

Kısayollar:
/status - sistem durumu (sıcaklık, bellek, disk, uptime)
/update - apt update + full-upgrade
/install <paket> - program kur
/remove <paket> - program kaldır
/search <kelime> - paket ara
/reboot - yeniden başlat
/shutdown - kapat
/services - çalışan servisler
/service <start|stop|restart|status|enable|disable> <ad>
/sh <komut> - komut çalıştır
/cancel - çalışan komutu iptal et
/forgetsudo - kayıtlı sudo parolasını sil

sudo parola isterse bot size sorar; parolayı bir sonraki mesajla gönderin
(mesaj sohbetten silinmeye çalışılır, parola yalnızca bellekte tutulur)."""


def api(method, **params):
    data = urllib.parse.urlencode(params).encode()
    url = "https://api.telegram.org/bot%s/%s" % (BOT_TOKEN, method)
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=70) as r:
        return json.load(r)


def send(text):
    text = text if text.strip() else "(boş çıktı)"
    for i in range(0, len(text), MAX_MSG):
        try:
            api("sendMessage", chat_id=CHAT_ID, text=text[i:i + MAX_MSG])
        except Exception as e:
            print("Gönderme hatası:", e, file=sys.stderr)


class Job:
    """Tek seferde bir kabuk komutu çalıştırır; sudo parolasını Telegram'dan alır."""

    def __init__(self, command):
        self.command = command
        self.proc = None
        self.waiting_password = False
        self.thread = threading.Thread(target=self.run, daemon=True)

    def start(self):
        self.thread.start()

    def alive(self):
        return self.thread.is_alive()

    def write_password(self, password):
        try:
            self.proc.stdin.write((password + "\n").encode())
            self.proc.stdin.flush()
        except Exception:
            pass
        self.waiting_password = False

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()

    def run(self):
        global sudo_password
        # sudo'yu stdin'den parola okuyacak şekilde sarmala
        script = ("sudo() { command sudo -S -p '%s' \"$@\"; }\n%s\n"
                  % (SUDO_MARKER, self.command))
        try:
            self.proc = subprocess.Popen(
                ["bash", "-c", script], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"),
                start_new_session=True)
        except Exception as e:
            send("Komut başlatılamadı: %s" % e)
            return
        buf = ""
        last_flush = time.time()
        fd = self.proc.stdout
        prompts = 0
        deadline = time.time() + COMMAND_TIMEOUT
        while True:
            ch = os.read(fd.fileno(), 4096)
            if not ch:
                break
            buf += ch.decode(errors="replace")
            if SUDO_MARKER in buf:
                before, _, buf = buf.partition(SUDO_MARKER)
                if before.strip():
                    send(before)
                prompts += 1
                if sudo_password is not None and prompts == 1:
                    self.write_password(sudo_password)
                else:
                    sudo_password = None
                    self.waiting_password = True
                    send("🔑 sudo parolası gerekli. Lütfen Raspberry Pi parolasını "
                         "bir sonraki mesajda gönderin (iptal: /cancel).")
                    # parola gelene kadar bekle
                    while self.waiting_password and self.proc.poll() is None:
                        time.sleep(0.2)
                continue
            if len(buf) >= MAX_MSG or (buf and time.time() - last_flush > 5):
                send(buf)
                buf = ""
                last_flush = time.time()
            if time.time() > deadline:
                self.cancel()
                buf += "\n(zaman aşımı, komut sonlandırıldı)"
                break
        code = self.proc.wait()
        send((buf + "\n" if buf.strip() else "") + "✅ Bitti (çıkış kodu: %s)" % code)


current_job = None
sudo_password = None


def quote(s):
    import shlex
    return shlex.quote(s)


def shortcut(text):
    """Telegram komutunu kabuk komutuna çevirir; kabuk komutu değilse None."""
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()
    if cmd == "/status":
        return ("echo Host: $(hostname); uptime -p; "
                "vcgencmd measure_temp 2>/dev/null; free -h; df -h /")
    if cmd == "/update":
        return "sudo apt update && sudo apt -y full-upgrade && sudo apt -y autoremove"
    if cmd == "/install" and arg:
        return "sudo apt -y install " + " ".join(quote(a) for a in arg.split())
    if cmd == "/remove" and arg:
        return "sudo apt -y remove " + " ".join(quote(a) for a in arg.split())
    if cmd == "/search" and arg:
        return "apt search " + quote(arg)
    if cmd == "/reboot":
        return "sudo reboot"
    if cmd == "/shutdown":
        return "sudo shutdown -h now"
    if cmd == "/services":
        return "systemctl list-units --type=service --state=running --no-pager"
    if cmd == "/service":
        p = arg.split()
        if len(p) == 2 and p[0] in ("start", "stop", "restart", "status",
                                    "enable", "disable"):
            return "sudo systemctl --no-pager %s %s" % (p[0], quote(p[1]))
        return "echo 'Kullanım: /service <start|stop|restart|status|enable|disable> <ad>'"
    if cmd in ("/install", "/remove", "/search", "/sh") and not arg:
        return "echo 'Kullanım: %s <değer>'" % cmd
    if cmd == "/sh":
        return arg
    return None


def handle(text):
    global current_job, sudo_password
    text = text.strip()
    if not text:
        return
    if current_job and current_job.alive() and current_job.waiting_password:
        if text == "/cancel":
            current_job.cancel()
            send("İptal edildi.")
            return
        sudo_password = text
        current_job.write_password(text)
        return
    if text in ("/start", "/help"):
        send(HELP)
        return
    if text.split("@")[0] == "/forgetsudo":
        sudo_password = None
        send("Kayıtlı sudo parolası silindi.")
        return
    if text.split("@")[0] == "/cancel":
        if current_job and current_job.alive():
            current_job.cancel()
            send("İptal edildi.")
        else:
            send("Çalışan komut yok.")
        return
    if current_job and current_job.alive():
        send("Başka bir komut çalışıyor. Bitmesini bekleyin veya /cancel gönderin.")
        return
    command = shortcut(text) if text.startswith("/") else text
    if command is None:
        send("Bilinmeyen komut. /help yazın.")
        return
    send("▶️ %s" % command)
    current_job = Job(command)
    current_job.start()


def main():
    if "buraya yazın" in BOT_TOKEN or not BOT_TOKEN:
        sys.exit("HATA: bot.py içindeki BOT_TOKEN alanına bot tokeninizi yazın.")
    if "buraya yazın" in CHAT_ID or not CHAT_ID:
        sys.exit("HATA: bot.py içindeki CHAT_ID alanına Telegram chat id'nizi yazın.")
    send("🤖 Raspberry Pi botu çalışıyor. /help yazın.")
    offset = None
    while True:
        try:
            params = {"timeout": 50}
            if offset is not None:
                params["offset"] = offset
            for upd in api("getUpdates", **params).get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message")
                if not msg or str(msg["chat"]["id"]) != CHAT_ID:
                    continue  # yetkisiz kullanıcıları yoksay
                was_waiting = bool(current_job and current_job.alive()
                                   and current_job.waiting_password)
                handle(msg.get("text", ""))
                if was_waiting and msg.get("text", "").strip() != "/cancel":
                    try:
                        api("deleteMessage", chat_id=CHAT_ID,
                            message_id=msg["message_id"])
                    except Exception:
                        pass
        except Exception as e:
            print("Hata:", e, file=sys.stderr)
            time.sleep(5)


if __name__ == "__main__":
    main()
