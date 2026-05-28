import os
import re
import sys
import sqlite3

import isodate
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackContext,
    CallbackQueryHandler,
)


# --- VERİTABANI YÖNETİCİSİ SINIFI ---
class VeritabaniYonetici:
    """
    Veritabanı bağlantısı ve YouTube ile ilgili
    veri yazma/okuma işlemlerini yönetir.
    """

    def __init__(self, db_dosyasi="kocluk.db"):
        self.db_dosyasi = db_dosyasi
        self.tablolari_olustur_ve_guncelle()

    def _connect(self):
        conn = sqlite3.connect(self.db_dosyasi)
        conn.row_factory = sqlite3.Row
        return conn

    def _create_all_tables(self, cursor):
        """Tüm tabloları doğru şema ile oluşturur."""

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Dersler (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Title TEXT NOT NULL UNIQUE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS OynatmaListeleri (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Title TEXT NOT NULL,
                PlaylistYoutubeID TEXT UNIQUE,
                DersID INTEGER,
                SinavTipi TEXT,
                FOREIGN KEY (DersID) REFERENCES Dersler (Id)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS Videolar (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Title TEXT,
                Link TEXT,
                Sure_dk INTEGER,
                SiraNo INTEGER,
                VideoID TEXT NOT NULL,
                OynatmaListesiID INTEGER,
                FOREIGN KEY (OynatmaListesiID)
                    REFERENCES OynatmaListeleri (Id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS KayitliPlaylistler (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                PlaylistID TEXT NOT NULL UNIQUE,
                SinavTipi TEXT NOT NULL,
                PlaylistTitle TEXT
            )
            """
        )

    def tablolari_olustur_ve_guncelle(self):
        conn = self._connect()
        cursor = conn.cursor()

        # --- OynatmaListeleri Şema Geçiş Kontrolü ---
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='OynatmaListeleri'
            """
        )

        if cursor.fetchone():
            cursor.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type='table' AND name='OynatmaListeleri'
                """
            )

            schema_sql = cursor.fetchone()["sql"]
            normalized_sql = re.sub(r"\s+", " ", schema_sql).upper()

            if (
                "TITLE TEXT NOT NULL UNIQUE" in normalized_sql
                or "TITLE TEXT UNIQUE" in normalized_sql
            ):
                print("Eski 'OynatmaListeleri' şeması algılandı, otomatik düzeltme yapılıyor...")

                try:
                    cursor.execute("ALTER TABLE OynatmaListeleri RENAME TO OynatmaListeleri_old")

                    self._create_all_tables(cursor)

                    cursor.execute(
                        """
                        INSERT INTO OynatmaListeleri
                            (Id, Title, DersID, SinavTipi)
                        SELECT
                            Id, Title, DersID, SinavTipi
                        FROM OynatmaListeleri_old
                        """
                    )

                    cursor.execute(
                        """
                        UPDATE OynatmaListeleri
                        SET PlaylistYoutubeID = (
                            SELECT PlaylistID
                            FROM KayitliPlaylistler
                            WHERE OynatmaListeleri.Title =
                                SUBSTR(
                                    KayitliPlaylistler.PlaylistTitle,
                                    1,
                                    LENGTH(OynatmaListeleri.Title)
                                )
                        )
                        WHERE PlaylistYoutubeID IS NULL
                        """
                    )

                    cursor.execute("DROP TABLE OynatmaListeleri_old")
                    conn.commit()

                    print("'OynatmaListeleri' şeması başarıyla güncellendi.")

                except Exception as e:
                    print(f"Veritabanı güncellemesi sırasında hata: {e}")
                    conn.rollback()

        # --- Videolar Şema Geçiş Kontrolü ---
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='Videolar'
            """
        )

        if cursor.fetchone():
            cursor.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type='table' AND name='Videolar'
                """
            )

            schema_sql = cursor.fetchone()["sql"]
            normalized_sql = re.sub(r"\s+", " ", schema_sql).upper()

            if "VIDEOID TEXT NOT NULL UNIQUE" in normalized_sql:
                print("Eski 'Videolar' şeması algılandı, otomatik düzeltme yapılıyor...")

                try:
                    cursor.execute("ALTER TABLE Videolar RENAME TO Videolar_old")

                    self._create_all_tables(cursor)

                    cursor.execute(
                        """
                        INSERT INTO Videolar
                        SELECT *
                        FROM Videolar_old
                        """
                    )

                    cursor.execute("DROP TABLE Videolar_old")
                    conn.commit()

                    print("'Videolar' şeması başarıyla güncellendi.")

                except Exception as e:
                    print(f"Veritabanı güncellemesi sırasında hata: {e}")
                    conn.rollback()

        self._create_all_tables(cursor)

        cursor.execute("PRAGMA table_info(KayitliPlaylistler)")
        columns_ref = {info["name"] for info in cursor.fetchall()}

        if "PlaylistTitle" not in columns_ref:
            cursor.execute("ALTER TABLE KayitliPlaylistler ADD COLUMN PlaylistTitle TEXT")

        conn.commit()
        conn.close()

    def add_kayitli_playlist(self, pl_id, tip, title):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO KayitliPlaylistler
                (PlaylistID, SinavTipi, PlaylistTitle)
            VALUES (?, ?, ?)
            ON CONFLICT(PlaylistID)
            DO UPDATE SET
                SinavTipi = excluded.SinavTipi,
                PlaylistTitle = excluded.PlaylistTitle
            """,
            (pl_id, tip, title),
        )

        conn.commit()
        conn.close()

        return cursor.rowcount > 0

    def get_all_kayitli_playlists(self):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT
                Id,
                PlaylistTitle,
                SinavTipi,
                PlaylistID
            FROM KayitliPlaylistler
            ORDER BY PlaylistTitle
            """
        )

        playlists = cursor.fetchall()
        conn.close()

        return playlists

    def delete_kayitli_playlist_by_id(self, kayitli_playlist_id):
        conn = self._connect()
        cursor = conn.cursor()

        try:
            cursor.execute(
                """
                SELECT PlaylistID
                FROM KayitliPlaylistler
                WHERE Id = ?
                """,
                (kayitli_playlist_id,),
            )

            kayit = cursor.fetchone()

            if not kayit:
                return

            playlist_youtube_id_to_delete = kayit["PlaylistID"]

            cursor.execute(
                """
                SELECT Id
                FROM OynatmaListeleri
                WHERE PlaylistYoutubeID = ?
                """,
                (playlist_youtube_id_to_delete,),
            )

            oynatma_listesi = cursor.fetchone()

            if oynatma_listesi:
                cursor.execute(
                    """
                    DELETE FROM OynatmaListeleri
                    WHERE Id = ?
                    """,
                    (oynatma_listesi["Id"],),
                )

            cursor.execute(
                """
                DELETE FROM KayitliPlaylistler
                WHERE Id = ?
                """,
                (kayitli_playlist_id,),
            )

            conn.commit()

            print(
                f"'{playlist_youtube_id_to_delete}' ID'li playlist "
                "ve ilişkili tüm veriler başarıyla silindi."
            )

        except sqlite3.Error as e:
            print(f"Veritabanı silme hatası: {e}")
            conn.rollback()

        finally:
            conn.close()

    def get_or_create_ders_id(self, ders_title):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT Id
            FROM Dersler
            WHERE Title = ?
            """,
            (ders_title,),
        )

        result = cursor.fetchone()

        if result:
            conn.close()
            return result["Id"]

        cursor.execute(
            """
            INSERT OR IGNORE INTO Dersler (Title)
            VALUES (?)
            """,
            (ders_title,),
        )

        new_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return new_id

    def update_or_create_playlist(
        self,
        playlist_youtube_id,
        playlist_title,
        ders_id,
        sinav_tipi,
    ):
        conn = self._connect()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT Id
            FROM OynatmaListeleri
            WHERE PlaylistYoutubeID = ?
            """,
            (playlist_youtube_id,),
        )

        result = cursor.fetchone()

        if result:
            playlist_id = result["Id"]

            cursor.execute(
                """
                UPDATE OynatmaListeleri
                SET
                    Title = ?,
                    DersID = ?,
                    SinavTipi = ?
                WHERE Id = ?
                """,
                (playlist_title, ders_id, sinav_tipi, playlist_id),
            )

            print(f"'{playlist_title}' listesinin bilgileri güncellendi.")

        else:
            cursor.execute(
                """
                INSERT INTO OynatmaListeleri
                    (PlaylistYoutubeID, Title, DersID, SinavTipi)
                VALUES (?, ?, ?, ?)
                """,
                (playlist_youtube_id, playlist_title, ders_id, sinav_tipi),
            )

            playlist_id = cursor.lastrowid

            print(f"'{playlist_title}' listesi veritabanına eklendi.")

        conn.commit()
        conn.close()

        return playlist_id

    def add_video_batch(self, video_list):
        if not video_list:
            return

        conn = self._connect()
        cursor = conn.cursor()

        cursor.executemany(
            """
            INSERT INTO Videolar
                (Title, Link, Sure_dk, SiraNo, VideoID, OynatmaListesiID)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    v["Title"],
                    v["Link"],
                    v["Sure_dk"],
                    v["SiraNo"],
                    v["VideoID"],
                    v["OynatmaListesiID"],
                )
                for v in video_list
            ],
        )

        conn.commit()
        conn.close()


