# modules/game_engine.py
import random

class WerewolfGame:
    def __init__(self, room_id):
        self.room_id = room_id
        self.is_active = False
        self.phase = "lobby"  # lobby, night, day_morning, day_discuss, day_vote, day_defense
        self.weather = "Trời Quang"
        
        # Quản lý người chơi: {user_id: {"name": str, "role": str, "alive": bool, "lover": int/None, "is_mayor": bool}}
        self.players = {}
        
        # Dữ liệu tương tác tạm thời trong đêm/ngày
        self.votes_night = {}      # {role_type: {sender_id: target_id}}
        self.votes_day = {}        # {sender_id: target_id}
        self.protected_target = None
        self.last_protected_target = None # Chống bảo vệ 2 đêm liên tiếp
        self.witch_has_save = True
        self.witch_has_kill = True
        self.witch_action_save = False # Đêm nay có cứu không
        self.witch_action_kill = None  # Đêm nay đầu độc ai
        
        self.elder_lives = 2       # Già làng có 2 mạng
        self.hunter_fired = False
        self.victim_tonight = None

    def reset(self):
        self.__init__(self.room_id)

    def change_weather(self):
        """Thay đổi thời tiết ngẫu nhiên mỗi khi đêm xuống"""
        from config import WEATHER_EFFECTS
        self.weather = random.choice(list(WEATHER_EFFECTS.keys()))
        return self.weather

    def add_player(self, user_id, name):
        if user_id in self.players:
            return False, "⚠️ Bạn đã ở trong phòng chờ này rồi!"
        if len(self.players) >= 20:
            return False, "❌ Phòng đã đầy (Tối đa 20 người)!"
        self.players[user_id] = {
            "name": name, "role": None, "alive": True, "lover": None, "is_mayor": False
        }
        return True, f"✅ *{name}* đã tham gia phòng chờ! (Hiện tại: {len(self.players)} người)"

    def remove_player(self, user_id):
        if user_id in self.players:
            name = self.players[user_id]["name"]
            del self.players[user_id]
            return True, f"🚪 *{name}* đã rời khỏi phòng chờ."
        return False, "⚠️ Bạn chưa tham gia phòng chờ này."

    def get_alive_count(self):
        return sum(1 for p in self.players.values() if p["alive"])

    def assign_roles(self):
        """Thuật toán phân phối bài động dựa trên số lượng người tham gia thực tế"""
        p_ids = list(self.players.keys())
        count = len(p_ids)
        
        # Thiết lập cấu trúc bài cơ bản tương ứng với số người chơi
        pool = []
        if count >= 4:
            pool = ["Ma Sói", "Tiên Tri", "Bảo Vệ", "Dân Làng"]
        if count >= 6:
            pool += ["Phù Thủy", "Thợ Săn"]
        if count >= 8:
            pool += ["Sói Nhỏ", "Già Làng"]
        if count >= 10:
            pool += ["Thằng Hề", "Kẻ Thâm Độc"]
            
        # Nếu thiếu bài, bù dân làng vào cho đủ số lượng
        while len(pool) < count:
            pool.append("Dân Làng")
        # Nếu thừa bài (do ít người hơn mức mốc), cắt bớt dân làng hoặc chức năng cuối
        pool = pool[:count]
        
        random.shuffle(pool)
        for i, p_id in enumerate(p_ids):
            self.players[p_id]["role"] = pool[i]

# Hệ thống quản lý đa phòng (Multi-room Engine) toàn cục để bot không bao giờ bị nghẽn luồng
games_manager = {}

def get_game(room_id) -> WerewolfGame:
    if room_id not in games_manager:
        games_manager[room_id] = WerewolfGame(room_id)
    return games_manager[room_id]
