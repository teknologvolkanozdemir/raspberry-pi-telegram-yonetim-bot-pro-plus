# raspberry-pi-telegram-yonetim-bot-pro-plus
Raspberry Pi OS işletim sistemli bilgisayarları Telegram üzerinden yönetmenizi sağlayan Python botu. Geliştirilmeye açıktır.

## Kurulum
1. Telegram'da @BotFather ile bot oluşturup **bot token**'ı alın.
2. @userinfobot ile kendi **chat id**'nizi öğrenin.
3. `bot.py` dosyasını açın; en üstteki
   - `BOT_TOKEN = "lütfen bot tokenini buraya yazın"` satırındaki yazıyı silip tokeninizi,
   - `CHAT_ID = "lütfen telegram chat id buraya yazın"` satırındaki yazıyı silip chat id'nizi yazın.
4. Çalıştırın: `python3 bot.py` (ek paket gerekmez).

## Kullanım
Bota yazdığınız her düz metin terminal komutu olarak çalışır (`sudo apt update`, `ls -la` ...). Kısayollar için `/help`.
`sudo` parola isterse bot Telegram'dan parolayı ister; bir sonraki mesajınız parola olarak kullanılır (mesaj silinmeye çalışılır, parola yalnızca bellekte tutulur, `/forgetsudo` ile silinir). Yalnızca ayarlanan chat id'den gelen mesajlar işlenir.
