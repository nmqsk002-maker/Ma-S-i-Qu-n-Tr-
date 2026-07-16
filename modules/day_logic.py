# modules/day_logic.py
from collections import Counter
from modules.menus import get_action_keyboard, defense_judgment_keyboard
from modules.database import update_stats

def start_day_phase(bot, game):
    """Bắt đầu buổi sáng: Công bố nạn nhân đêm qua và kiểm tra điều kiện thắng"""
    game.phase = "day_morning"
    
    # Import trực tiếp bên trong hàm để tránh lỗi Circular Import
    import modules.night_logic as nl
    victim_id = nl.process_night_results(game)
    
    announcement = "☀️ **TRỜI SÁNG RỒI! MỌI NGƯỜI THỨC DẬY** ☀️\n\n"
    
    if victim_id and victim_id in game.players:
        game.players[victim_id]["alive"] = False
        v_name = game.players[victim_id]["name"]
        v_role = game.players[victim_id]["role"]
        announcement += f"💀 Đêm qua, một vụ án mạng kinh hoàng đã xảy ra... **{v_name}** ({v_role}) đã tử thương!\n"
        
        # Xử lý dây chuyền: Nếu Thợ Săn chết, cho phép họ kéo theo 1 người
        if v_role == "Thợ Săn" and not game.hunter_fired:
            game.hunter_fired = True
            try:
                bot.send_message(
                    game.room_id, 
                    f"🎯 **💥 KÍCH HOẠT CHỨC NĂNG THỢ SĂN:** {v_name} trước khi chết đã kịp giương súng! "
                    f"Hãy chọn 1 người để bắn hạ trong chat riêng của bạn.",
                )
                bot.send_message(
                    victim_id,
                    "🎯 Bạn đã chết! Chọn 1 mục tiêu để bắn hạ chết cùng bạn:",
                    reply_markup=get_action_keyboard(game, "hunter_shot", exclude_id=victim_id)
                )
            except Exception:
                pass
    else:
        announcement += "😇 Một đêm bình yên kỳ lạ... Không có ai chết cả!\n"
        
    bot.send_message(game.room_id, announcement, parse_mode="Markdown")
    
    # Kiểm tra điều kiện thắng ngay sau khi có người chết ban đêm
    if check_victory(bot, game):
        return

    # Chuyển sang phase thảo luận công khai
    start_discussion_phase(bot, game)

def start_discussion_phase(bot, game):
    """Mở cổng thảo luận ban ngày"""
    game.phase = "day_discuss"
    game.votes_day = {}
    
    msg = (
        "⚖️ **GIAI ĐOẠN THẢO LUẬN BẮT ĐẦU** ⚖️\n\n"
        "Mọi người hãy cùng tranh luận, tìm ra kẻ tình nghi là Ma Sói.\n"
        "Sau đó, gõ lệnh `/vote` hoặc sử dụng menu hệ thống để tiến hành bỏ phiếu treo cổ!"
    )
    bot.send_message(game.room_id, msg, parse_mode="Markdown")

def process_voting_results(bot, game):
    """Tổng hợp phiếu bầu ban ngày, tính điểm ưu tiên và đưa người bị nghi ngờ vào phòng Biện hộ"""
    import modules.night_logic as nl
    if not game.votes_day:
        bot.send_message(game.room_id, "🕊️ Làng yên bình, không ai bỏ phiếu treo cổ ai cả. Đêm tiếp theo bắt đầu!")
        nl.start_night_phase(bot, game)
        return

    # Tính toán số phiếu bầu thực tế có nhân hệ số
    calculated_votes = []
    for voter_id, target_id in game.votes_day.items():
        # Kiểm tra nếu người bầu bị Kẻ Thâm Độc nguyền rủa -> Phiếu vô hiệu
        if game.votes_night.get("corrupt") == voter_id:
            continue
            
        weight = 1
        # Nếu người bầu là Cảnh Sát Trưởng -> Phiếu tính gấp đôi (2 phiếu)
        if game.players[voter_id].get("is_mayor", False):
            weight = 2
            
        for _ in range(weight):
            calculated_votes.append(target_id)

    if not calculated_votes:
        bot.send_message(game.room_id, "🕊️ Không có phiếu bầu nào hợp lệ. Đêm tiếp theo bắt đầu!")
        nl.start_night_phase(bot, game)
        return

    # Tìm người bị vote nhiều nhất
    vote_counts = Counter(calculated_votes)
    top_targets = vote_counts.most_common(2)
    
    # Xử lý Bằng Phiếu (Tie Vote)
    if len(top_targets) > 1 and top_targets[0][1] == top_targets[1][1]:
        bot.send_message(game.room_id, "⚖️ **Số phiếu bằng nhau!** Làng không thống nhất được ai có tội. Không ai bị treo cổ hôm nay.")
        nl.start_night_phase(bot, game)
        return

    punished_id, highest_votes = top_targets[0]
    game.defense_target = punished_id
    game.phase = "day_defense"
    game.judgment_votes = {"guilty": 0, "innocent": 0, "voters": []}
    
    punished_name = game.players[punished_id]["name"]
    
    defense_msg = (
        f"🚨 **PHÒNG BIỆN HỘ LÂM THỜI** 🚨\n\n"
        f"Người dân làng đang hướng sự nghi ngờ vào **{punished_name}** với tổng số tích lũy tương đương {highest_votes} phiếu!\n"
        f"⚠️ **{punished_name}** có thời gian để đưa ra lời biện hộ. Sau đó, cả làng sẽ biểu quyết TREO CỔ hay THA BỔNG qua menu nút bấm dưới đây:"
    )
    bot.send_message(game.room_id, defense_msg, reply_markup=defense_judgment_keyboard(), parse_mode="Markdown")

