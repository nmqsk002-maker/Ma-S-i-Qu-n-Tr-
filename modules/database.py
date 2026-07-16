# modules/database.py
import sqlite3

DB_FILE = "werewolf.db"

def init_db():
    """Khởi tạo cấu trúc cơ sở dữ liệu nếu chưa tồn tại"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Bảng người chơi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            display_name TEXT,
            elo INTEGER DEFAULT 1000,
            matches_played INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

def register_player(user_id, username, display_name):
    """Đăng ký người chơi mới vào hệ thống nếu họ chưa có tài khoản"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM players WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO players (user_id, username, display_name) VALUES (?, ?, ?)",
            (user_id, username, display_name)
        )
        conn.commit()
    else:
        # Cập nhật lại tên nếu họ có thay đổi trên Telegram
        cursor.execute(
            "UPDATE players SET username = ?, display_name = ? WHERE user_id = ?",
            (username, display_name, user_id)
        )
        conn.commit()
    conn.close()

def get_profile(user_id):
    """Lấy thông tin Profile chi tiết của người chơi"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT elo, matches_played, wins, losses, streak, display_name FROM players WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            "elo": row[0], "matches": row[1], "wins": row[2], 
            "losses": row[3], "streak": row[4], "name": row[5]
        }
    return None

def update_stats(user_id, is_win):
    """Cập nhật điểm Elo, chuỗi thắng, số trận sau khi kết thúc game"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    profile = get_profile(user_id)
    if not profile:
        conn.close()
        return

    new_matches = profile["matches"] + 1
    if is_win:
        new_wins = profile["wins"] + 1
        new_losses = profile["losses"]
        new_elo = profile["elo"] + 15
        new_streak = profile["streak"] + 1
    else:
        new_wins = profile["wins"]
        new_losses = profile["losses"] + 1
        new_elo = max(100, profile["elo"] - 10) # Không để tụt dưới 100 Elo
        new_streak = 0

    cursor.execute('''
        UPDATE players 
        SET matches_played = ?, wins = ?, losses = ?, elo = ?, streak = ? 
        WHERE user_id = ?
    ''', (new_matches, new_wins, new_losses, new_elo, new_streak, user_id))
    conn.commit()
    conn.close()

def get_leaderboard():
    """Lấy danh sách Top 10 người chơi cao điểm nhất"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT display_name, elo FROM players ORDER BY elo DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return rows