class YouTubeEntegrasyonu:
    def __init__(self, db, api_key):
        self.db = db
        self.api_key = api_key

        if not self.api_key:
            raise ValueError("YouTube API anahtarı .env dosyasında bulunamadı!")

        self.youtube = build("youtube", "v3", developerKey=self.api_key)

    def parse_duration(self, duration_str):
        return int(isodate.parse_duration(duration_str).total_seconds() / 60)

    def find_lesson_for_playlist(self, playlist_title):
        ders_eslesmeleri = {
            "Matematik": ["matematik", "problem", "problemler"],
            "Fizik": ["fizik"],
            "Kimya": ["kimya"],
            "Biyoloji": ["biyoloji"],
            "Türkçe": ["türkçe", "edebiyat"],
            "Tarih": ["tarih"],
            "Coğrafya": ["coğrafya"],
            "Geometri": ["geometri"],
        }

        playlist_title_lower = playlist_title.lower()

        for ders, anahtar_kelimeler in ders_eslesmeleri.items():
            if any(kelime in playlist_title_lower for kelime in anahtar_kelimeler):
                return ders

        return None

    def get_playlist_details(self, playlist_id):
        try:
            playlist_request = self.youtube.playlists().list(
                part="snippet",
                id=playlist_id,
            )

            playlist_response = playlist_request.execute()

            if playlist_response.get("items"):
                snippet = playlist_response["items"][0]["snippet"]

                return {
                    "title": snippet["title"],
                    "channelTitle": snippet["channelTitle"],
                }

            return None

        except HttpError as e:
            print(f"YouTube API hatası: {e}")
            return None

        except Exception as e:
            print(f"Playlist detayları alınırken genel hata: {e}")
            return None

    def process_single_playlist(self, playlist_youtube_id, sinav_tipi, ders_adi):
        try:
            details = self.get_playlist_details(playlist_youtube_id)

            if not details:
                return {
                    "success": False,
                    "message": (
                        f"HATA: '{playlist_youtube_id}' ID'li oynatma listesi "
                        "bulunamadı veya gizli."
                    ),
                }

            playlist_title = details["title"]
            channel_title = details["channelTitle"]
            full_title = f"{playlist_title} | {channel_title}"

            ders_id = self.db.get_or_create_ders_id(ders_adi)

            db_playlist_id = self.db.update_or_create_playlist(
                playlist_youtube_id,
                full_title,
                ders_id,
                sinav_tipi,
            )

            conn = self.db._connect()
            cursor = conn.cursor()

            cursor.execute(
                """
                DELETE FROM Videolar
                WHERE OynatmaListesiID = ?
                """,
                (db_playlist_id,),
            )

            conn.commit()
            conn.close()

            videos_to_add = []
            next_page_token = None

            while True:
                playlist_items_request = self.youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_youtube_id,
                    maxResults=50,
                    pageToken=next_page_token,
                )

                playlist_items_response = playlist_items_request.execute()

                valid_items = [
                    item
                    for item in playlist_items_response.get("items", [])
                    if item["snippet"]["title"] not in ["Private video", "Deleted video"]
                ]

                if not valid_items:
                    break

                video_ids = [
                    item["contentDetails"]["videoId"]
                    for item in valid_items
                ]

                videos_request = self.youtube.videos().list(
                    part="contentDetails",
                    id=",".join(video_ids),
                )

                videos_response = videos_request.execute()

                durations = {
                    item["id"]: self.parse_duration(
                        item["contentDetails"]["duration"]
                    )
                    for item in videos_response.get("items", [])
                }

                for item in valid_items:
                    video_id = item["contentDetails"]["videoId"]

                    video_info = {
                        "Title": item["snippet"]["title"],
                        "Link": f"https://www.youtube.com/watch?v={video_id}",
                        "Sure_dk": durations.get(video_id, 0),
                        "SiraNo": item["snippet"]["position"],
                        "VideoID": video_id,
                        "OynatmaListesiID": db_playlist_id,
                    }

                    videos_to_add.append(video_info)

                next_page_token = playlist_items_response.get("nextPageToken")

                if not next_page_token:
                    break

            self.db.add_video_batch(videos_to_add)

            return {
                "success": True,
                "title": full_title,
                "ders": ders_adi,
                "video_count": len(videos_to_add),
            }

        except HttpError as e:
            return {
                "success": False,
                "message": f"Bir HTTP hatası oluştu: {e}",
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Genel bir hata oluştu: {e}",
            }


