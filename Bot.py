# ==========================================
# PHẦN 16: HỆ THỐNG THẢO LUẬN BAN NGÀY & KÍCH HOẠT LÁ BÀI SỰ KIỆN
# ==========================================

# Định nghĩa Pool thời tiết và các lá bài sự kiện tác động ban ngày
WEATHER_DAY_POOL = {
    "Đẹp Trời": {"icon": "☀️", "time_mod": 1.0, "desc": "Thời tiết lý tưởng. Thời gian thảo luận giữ nguyên chuẩn định mức."},
    "Ngày Mưa Bão": {"icon": "⛈️", "time_mod": 0.5, "desc": "Sấm sét vang trời khiến dân làng hoang mang. Thời gian thảo luận bị rút ngắn 50%!"},
    "Ngày Nắng Hạn": {"icon": "🥵", "time_mod": 1.0, "desc": "Không khí oi bức. Ai dùng kỹ năng đêm qua sẽ bị cấm chat trong 20 giây đầu tiên để hồi sức."}
}

EVENT_CARDS_POOL = [
    {"id": "binh_thuong", "name": "🕊️ Bình Yên", "desc": "Không có sự kiện đặc biệt nào xảy ra trong làng."},
    {"id": "dich_benh", "name": "🦠 Dịch Bệnh", "desc": "Khóa mõm (Mute) ngẫu nhiên 1 người chơi bất kỳ trong làng, họ không thể chat trong ngày hôm nay."},
    {"id": "toa_an", "name": "⚖️ Tòa Án Lương Tâm", "desc": "Ngày hôm nay toàn bộ phiếu bầu khởi tố treo cổ sẽ hiển thị công khai danh tính rõ ràng."}
]

# Bộ nhớ tạm lưu danh sách người chơi bị khóa mõm (Mute) trong ngày của từng phòng chơi
muted_players_today = {}

def start_day_discussion_phase(room_id):
    """
    Khởi động giai đoạn thảo luận công khai ban ngày.
    Tính toán thời tiết, rút lá bài sự kiện và thiết lập bộ đếm thời gian.
    """
    if room_id not in game_rooms or game_rooms[room_id]["status"] != "Day":
        return
        
    room_data = game_rooms[room_id]
    room_data["status"] = "Discussion"
    muted_players_today[room_id] = set()
    
    # 1. Cấu hình hiệu ứng Thời tiết ban ngày
    weather_key = random.choice(list(WEATHER_DAY_POOL.keys()))
    weather_info = WEATHER_DAY_POOL[weather_key]
    
    # 2. Rút Lá bài Sự kiện ngẫu nhiên ban ngày
    event_card = random.choice(EVENT_CARDS_POOL)
    room_data["event_card"] = event_card["id"]
    
    # Tính toán thời gian thảo luận gốc là 90 giây nhân với hệ số thời tiết
    discussion_time = int(90 * weather_info["time_mod"])
    
    # Xử lý hiệu ứng Lá bài Sự kiện: Dịch Bệnh (Mute 1 người ngẫu nhiên)
    muted_text = ""
    if event_card["id"] == "dich_benh" and room_data["alive"]:
        lucky_victim = random.choice(room_data["alive"])
        muted_players_today[room_id].add(lucky_victim)
        muted_text = f"🚨 **Cách ly y tế:** **{user_db[lucky_victim]['name']}** dính vi-rút bệnh lạ, bị **KHÓA MÕM (MUTE)** hoàn toàn trong ngày hôm nay!\n"

    # Xử lý hiệu ứng Thời tiết: Ngày Nắng Hạn (Mute tạm thời những người dùng chiêu đêm qua)
    if weather_key == "Ngày Nắng Hạn":
        for pid in room_data["alive"]:
            if room_data["roles"][pid].get("used_skill_last_night"): 
                muted_players_today[room_id].add(pid)
    
    # 3. Tạo văn bản thông báo sự kiện ban ngày đầy kịch tính
    discussion_msg = (
        f"📣 **GIAI ĐOẠN THẢO LUẬN CHÍNH THỨC** 📣\n"
        f"-----------------------------------------\n"
        f"{weather_info['icon']} **Thời tiết hôm nay:** `{weather_key}`\n"
        f"ℹ️ *Tác động:* _{weather_info['desc']}_\n\n"
        f"🃏 **Lá bài Sự kiện rút được:** **{event_card['name']}**\n"
        f"ℹ️ *Chi tiết:* _{event_card['desc']}_\n"
        f"-----------------------------------------\n"
        f"{muted_text}"
        f"⏳ **Thời gian đếm ngược thảo luận:** `{discussion_time} giây`\n\n"
        f"💬 *Toàn bộ thành viên còn sống hãy tích cực nhắn tin tranh luận để tìm ra kịch sĩ ẩn danh!*"
    )
    
    # Phát sóng thông báo và mở luồng đếm ngược
    for pid in room_data["players"]:
        try:
            bot.send_message(pid, discussion_msg, parse_mode="Markdown")
        except Exception: 
            pass
        
    room_data["history_log"].append(f"☀️ Thảo luận ngày mở. Thời tiết: {weather_key}, Sự kiện: {event_card['name']}")
    
    # Khởi chạy luồng hẹn giờ đếm ngược đóng cổng chat thảo luận ban ngày
    threading.Thread(target=countdown_discussion_timer, args=(room_id, discussion_time)).start()

