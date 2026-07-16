# modules/night_logic.py
# modules/night_logic.py
import random
from config import TIME_NIGHT, WEATHER_EFFECTS
from modules.menus import get_action_keyboard

def start_night_phase(bot, game):
    """Bắt đầu chu kỳ ban đêm: Đổi thời tiết, khóa chat, gửi menu hành động"""
    game.phase = "night"
    current_weather = game.change_weather()
    weather_desc = WEATHER_EFFECTS[current_weather]
    
    night_announcement = (
        f"🌙 **ĐÊM BUÔNG XUỐNG... MỌI NGƯỜI NHẮM MẮT NGỦ** 🌙\n\n"
        f"🌤️ **Thời tiết đêm nay:** {current_weather}\n"
        f"📝 *Hiệu ứng:* {weather_desc}\n\n"
        f"⏳ Bạn có {TIME_NIGHT} giây để thực hiện các chức năng bí mật qua chat riêng với Bot!"
    )
    try: bot.send_message(game.room_id, night_announcement, parse_mode="Markdown")
    except: pass

    # Đồng bộ cấu trúc lưu phiếu bầu ban đêm chuẩn dict
    game.votes_night = {
        "werewolf": {},  # {sói_id: mục_tiêu_id}
        "seer": None,
        "guard": None,
        "corrupt": None
    }
    game.protected_target = None
    game.witch_action_save = False
    game.witch_action_kill = None

    for p_id, p_info in game.players.items():
        if not p_info["alive"]: continue
        role = p_info["role"]
        
        try:
            if role in ["Ma Sói", "Sói Nhỏ", "Sói Trắng"]:
                # Bật cờ is_wolf_action=True để lọc danh sách, Sói không nhìn thấy đồng đội để cắn
                bot.send_message(
                    p_id, "🐺 **Phe Ma Sói:** Hãy chọn 1 nạn nhân dân làng để cắn đêm nay:",
                    reply_markup=get_action_keyboard(game, "wolf", is_wolf_action=True)
                )
            elif role == "Tiên Tri":
                bot.send_message(p_id, "🔮 **Tiên Tri:** Chọn 1 người chơi để soi danh tính bí mật:", reply_markup=get_action_keyboard(game, "seer"))
            elif role == "Bảo Vệ":
                exclude = p_id if game.weather == "Trăng Tròn" else None
                bot.send_message(p_id, "🛡️ **Bảo Vệ:** Chọn 1 người chơi bạn muốn che chở đêm nay:", reply_markup=get_action_keyboard(game, "guard", exclude_id=exclude))
            elif role == "Kẻ Thâm Độc":
                bot.send_message(p_id, "🦅 **Kẻ Thâm Độc:** Chọn 1 người bạn muốn nguyền rủa:", reply_markup=get_action_keyboard(game, "corrupt"))
            elif role == "Phù Thủy":
                bot.send_message(p_id, "🧪 **Phù Thủy:** Hãy kiên nhẫn chờ phe Sói hành động...")
            else:
                bot.send_message(p_id, "💤 Bạn không có chức năng ban đêm. Hãy ngủ ngon và cầu nguyện...")
        except: pass

def process_night_results(game):
    """Tính toán kết quả ban đêm: Sửa hàm tìm phần tử số đông an toàn chống kẹt luồng"""
    protected_id = game.protected_target
    game.last_protected_target = protected_id

    # Sửa lỗi đếm phiếu Sói: Lấy toàn bộ giá trị mục tiêu từ dict ra ép kiểu thành list
    wolf_votes = list(game.votes_night.get("werewolf", {}).values())
    wolf_victim = None
    
    if wolf_votes:
        # Đếm số lần xuất hiện của từng mục tiêu và lấy người bị vote nhiều nhất
        wolf_victim = max(set(wolf_votes), key=wolf_votes.count)
    else:
        # Nếu phe Sói treo máy không vote, tự động chọn ngẫu nhiên 1 người phe Dân còn sống để tránh kẹt game
        alive_villagers = [p_id for p_id, p_info in game.players.items() if p_info["alive"] and p_info["role"] not in ["Ma Sói", "Sói Nhỏ", "Sói Trắng"]]
        if alive_villagers:
            wolf_victim = random.choice(alive_villagers)

    final_victim = wolf_victim
    if final_victim and final_victim == protected_id:
        final_victim = None
        
    if game.witch_action_save and game.witch_has_save:
        if wolf_victim == final_victim:
            final_victim = None
            game.witch_has_save = False
            
    if game.witch_action_kill and game.witch_has_kill:
        final_victim = game.witch_action_kill
        game.witch_has_kill = False

    if final_victim and game.players[final_victim]["role"] == "Già Làng":
        if game.elder_lives > 1:
            game.elder_lives -= 1
            final_victim = None

    game.victim_tonight = final_victim
    return final_victim

def handle_seer_logic(game, target_id):
    target_role = game.players[target_id]["role"]
    if game.weather == "Sương Mù" and random.random() < 0.30:
        fake_roles = ["Ma Sói", "Dân Làng", "Phù Thủy"]
        if target_role in fake_roles: fake_roles.remove(target_role)
        return random.choice(fake_roles)
    return target_role