# --- TELEGRAM BOTU ---
db_yonetici = VeritabaniYonetici()
yt_entegrasyon = None


def extract_playlist_id(url):
    regex = r"(?:https?:\/\/)?(?:www\.)?youtube\.com\/playlist\?list=([a-zA-Z0-9_-]+)"
    match = re.search(regex, url)

    return match.group(1) if match else None


async def start(update: Update, context: CallbackContext):
    help_text = (
        "Merhaba! Ben Koçluk Paneli YouTube Botu.\n\n"
        "🔹 Bana bir YouTube oynatma listesi linki göndererek veritabanına ekleyebilirsiniz.\n"
        "🔹 /listele komutuyla kayıtlı tüm playlistleri görebilirsiniz.\n"
        "🔹 /sil komutuyla bir playlisti kayıtlardan silebilirsiniz."
    )

    await update.message.reply_text(help_text)


async def listele_command(update: Update, context: CallbackContext):
    playlists = db_yonetici.get_all_kayitli_playlists()

    if not playlists:
        await update.message.reply_text("Veritabanında kayıtlı oynatma listesi bulunmuyor.")
        return

    message_parts = ["📋 Kayıtlı Oynatma Listeleri:\n"]

    for pl in playlists:
        title = pl["PlaylistTitle"] if pl["PlaylistTitle"] else f"ID: {pl['PlaylistID']}"
        message_parts.append(f"- {title} ({pl['SinavTipi']})")

    await update.message.reply_text("\n".join(message_parts))


