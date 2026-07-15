# ==========================================
# PHẦN 22: HỆ THỐNG PHẦN THƯỞNG, EXP, CẤP ĐỘ & KẾT THÚC GAME
# ==========================================

def add_exp_and_check_level_up(user_id, exp_gain):
    """Cộng điểm kinh nghiệm cho người chơi và tự động kích hoạt hiệu ứng lên cấp"""
    user_data = user_db[user_id]
    user_data["exp"] += exp_gain
    
    # Công thức tính EXP yêu cầu để lên cấp: Level * 100
    next_level_exp = user_data["level"] * 100
    
    level_up_occurred = False
    while user_data["exp"] >= next_level_exp:
        user_data["exp"] -= next_level_exp
        user_data["level"] += 1
        next_level_exp = user_data["level"] * 100
        level_up_occurred = True
        
    return level_up_occurred

def process_end_of_game_rewards(room_id, winning_team):
    """
    Hàm kết thúc trận đấu:
    - Quyết toán tiền đặt cược của các linh hồn khán giả (Phần 45).
    - Tự động in Nhật ký diễn biến trận đấu ra sảnh chat tổng (Phần 28).
    - Trả tự do, mở lại quyền chat Group cho tất cả mọi người (Phần 41).
    - Đóng gói dữ liệu xuất file JSON lưu cứng lên VPS (Phần 42).
    - Chia đều tổng quỹ cược Vàng và cộng EXP thăng cấp cho những người thắng cuộc.
    - Cuối hàm, quét tự động lật mở Thành Tựu thưởng Vàng lớn (Phần 40).
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    room_data["status"] = "End"
    
    # 📥 ĐỒNG BỘ PHẦN 45: Tự động quyết toán hóa đơn đặt cược của các linh hồn khán giả
    if 'settle_spectator_betting_rewards' in globals():
        settle_spectator_betting_rewards(room_id, winning_team)
    
    # 📥 ĐỒNG BỘ PHẦN 28: Tự động xuất nhật ký trận đấu ra màn hình cho người chơi xem trước khi phòng bị xóa
    if 'generate_and_send_game_log' in globals():
        generate_and_send_game_log(room_id)
        
    # 📥 ĐỒNG BỘ PHẦN 41: Trả lại tự do hoàn toàn cho toàn bộ thành viên (sống + chết) khi trận đấu kết thúc
    if 'lift_all_restrictions_on_game_over' in globals():
        # Giả lập biến nhóm chat chat_id nếu bạn chạy qua phòng chat tổng, mặc định gộp theo host
        lift_all_restrictions_on_game_over(room_id, room_data["host"])
        
    # 📥 ĐỒNG BỘ PHẦN 42: Đóng gói dữ liệu xuất file JSON lịch sử trận đấu lưu cứng lên ổ đĩa
    if 'save_match_history_to_storage' in globals():
        save_match_history_to_storage(room_id)

    total_players = len(room_data["players"])
    bet_fee = room_data["bet"]
    total_prize_pool = total_players * bet_fee
    
    winners = []
    losers = []
    
    for pid in room_data["players"]:
        pdata = room_data["roles"][pid]
        if pdata["team"] == winning_team:
            winners.append(pid)
        else:
            losers.append(pid)
            
    # Thuật toán phân chia tiền vàng thưởng tích hợp Sự Kiện Giờ Vàng (Phần 33)
    gold_reward_per_winner = 0
    multiplier_text = ""
    if winners:
        base_reward = int(total_prize_pool / len(winners))
        # Kiểm tra xem có đang bật sự kiện Giờ Vàng X2 không (Phần 33)
        if globals().get("IS_DOUBLE_GOLD_EVENT", False):
            gold_reward_per_winner = base_reward * 2
            multiplier_text = " 🔥 *(Đã nhân đôi X2 Giờ Vàng)*"
        else:
            gold_reward_per_winner = base_reward
            
        for w_id in winners:
            user_db[w_id]["gold"] += gold_reward_per_winner
            user_db[w_id]["win"] += 1
            
    for l_id in losers:
        user_db[l_id]["lose"] += 1

    end_game_msg = (
        f"👑 **TRẬN ĐẤU KẾT THÚC — PHE {winning_team.upper()} CHIẾN THẮNG** 👑\n"
        f"-----------------------------------------\n"
        f"💰 **Tổng quỹ cược trận đấu:** `{total_prize_pool:,} Vàng`\n"
        f"🎁 **Phần thưởng mỗi người thắng:** `+{gold_reward_per_winner:,} Vàng`{multiplier_text}\n"
        f"-----------------------------------------\n"
        f"🏆 **DANH SÁCH ANH HÙNG CHIẾN THẮNG ({winning_team}):**\n"
    )
    
    for w_id in winners:
        pname = user_db[w_id]["name"]
        prole = room_data["roles"][w_id]["role"]
        level_up = add_exp_and_check_level_up(w_id, 50) # Thắng trận nhận ngay 50 EXP gốc
        lvl_up_text = " 🔥 **LEVEL UP!**" if level_up else ""
        end_game_msg += f"🔹 **{pname}** (Vai trò: `{prole}`){lvl_up_text}\n"
        
        # Cập nhật tiến độ nhiệm vụ hàng ngày 'Thắng 1 trận' (Phần 35)
        if 'update_quest_progress' in globals():
            update_quest_progress(w_id, "q2")
        
    end_game_msg += "\n💀 **DANH SÁCH BẠI TRẬN ĐÁNG TIẾC:**\n"
    for l_id in losers:
        pname = user_db[l_id]["name"]
        prole = room_data["roles"][l_id]["role"]
        level_up = add_exp_and_check_level_up(l_id, 15) # Thua trận nhận khích lệ 15 EXP gốc
        lvl_up_text = " 🔥 **LEVEL UP!**" if level_up else ""
        end_game_msg += f"🔸 **{pname}** (Vai trò: `{prole}`){lvl_up_text}\n"
        
    end_game_msg += (
        f"-----------------------------------------\n"
        f"💬 *Phòng chơi sẽ tự động đóng lại sau vài giây. Hãy sử dụng nút Quay Lại để tiếp tục tìm trận mới!*"
    )

    for pid in room_data["players"]:
        try: bot.send_message(pid, end_game_msg, parse_mode="Markdown")
        except Exception: pass
        
        # Cập nhật tiến độ nhiệm vụ hàng ngày 'Tham gia 2 trận' (Phần 35) cho tất cả mọi người
        if 'update_quest_progress' in globals():
            update_quest_progress(pid, "q1")
            
    room_data["history_log"].append(f"👑 Trận đấu kết thúc. Phe {winning_team} thắng.")

    # 📥 ĐỒNG BỘ PHẦN 40: Cuối trận, tự động quét mở khóa Thành Tựu thưởng Vàng lớn cho người chơi
    if 'scan_and_unlock_user_achievements' in globals():
        for pid in room_data["players"]:
            scan_and_unlock_user_achievements(pid)

    # Giải phóng phòng chơi khỏi bộ nhớ RAM sau 5 giây delay
    def delayed_cleanup():
        time.sleep(5)
        if room_id in game_rooms:
            del game_rooms[room_id]
            
    threading.Thread(target=delayed_cleanup).start()


# ==========================================
# PHẦN 23: TÍNH NĂNG THẦN TÌNH YÊU (CUPID) & LOGIC CHẾT CHÙM VÌ TÌNH
# ==========================================

# Bộ nhớ tạm lưu trữ danh sách Cặp Đôi của từng phòng chơi: { room_id: {"lovers": set([id1, id2]), "cupid_id": id} }
lovers_cache = {}

def get_cupid_selection_markup(room_id, cupid_id, selected_p1=None):
    """Tạo menu nút bấm chọn mục tiêu kết đôi cho Cupid"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    room_data = game_rooms[room_id]
    
    for pid in room_data["players"]:
        if selected_p1 and pid == selected_p1:
            continue
            
        pname = user_db[pid]["name"]
        if not selected_p1:
            cb_data = f"cupid_p1_{room_id}_{pid}"
            btn_text = f"👤 {pname}"
        else:
            cb_data = f"cupid_p2_{room_id}_{selected_p1}_{pid}"
            btn_text = f"💘 Ghép với {pname}"
            
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=cb_data))
        
    return markup