def countdown_discussion_timer(room_id, seconds):
    """Luồng đếm ngược thời gian thảo luận ban ngày"""
    time.sleep(seconds)
    if room_id in game_rooms and game_rooms[room_id]["status"] == "Discussion":
        # Hết giờ thảo luận, cưỡng chế đóng cổng chat tổng và chuyển sang giai đoạn Tố Giác Treo Cổ (Phần 17)
        if 'start_voting_nomination_phase' in globals():
            start_voting_nomination_phase(room_id)

# ==========================================
# MIDDLEWARE KIỂM SOÁT VÀ PHÒNG CHỐNG CHAT TRỘM TRONG GROUP
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_group_chat_filter(message):
    """
    Bộ lọc kiểm tra tin nhắn chat tổng: 
    - Chặn đứng hành vi chat của người chết.
    - Chặn đứng hành vi chat của người bị dính hiệu ứng Mute (Dịch bệnh/Thời tiết).
    - Chặn đứng hành vi chat của mọi người trừ nghi phạm khi đang trong giai đoạn Biện hộ.
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Tìm xem người chơi này đang thuộc phòng game nào
    active_room_id = None
    for rid, rdata in game_rooms.items():
        if user_id in rdata["players"]:
            active_room_id = rid
            break
            
    if active_room_id:
        room_data = game_rooms[active_room_id]
        
        # 1. Chặn người chơi đã chết chat vào sảnh khi game đang chạy
        if room_data["status"] in ["Night", "Day", "Discussion", "Vote_Nomination", "Stage_Defense", "Final_Judgment"] and user_id not in room_data["alive"]:
            try:
                bot.delete_message(chat_id, message.message_id)
                bot.send_message(user_id, "👻 Bạn đã chết, vui lòng giữ linh hồn lặng im không được phím chiến phá bĩnh trò chơi!")
            except Exception: 
                pass
            return
            
        # 2. Chặn người chơi đang bị dính án phạt Mute từ Sự kiện thời tiết hoặc bài dịch bệnh
        if room_data["status"] == "Discussion" and user_id in muted_players_today.get(active_room_id, set()):
            try:
                bot.delete_message(chat_id, message.message_id)
                bot.send_message(user_id, "🔇 Bạn đang trong trạng thái bị khóa mõm cấm ngôn luận, không thể gửi tin nhắn chat tổng lúc này!")
            except Exception: 
                pass
            return

        # 3. Đồng bộ Phần 18: Nếu đang trong giai đoạn Biện hộ, chặn chat tất cả mọi người trừ Nghi phạm trên bục
        if room_data["status"] == "Stage_Defense":
            suspect_id = globals().get("current_suspect_on_stage", {}).get(active_room_id)
            if user_id != suspect_id:
                try:
                    bot.delete_message(chat_id, message.message_id)
                    bot.send_message(user_id, "🔇 Làng đang trong giờ thi hành lệnh giữ trật tự! Hãy để nghi phạm thực hiện quyền biện hộ duy nhất trên bục lúc này.")
                except Exception: 
                    pass
                return