async def sil_command(update: Update, context: CallbackContext):
    playlists = db_yonetici.get_all_kayitli_playlists()

    if not playlists:
        await update.message.reply_text("Silinecek oynatma listesi bulunmuyor.")
        return

    keyboard = []

    for pl in playlists:
        title = pl["PlaylistTitle"] if pl["PlaylistTitle"] else pl["PlaylistID"]
        display_text = (title[:40] + "..") if len(title) > 40 else title

        keyboard.append(
            [
                InlineKeyboardButton(
                    f"❌ {display_text} ({pl['SinavTipi']})",
                    callback_data=f"delete|{pl['Id']}",
                )
            ]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Hangi oynatma listesini silmek istersiniz?",
        reply_markup=reply_markup,
    )


async def handle_message(update: Update, context: CallbackContext):
    playlist_id = extract_playlist_id(update.message.text)

    if not playlist_id or len(playlist_id) < 15:
        await update.message.reply_text(
            "Bu geçerli bir YouTube oynatma listesi linki değil gibi görünüyor."
        )
        return

    playlist_details = yt_entegrasyon.get_playlist_details(playlist_id)

    if not playlist_details:
        await update.message.reply_text(
            "Bu playlist ID'si ile bir başlık alınamadı. "
            "Linkin doğru olduğundan veya listenin gizli olmadığından emin olun."
        )
        return

    playlist_title = playlist_details["title"]
    ders_adi = yt_entegrasyon.find_lesson_for_playlist(playlist_title)

    if ders_adi:
        keyboard = [
            [
                InlineKeyboardButton(
                    "TYT",
                    callback_data=f"add|{playlist_id}|{ders_adi}|TYT",
                )
            ],
            [
                InlineKeyboardButton(
                    "AYT",
                    callback_data=f"add|{playlist_id}|{ders_adi}|AYT",
                )
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"'{playlist_title}' listesi '{ders_adi}' dersi olarak algılandı.\n\n"
            "Hangi sınav türü için eklensin?",
            reply_markup=reply_markup,
        )

    else:
        dersler = [
            "Matematik",
            "Geometri",
            "Fizik",
            "Kimya",
            "Biyoloji",
            "Türkçe",
            "Tarih",
            "Coğrafya",
        ]

        keyboard = []

        for ders in dersler:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        ders,
                        callback_data=f"ders|{playlist_id}|{ders}",
                    )
                ]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"'{playlist_title}' listesinin dersi otomatik bulunamadı.\n\n"
            "Lütfen aşağıdaki derslerden birini seçin:",
            reply_markup=reply_markup,
        )