def trigger_cupid_menu(room_id):
    """Hàm tìm kiếm Cupid trong phòng để gửi bảng menu bắn mũi tên tình yêu"""
    room_data = game_rooms[room_id]
    cupid_id = None
    
    for pid in room_data["players"]:
        if room_data["roles"][pid]["role"] == "Thần Tình Yêu (Cupid)":
            cupid_id = pid
            break
            
    if not cupid_id:
        return
        
    cupid_text = (
        "🏹 **MŨI TÊN TÌNH YÊU CUPID KÍCH HOẠT** 🏹\n"
        "-----------------------------------------\n"
        "💘 Là Thần Tình Yêu, bạn có nhiệm vụ ghép đôi cho 2 người chơi bất kỳ trong làng trước khi cuộc chiến bắt đầu.\n\n"
        "👉 **Bước 1:** Hãy lựa chọn **Người thứ nhất** để ban phát tình yêu từ danh sách dưới đây:"
    )
    bot.send_message(cupid_id, cupid_text, parse_mode="Markdown", reply_markup=get_cupid_selection_markup(room_id, cupid_id))

def apply_lovers_heartbreak_death(room_id, current_dead_set):
    """
    Hàm bổ trợ quét dây chuyền tình ái.
    Nếu phát hiện 1 trong 2 người yêu dính trong danh sách chết, cưỡng chế gạt người còn lại chết cùng.
    """
    if room_id not in lovers_cache:
        return current_dead_set
        
    room_lovers = lovers_cache[room_id]["lovers"]
    room_data = game_rooms[room_id]
    
    lovers_list = list(room_lovers)
    if len(lovers_list) < 2:
        return current_dead_set
        
    p1, p2 = lovers_list[0], lovers_list[1]
    
    # Tình huống 1: Người thứ 1 chết, lôi theo người thứ 2
    if p1 in current_dead_set and p2 in room_data["alive"]:
        current_dead_set.add(p2)
        room_data["history_log"].append(f"💖 {user_db[p2]['name']} đã tự sát vì đau buồn khi người tình {user_db[p1]['name']} hy sinh.")
        
    # Tình huống 2: Người thứ 2 chết, lôi theo người thứ 1
    elif p2 in current_dead_set and p1 in room_data["alive"]:
        current_dead_set.add(p1)
        room_data["history_log"].append(f"💖 {user_db[p1]['name']} đã tự sát vì đau buồn khi người tình {user_db[p2]['name']} hy sinh.")
        
    return current_dead_set