def execute_hanging(bot, game):
    """Thực thi treo cổ dựa trên kết quả biểu quyết phòng biện hộ"""
    import modules.night_logic as nl
    target_id = game.defense_target
    target_name = game.players[target_id]["name"]
    target_role = game.players[target_id]["role"]
    
    guilty = game.judgment_votes["guilty"]
    innocent = game.judgment_votes["innocent"]
    
    result_text = f"📊 **Kết quả biểu quyết:** 💀 Treo Cổ: {guilty} | 🕊️ Tha Bổng: {innocent}\n\n"
    
    if guilty > innocent:
        game.players[target_id]["alive"] = False
        result_text += f"⚖️ Dân làng quyết định xử tử hình **{target_name}**! Vai trò thật sự của người này là: **{target_role}**.\n"
        
        # Kiểm tra điều kiện thắng độc lập của THẰNG HỀ
        if target_role == "Thằng Hề":
            bot.send_message(game.room_id, f"🃏 **THẰNG HỀ CHIẾN THẮNG ĐƠN ĐỘC!** **{target_name}** là Thằng Hề và đã lừa cả làng treo cổ mình thành công!")
            end_game_cleanup(bot, game, winner_side="Thằng Hề")
            return
            
        # Kiểm tra hiệu ứng dây chuyền nếu Thợ Săn bị treo cổ ban ngày
        if target_role == "Thợ Săn" and not game.hunter_fired:
            game.hunter_fired = True
            bot.send_message(game.room_id, f"🎯 **💥 THỢ SĂN PHẢN SÁT:** {target_name} rút súng bắn trả! Hãy kiểm tra chat riêng.")
            bot.send_message(target_id, "🎯 Chọn 1 mục tiêu để bắn hạ chết cùng bạn:", reply_markup=get_action_keyboard(game, "hunter_shot", exclude_id=target_id))
    else:
        result_text += f"🕊️ Sông có khúc người có lúc, dân làng đã mủi lòng tha bổng cho **{target_name}** khỏi giá treo cổ!\n"
        
    bot.send_message(game.room_id, result_text, parse_mode="Markdown")
    
    # Kiểm tra điều kiện thắng sau khi treo cổ
    if check_victory(bot, game):
        return
        
    # Chuyển sang đêm tiếp theo nếu chưa ai thắng
    nl.start_night_phase(bot, game)

def check_victory(bot, game):
    """Kiểm tra điều kiện thắng cuộc của các phe"""
    wolves = 0
    villagers = 0
    
    for p_id, p_info in game.players.items():
        if p_info["alive"]:
            if p_info["role"] in ["Ma Sói", "Sói Nhỏ", "Sói Trắng"]:
                wolves += 1
            else:
                villagers += 1
                
    if wolves == 0:
        bot.send_message(game.room_id, "🎉 **PHE DÂN LÀNG CHIẾN THẮNG!!!** Tất cả Ma Sói gian ác đã bị thanh trừng hoàn toàn.")
        end_game_cleanup(bot, game, winner_side="Dân Làng")
        return True
    elif wolves >= villagers:
        bot.send_message(game.room_id, "🐺 **PHE MA SÓI CHIẾN THẮNG!!!** Nanh vuốt của Ma Sói đã xé toạc toàn bộ dân làng.")
        end_game_cleanup(bot, game, winner_side="Ma Sói")
        return True
        
    return False

def end_game_cleanup(bot, game, winner_side):
    """Tổng kết trận đấu, cập nhật điểm Elo Elo vào Database và reset phòng"""
    summary = "📋 **DANH SÁCH VAI TRÒ CHUNG CUỘC:**\n"
    
    for p_id, p_info in game.players.items():
        role = p_info["role"]
        status = "🟢 Sống" if p_info["alive"] else "💀 Chết"
        summary += f"- {p_info['name']}: **{role}** ({status})\n"
        
        # Tính toán kết quả thắng/thua để cộng trừ Elo
        is_win = False
        if winner_side == "Dân Làng" and role not in ["Ma Sói", "Sói Nhỏ", "Sói Trắng", "Thằng Hề"]:
            is_win = True
        elif winner_side == "Ma Sói" and role in ["Ma Sói", "Sói Nhỏ", "Sói Trắng"]:
            is_win = True
        elif winner_side == "Thằng Hề" and p_id == game.defense_target:
            is_win = True
            
        # Ghi nhận kết quả vào cơ sở dữ liệu SQLite
        update_stats(p_id, is_win)
        
    bot.send_message(game.room_id, summary, parse_mode="Markdown")
    bot.send_message(game.room_id, "🔄 Phòng đấu đã được dọn dẹp sạch sẽ. Gõ `/start` hoặc bấm nút để mở Lobby mới!")
    game.reset()