async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    action = data[0]

    if action == "ders":
        playlist_id = data[1]
        ders_adi = data[2]

        keyboard = [
            [
                InlineKeyboardButton(
                    "TYT",
                    callback_data=f"add|{playlist_id}|{ders_adi}|TYT",
                )
            ],
            [
                InlineKeyboardButton(
                    "AYT",
                    callback_data=f"add|{playlist_id}|{ders_adi}|AYT",
                )
            ],
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            text=f"'{ders_adi}' dersi seçildi.\n\nHangi sınav türü için eklensin?",
            reply_markup=reply_markup,
        )

    elif action == "add":
        if len(data) < 4:
            await query.edit_message_text(
                text="Hata: Eksik bilgi. Lütfen işlemi tekrar başlatın."
            )
            return

        playlist_id = data[1]
        ders_adi = data[2]
        sinav_tipi = data[3]

        playlist_details = yt_entegrasyon.get_playlist_details(playlist_id)

        if not playlist_details:
            await query.edit_message_text(
                text=(
                    f"HATA: {playlist_id} ID'li playlist başlığı alınamadı. "
                    "Linki, playlist'in gizli olmadığını veya API anahtarınızı kontrol edin."
                )
            )
            return

        playlist_title = playlist_details["title"]
        channel_title = playlist_details["channelTitle"]
        full_title = f"{playlist_title} | {channel_title}"

        await query.edit_message_text(
            text=(
                f"'{playlist_title}' listesi işleniyor...\n\n"
                "Bu işlem playlist'in uzunluğuna göre birkaç dakika sürebilir."
            )
        )

        db_yonetici.add_kayitli_playlist(
            playlist_id,
            sinav_tipi,
            full_title,
        )

        result = yt_entegrasyon.process_single_playlist(
            playlist_id,
            sinav_tipi,
            ders_adi,
        )

        if result["success"]:
            result_message = (
                "✅ Başarılı!\n\n"
                f"📖 Liste: {result['title']}\n"
                f"📚 Ders: {result['ders']}\n"
                f"📹 Video Sayısı: {result['video_count']}\n\n"
                "Veritabanına eklendi."
            )
        else:
            result_message = f"❌ HATA!\n\n{result['message']}"

        await query.edit_message_text(text=result_message)

    elif action == "delete":
        kayitli_playlist_id = data[1]

        db_yonetici.delete_kayitli_playlist_by_id(kayitli_playlist_id)

        await query.edit_message_text(
            text="✅ Playlist ve tüm videoları veritabanından başarıyla silindi."
        )


def main():
    global yt_entegrasyon

    load_dotenv()

    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
    youtube_api_key = os.getenv("YOUTUBE_API_KEY")

    if not telegram_token or not youtube_api_key:
        print("HATA: .env dosyasında TELEGRAM_BOT_TOKEN veya YOUTUBE_API_KEY eksik!")
        sys.exit(1)

    yt_entegrasyon = YouTubeEntegrasyonu(
        db_yonetici,
        youtube_api_key,
    )

    app = Application.builder().token(telegram_token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("listele", listele_command))
    app.add_handler(CommandHandler("sil", sil_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_callback))

    print("Bot başlatıldı, komut bekleniyor...")

    app.run_polling()


if __name__ == "__main__":
    main()