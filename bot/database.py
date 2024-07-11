import sqlite3

db = sqlite3.connect("data/video-downloader.db")
cr = db.cursor()


def init_db():
    cr.execute(
        "CREATE TABLE IF NOT EXISTS downloads \
        (file_id VARCHAR(100), \
        media_id VARCHAR(100), \
        media_format VARCHAR(30))"
    )
    db.commit()
