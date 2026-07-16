# modules/night_logic.py
import random
from config import TIME_NIGHT, WEATHER_EFFECTS
from modules.menus import get_action_keyboard, witch_night_keyboard

def start_night_phase(bot, game):
    """Bắt đầu chu kỳ ban đêm: Đổi thời tiết, khóa chat, gửi menu hành động"""
    game.phase = "night"
    
    # 1. Thay đổi thời tiết ngẫu nhiên và thông báo hiệu ứng
    current_weather = game.change_weather()
    weather_desc = WEATHER_EFFECTS[current_weather]
    
    night_announcement = (
        f"🌙 **ĐÊM BUÔNG XUỐNG... MỌI NGƯỜI NHẮM MẮT NGỦ** 🌙\n\n"
        f"🌤️ **Thời tiết đêm nay:** {current_weather}\n"
        f"📝 *Hiệu ứng:* {weather_desc}\n\n"
        f"⏳ Bạn có {TIME_NIGHT} giây để thực hiện các chức năng bí mật qua chat riêng với Bot!"
    )
    
    # Gửi thông báo vào nhóm chung của phòng
    try:
        bot.send_message(game.room_id, night_announcement, parse_mode="Markdown")
    except Exception:
        pass

    # 2. Reset các biến hành động tạm thời của đêm cũ
    game.votes_night = {
        "werewolf": {},  # {sói_id: mục_tiêu}
        "seer": None,    # {mục_tiêu_soi}
        "guard": None    # {mục_tiêu_bảo_vệ}
    }
    game.witch_action_save = False
    game.witch_action_kill = None

    # 3. Quét danh sách người chơi còn sống và gửi menu chức năng qua Chat Riêng (Inbox)
    for p_id, p_info in game.players.items():
        if not p_info["alive"]:
            continue
            
        role = p_info["role"]
        
        try:
            if role in ["Ma Sói", "Sói Nhỏ", "Sói Trắng"]:
                bot.send_message(
                    p_id, 
                    "🐺 **Phe Ma Sói:** Hãy thống nhất chọn 1 nạn nhân để cắn đêm nay:",
                    reply_markup=get_action_keyboard(game, "wolf")
                )
                
            elif role == "Tiên Tri":
                bot.send_message(
                    p_id,
                    "🔮 **Tiên Tri:** Chọn 1 người chơi để soi danh tính bí mật:",
                    reply_markup=get_action_keyboard(game, "seer")
                )
                
            elif role == "Bảo Vệ":
                # Nếu thời tiết là Trăng Tròn, Bảo Vệ không thể tự bảo vệ chính mình (exclude_id=p_id)
                exclude = p_id if game.weather == "Trăng Tròn" else None
                bot.send_message(
                    p_id,
                    "🛡️ **Bảo Vệ:** Chọn 1 người chơi bạn muốn che chở đêm nay:",
                    reply_markup=get_action_keyboard(game, "guard", exclude_id=exclude)
                )
                
            elif role == "Phù Thủy":
                # Logic Phù Thủy sẽ được kích hoạt động sau khi Sói cắn xong, hoặc gửi thông báo chờ
                bot.send_message(p_id, "🧪 **Phù Thủy:** Hãy kiên nhẫn chờ phe Sói hành động...")
                
            elif role == "Kẻ Thâm Độc":
                bot.send_message(
                    p_id,
                    "🦅 **Kẻ Thâm Độc:** Chọn 1 người bạn muốn nguyền rủa (Phiếu bầu của họ ban ngày sẽ vô hiệu):",
                    reply_markup=get_action_keyboard(game, "corrupt")
                )
                
            else:
                # Dân Làng, Già Làng, Thợ Săn, Thằng Hề ngủ ngon
                bot.send_message(p_id, "💤 Bạn không có chức năng ban đêm. Hãy ngủ ngon và cầu nguyện...")
                
        except Exception:
            # Phòng trường hợp người chơi chưa bấm /start với bot riêng
            pass

def process_night_results(game):
    """
    Hàm tính toán kết quả ban đêm dựa trên thứ tự ưu tiên (Tick Rate):
    Bảo Vệ -> Sói cắn -> Phù Thủy tác động -> Tổng hợp nạn nhân cuối cùng
    """
    # 1. Xác định mục tiêu được Bảo Vệ cứu
    protected_id = game.protected_target
    
    # Cập nhật lịch sử bảo vệ để chống trùng đêm sau (luật cơ bản)
    game.last_protected_target = protected_id

    # 2. Xác định mục tiêu bị Sói cắn (Lấy phiếu bầu số đông của phe Sói)
    wolf_votes = list(game.votes_night.get("werewolf", {}).values())
    wolf_victim = None
    if wolf_votes:
        # Tìm phần tử xuất hiện nhiều nhất trong danh sách bầu của Sói
        wolf_victim = max(set(wolf_votes), key=wolf_votes.count)

    # 3. Tính toán kết quả tương tác của Phù Thủy
    final_victim = wolf_victim
    
    # Nếu Sói cắn trúng người được Bảo vệ -> Sói xịt cắn
    if final_victim and final_victim == protected_id:
        final_victim = None
        
    # Nếu Phù Thủy chọn Cứu nạn nhân của Sói
    if game.witch_action_save and game.witch_has_save:
        if wolf_victim == final_victim: # Chỉ cứu được nếu người đó chưa được bảo vệ cứu sẵn
            final_victim = None
            game.witch_has_save = False # Mất bình cứu
            
    # Nếu Phù Thủy chọn Đầu Độc một ai đó bằng bình độc
    if game.witch_action_kill and game.witch_has_kill:
        # Bình độc chết ngay lập tức, không được Bảo vệ hay Già làng cứu
        final_victim = game.witch_action_kill
        game.witch_has_kill = False # Mất bình độc

    # 4. Kiểm tra trường hợp đặc biệt: Già Làng (Elder) có 2 mạng
    if final_victim and game.players[final_victim]["role"] == "Già Làng":
        if game.elder_lives > 1:
            game.elder_lives -= 1
            final_victim = None # Đêm đầu bị cắn thì không chết

    game.victim_tonight = final_victim
    return final_victim

def handle_seer_logic(game, target_id):
    """Xử lý kết quả soi của Tiên Tri tính toán theo hiệu ứng thời tiết"""
    target_role = game.players[target_id]["role"]
    
    # Nếu thời tiết là Sương Mù, Tiên Tri có 30% tỷ lệ nhận kết quả sai lệch ngẫu nhiên
    if game.weather == "Sương Mù" and random.random() < 0.30:
        fake_roles = ["Ma Sói", "Dân Làng", "Phù Thủy"]
        if target_role in fake_roles:
            fake_roles.remove(target_role)
        return random.choice(fake_roles)
        
    # Luật trả kết quả cơ bản: Trả về tên Vai trò cụ thể của mục tiêu
    return target_role
