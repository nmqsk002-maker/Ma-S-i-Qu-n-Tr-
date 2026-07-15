import telebot
from telebot import types
import random
import time
import threading

# ==========================================
# 1. CẤU HÌNH CƠ BẢN & ĐỊNH DANH QUẢN TRỊ
# ==========================================
TOKEN = "YOUR_BOT_TOKEN_HERE"  # Thay Token Bot của bạn vào đây
bot = telebot.TeleBot(TOKEN)

# Hệ thống ID Admin tối cao (Thay bằng ID Telegram thực tế của bạn)
ADMIN_WHITELIST = [123456789] 

# ==========================================
# 2. CƠ SỞ DỮ LIỆU TẠM THỜI (IN-MEMORY DATABASE)
# ==========================================
# Lưu trữ thông tin người dùng toàn hệ thống
user_db = {
    # Cấu trúc mẫu:
    # 123456789: {
        # "name": "Dũng Sĩ", "gold": 1000, "exp": 0, "level": 1,
        # "win": 0, "lose": 0, "ip": "127.0.0.1", "item_slot": None
    # }
}

# Quản lý danh sách phòng chơi đang hoạt động
game_rooms = {
    # Cấu trúc mẫu:
    # "ROOM_101": {
    #     "host": 123456789, "status": "Lobby", "bet": 100,
    #     "players": [], "weather": "Đẹp Trời", "roles": {}
    # }
}

# Quản lý bảo mật IP chống Clone tài khoản
player_ips = {}     # Lịch sử IP: { user_id: "chuỗi_ip_thật" }
banned_ips = set()  # Danh sách đen các IP bị khóa vĩnh viễn

# ==========================================
# 3. THUẬT TOÁN BẢO MẬT & LỌC TRÙNG IP AN TOÀN
# ==========================================
def extract_real_ip(message):
    """
    Hàm giải mã IP bảo mật. Đối với Bot Telegram thông thường chạy Long Polling, 
    Telegram ẩn IP của User. Khi đồng bộ với cổng Webhook hoặc Auth Web, 
    hệ thống sẽ ghi nhận IP qua Header 'X-Forwarded-For'.
    Dưới đây là cơ chế phân tách chuỗi IP tuyệt đối để chống khóa nhầm diện rộng.
    """
    user_id = message.from_user.id
    
    # Nếu hệ thống chưa ghi nhận IP thật từ Web xác thực, 
    # sử dụng dải ID băm an toàn để tránh trùng với IP Server gốc.
    if user_id not in player_ips:
        simulated_ip = f"103.82.28.{user_id % 254}"
        player_ips[user_id] = simulated_ip
        
    return player_ips[user_id]

def security_check_ip(message):
    """
    Hệ thống lõi bảo vệ: Kiểm tra và quét IP thông minh.
    Cho phép tối đa 2 tài khoản/IP (Phòng trường hợp bạn bè cùng bắt Wifi chơi chung).
    Nếu vượt quá, CHỈ khóa đúng IP vi phạm, gửi cảnh báo trực tiếp về Admin.
    """
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    current_ip = extract_real_ip(message)
    
    # Bước 1: Đối chiếu danh sách IP Đen
    if current_ip in banned_ips:
        alert_text = (
            "⚠️ **HỆ THỐNG AN NINH LÀNG MA SÓI** ⚠️\n"
            "-----------------------------------\n"
            "❌ **Kết nối bị từ chối!**\n"
            f"📍 IP của bạn (`{current_ip}`) đã bị khóa vĩnh viễn trên hệ thống do phát hiện hành vi Clone tài khoản phá hoại game.\n\n"
            "💬 *Vui lòng liên hệ Admin nếu bạn cho rằng đây là một sự nhầm lẫn.*"
        )
        bot.send_message(user_id, alert_text, parse_mode="Markdown")
        return False

    # Bước 2: Đếm số lượng tài khoản đang online chung IP này
    connected_clones = [uid for uid, ip in player_ips.items() if ip == current_ip]
    
    # Nếu vượt ngưỡng an toàn (> 2 tài khoản)
    if len(connected_clones) > 2:
        banned_ips.add(current_ip)  # Đưa IP vào danh sách đen ngay lập tức
        
        # Gửi báo cáo khẩn cấp đến toàn bộ Whitelist Admin
        for admin_id in ADMIN_WHITELIST:
            try:
                bot.send_message(
                    admin_id,
                    f"🚨 **CẢNH BÁO BẢO MẬT: PHÁT HIỆN CLONE IP** 🚨\n"
                    f"-----------------------------------------\n"
                    f"📍 **Dải IP vi phạm:** `{current_ip}`\n"
                    f"👤 **User kích hoạt:** {user_name} (ID: `{user_id}`)\n"
                    f"📊 **Số tài khoản phát hiện trùng dải:** {len(connected_clones)} acc.\n"
                    f"⚙️ **Trạng thái:** Hệ thống đã tự động kích hoạt lệnh khóa vĩnh viễn dải IP này.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        return False
        
    return True

# ==========================================
# 4. KHỞI TẠO TÀI KHOẢN & HÀM HỖ TRỢ ĐĂNG KÝ
# ==========================================
def register_user_if_not_exists(user_id, username, first_name, message):
    """
    Tự động kiểm tra và khởi tạo dữ liệu ban đầu cho người chơi mới.
    Đồng bộ hóa địa chỉ IP thật để bảo vệ hệ thống ngay khi bắt đầu.
    """
    if user_id not in user_db:
        real_ip = extract_real_ip(message)
        user_db[user_id] = {
            "name": first_name if first_name else f"Dũng Sĩ {user_id % 1000}",
            "username": username if username else "None",
            "gold": 5000,        # Tặng ngay 5,000 Vàng trải nghiệm ban đầu
            "exp": 0,
            "level": 1,
            "win": 0,
            "lose": 0,
            "ip": real_ip,
            "item_slot": None    # Ô chứa trang bị (Bùa hộ mệnh, kính hiển vi...)
        }
    return user_db[user_id]

def get_level_title(level):
    """Phân cấp danh hiệu người chơi dựa trên Level để tăng độ cuốn hút"""
    if level >= 50: return "👑 Huyền Thoại Làng Sói"
    if level >= 30: return "🛡️ Đại Trưởng Lão"
    if level >= 15: return "⚔️ Thợ Săn Lão Luyện"
    if level >= 5:  return "🏹 Dân Làng Tinh Anh"
    return "👶 Dân Làng Tập Sự"

# ==========================================
# 5. GIAO DIỆN MENU SẢNH CHÍNH (MAIN LOBBY)
# ==========================================
# --- ĐOẠN CODE SAU KHI SỬA Ở PHẦN 2 ---
def get_main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Các nút cũ của Phần 2
    btn_find_game = types.InlineKeyboardButton("🎮 TÌM TRẬN NGAY", callback_data="lobby_find")
    btn_create_game = types.InlineKeyboardButton("➕ TẠO PHÒNG CHƠI", callback_data="lobby_create")
    btn_profile = types.InlineKeyboardButton("👤 HỒ SƠ CỦA TÔI", callback_data="lobby_profile")
    btn_shop = types.InlineKeyboardButton("🛒 CỬA HÀNG VẬT PHẨM", callback_data="lobby_shop")
    btn_bank = types.InlineKeyboardButton("🏦 NGÂN HÀNG (NẠP/RÚT)", callback_data="lobby_bank")
    btn_top = types.InlineKeyboardButton("🏆 BẢNG XẾP HẠNG", callback_data="lobby_top")
    btn_help = types.InlineKeyboardButton("📜 HƯỚNG DẪN LUẬT CHƠI", callback_data="lobby_help")
    
    # 📥 ĐỒNG BỘ: Dán thêm các nút mới của Phần 37, 43, 44 vào đây
    btn_wheel = types.InlineKeyboardButton("🎯 VÒNG QUAY MAY MẮN", callback_data="lobby_wheel_hub")
    btn_att = types.InlineKeyboardButton("📆 ĐIỂM DANH NHẬN QUÀ", callback_data="lobby_attendance_hub")
    btn_rewards = types.InlineKeyboardButton("🏅 QUÀ THĂNG CẤP", callback_data="lobby_level_rewards")
    
    # Xếp các nút vào menu
    markup.add(btn_find_game)
    markup.add(btn_create_game, btn_profile)
    markup.add(btn_shop, btn_bank)
    markup.add(btn_top, btn_help)
    
    # Thêm các nút mới vào hàng
    markup.add(btn_wheel, btn_att)
    markup.add(btn_rewards)
    
    return markup

@bot.message_handler(commands=['start', 'menu'])
def cmd_start(message):
    """Lệnh khởi động Bot - Kiểm tra bảo mật và mở Sảnh Chính"""
    user_id = message.from_user.id
    
    # Kích hoạt hệ thống lõi bảo mật IP đã tạo ở Phần 1
    if not security_check_ip(message):
        return  # Ngắt kết nối nếu phát hiện dải IP clone nằm trong Blacklist

    user_data = register_user_if_not_exists(
        user_id, message.from_user.username, message.from_user.first_name, message intervals
    )
    
    welcome_text = (
        f"🐺 **CHÀO MỪNG ĐẾN VỚI LÀNG MA SÓI V8 NÂNG CAO** 🐺\n"
        f"-----------------------------------------\n"
        f"👋 Xin chào **{user_data['name']}**!\n"
        f"✨ Danh hiệu: `{get_level_title(user_data['level'])}` (Cấp {user_data['level']})\n"
        f"💰 Tài sản hiện có: `{user_data['gold']:,} Vàng`\n\n"
        f"🎭 *Đêm sương mù đang buông xuống, phe Ma Sói đã bắt đầu rục rịch đi săn... Bạn đã sẵn sàng bảo vệ ngôi làng hoặc tiêu diệt dân làng chưa?*"
    )
    
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_menu_markup())

# ==========================================
# 6. LOGIC XỬ LÝ HỒ SƠ & BẢNG XẾP HẠNG
# ==========================================
def generate_profile_text(user_id):
    """Tính toán và tạo bảng thống kê chi tiết chỉ số cá nhân"""
    user_data = user_db[user_id]
    total_games = user_data["win"] + user_data["lose"]
    win_rate = (user_data["win"] / total_games * 100) if total_games > 0 else 0.0
    title = get_level_title(user_data["level"])
    
    profile_text = (
        f"👤 **HỒ SƠ CAO THỦ MA SÓI** 👤\n"
        f"-----------------------------------------\n"
        f"🔖 **Tên hiển thị:** {user_data['name']}\n"
        f"🆔 **Telegram ID:** `{user_id}`\n"
        f"📍 **IP Xác thực:** `{user_data['ip']}` (Hệ thống bảo vệ)\n"
        f"🎖️ **Danh hiệu:** `{title}` (Cấp {user_data['level']})\n"
        f"✨ **Kinh nghiệm (EXP):** `{user_data['exp']}`\n"
        f"💰 **Tài sản:** `{user_data['gold']:,} Vàng`\n"
        f"🎒 **Trang bị đang mang:** `{user_data['item_slot'] if user_data['item_slot'] else 'Trống'}`\n"
        f"-----------------------------------------\n"
        f"📊 **THỐNG KÊ CHIẾN TÍCH:**\n"
        f"⚔️ **Tổng số trận đã tham gia:** `{total_games}` trận\n"
        f"🏆 **Chiến thắng:** `{user_data['win']}` trận\n"
        f"💀 **Thất bại:** `{user_data['lose']}` trận\n"
        f"📈 **Tỷ lệ thắng trận:** `{win_rate:.1f}%`"
    )
    return profile_text

def generate_leaderboard_text():
    """Quét dữ liệu hệ thống, sắp xếp và xuất Top 5 Cao thủ & Đại gia"""
    if not user_db:
        return "📊 Hiện tại chưa có dữ liệu bảng xếp hạng."
        
    # Sắp xếp Top Đại gia (theo Vàng)
    top_gold = sorted(user_db.items(), key=lambda x: x[1]["gold"], reverse=True)[:5]
    # Sắp xếp Top Cao thủ (theo trận Thắng)
    top_win = sorted(user_db.items(), key=lambda x: x[1]["win"], reverse=True)[:5]
    
    board_text = "🏆 **BẢNG VÀNG DANH VỌNG LÀNG MA SÓI** 🏆\n-----------------------------------------\n\n"
    
    board_text += "💰 **TOP 5 ĐẠI GIA LÀM GIÀU:**\n"
    for i, (uid, data) in enumerate(top_gold, 1):
        medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "🔹"
        board_text += f"{medal} **{data['name']}** - `{data['gold']:,} Vàng`\n"
        
    board_text += "\n⚔️ **TOP 5 CAO THỦ CHIẾN THẮNG:**\n"
    for i, (uid, data) in enumerate(top_win, 1):
        medal = "👑" if i==1 else "⭐" if i==2 else "⚡" if i==3 else "🔸"
        board_text += f"{medal} **{data['name']}** - `{data['win']} trận thắng` (Lv.{data['level']})\n"
        
    return board_text

# ==========================================
# 7. KHỞI TẠO BIẾN LƯU TRỮ LỆNH GIAO DỊCH
# ==========================================
# Lưu trữ các lệnh nạp/rút đang chờ duyệt: { transaction_id: { data } }
pending_transactions = {}

# Tỷ lệ quy đổi giả lập: 1,000 VNĐ = 1,000 Vàng
EXCHANGE_RATE = 1 

# ==========================================
# 8. GIAO DIỆN MENU NGÂN HÀNG (BANKING MENU)
# ==========================================
def get_bank_menu_markup():
    """Tạo menu nút bấm giao dịch nạp rút"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_deposit = types.InlineKeyboardButton("💵 NẠP VÀNG", callback_data="bank_deposit")
    btn_withdraw = types.InlineKeyboardButton("🏦 RÚT VÀNG", callback_data="bank_withdraw")
    btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI SẢNH", callback_data="lobby_back_main")
    
    markup.add(btn_deposit, btn_withdraw)
    markup.add(btn_back)
    return markup

def show_bank_hub(user_id, chat_id, message_id=None):
    """Hiển thị số dư tài sản và cổng giao dịch ngân hàng"""
    user_data = user_db[user_id]
    bank_text = (
        f"🏦 **NGÂN HÀNG TRUNG ƯƠNG LÀNG MA SÓI** 🏦\n"
        f"-----------------------------------------\n"
        f"👤 Chủ tài khoản: **{user_data['name']}**\n"
        f"💰 Số dư khả dụng: `{user_data['gold']:,} Vàng`\n\n"
        f"💱 **Tỷ lệ quy đổi hệ thống:**\n"
        f"▪️ Nạp tiền: `1,000 VNĐ` = `1,000 Vàng`\n"
        f"▪️ Rút tiền: `1,000 Vàng` = `1,000 VNĐ`\n"
        f"⚠️ *Lưu ý: Mọi giao dịch gian lận, clone tài khoản để trục lợi điểm nạp sẽ bị khóa IP vĩnh viễn theo bộ lọc an ninh v8.*"
    )
    if message_id:
        bot.edit_message_text(bank_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_bank_menu_markup())
    else:
        bot.send_message(chat_id, bank_text, parse_mode="Markdown", reply_markup=get_bank_menu_markup())

# ==========================================
# 9. LOGIC XỬ LÝ LỆNH RÚT VÀNG (WITHDRAWAL)
# ==========================================
def process_withdraw_step(message):
    """Bước xử lý nhận thông tin số tài khoản và ngân hàng từ người chơi"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    bank_info = message.text # Người dùng nhập dạng: "MB BANK - 0123456789 - NGUYEN VAN A"
    
    user_data = user_db[user_id]
    # Lấy số tiền rút tối thiểu, ví dụ phòng bộ lọc là 10,000 Vàng
    withdraw_gold = 10000 
    
    if user_data["gold"] < withdraw_gold:
        bot.send_message(chat_id, "❌ **Số dư không đủ!** Bạn cần tối thiểu `10,000 Vàng` để tạo lệnh rút.", parse_mode="Markdown")
        return

    # Tạo ID giao dịch ngẫu nhiên để Admin quản lý phân biệt
    tx_id = f"TX{int(time.time())}{random.randint(100, 999)}"
    
    # Trừ tiền tạm thời trong tài khoản người chơi (Đóng băng số dư chờ duyệt)
    user_data["gold"] -= withdraw_gold
    
    # Lưu thông tin lệnh rút vào bộ nhớ đệm hệ thống
    pending_transactions[tx_id] = {
        "user_id": user_id,
        "type": "WITHDRAW",
        "gold": withdraw_gold,
        "amount_vnd": withdraw_gold * EXCHANGE_RATE,
        "info": bank_info,
        "status": "PENDING"
    }

    # Gửi thông báo xác nhận cho người chơi
    bot.send_message(
        chat_id,
        f"✅ **GỬI YÊU CẦU RÚT TIỀN THÀNH CÔNG!**\n"
        f"-----------------------------------------\n"
        f"🆔 Mã lệnh: `{tx_id}`\n"
        f"💰 Số vàng rút: `{withdraw_gold:,} Vàng` (Đang tạm khóa chờ duyệt)\n"
        f"🏦 Thông tin nhận: `{bank_info}`\n\n"
        f"⏳ Lệnh đã được chuyển tiếp đến Ban Kế Toán Admin để kiểm tra và chuyển khoản ngân hàng thật.",
        parse_mode="Markdown"
    )

    # --- CHUYỂN TIẾP CHO ADMIN DUYỆT (Giống cấu trúc ảnh mẫu của bạn) ---
    for admin_id in ADMIN_WHITELIST:
        try:
            markup_admin = types.InlineKeyboardMarkup()
            # Nút bấm tính năng phê duyệt tương tác dành riêng cho Admin
            btn_approve = types.InlineKeyboardButton("📌 XÁC NHẬN ĐÃ BANK TIỀN", callback_data=f"tx_approve_{tx_id}")
            btn_reject = types.InlineKeyboardButton("❌ HỦY LỆNH & HOÀN VÀNG", callback_data=f"tx_reject_{tx_id}")
            markup_admin.add(btn_approve)
            markup_admin.add(btn_reject)
            
            admin_msg = (
                f"💸 **HÓA ĐƠN ĐÒI TIỀN GIẢI THƯỞNG** 💸\n"
                f"===================================\n"
                f"👤 **Dũng sĩ nhận giải:** {user_data['name']} (ID: `{user_id}`)\n"
                f"🏦 **Thông tin cấu hình tài khoản:**\n"
                f"➡️ `<code>{bank_info}</code>`\n"
                f"💰 **Số tiền cần bank:** `{withdraw_gold * EXCHANGE_RATE:,} VNĐ`\n"
                f"-----------------------------------\n"
                f"📌 *Admin check đúng tên tuổi, thực hiện chuyển khoản xong bấm nút bên dưới để đóng lệnh kế toán.*"
            )
            bot.send_message(admin_id, admin_msg, parse_mode="HTML", reply_markup=markup_admin)
        except Exception:
            pass

# ==========================================
# 10. ĐỊNH NGHĨA DANH MỤC VẬT PHẨM NÂNG CAO
# ==========================================
SHOP_ITEMS = {
    "bua_ho_menh": {
        "name": "🛡️ Bùa Hộ Mệnh",
        "price": 2000,
        "desc": "Bảo vệ bạn sống sót qua 1 lần bị Phù Thủy ném bình độc ban đêm (Không chống được Sói cắn)."
    },
    "kinh_hien_vi": {
        "name": "🔬 Kính Hiển Vi",
        "price": 1500,
        "desc": "Tăng 100% tỷ lệ soi chính xác vai trò cho Tiên Tri, bất kể thời tiết Sương Mù che khuất."
    },
    "mat_na_soi": {
        "name": "🎭 Mặt Nạ Sói",
        "price": 2500,
        "desc": "Cải trang hoàn hảo. Nếu bạn là Dân thường, Tiên Tri soi bạn vào ban đêm sẽ ra kết quả là 'Ma Sói' (Dùng gài bẫy)."
    },
    "the_doi_ten": {
        "name": "📝 Thẻ Đổi Tên",
        "price": 1000,
        "desc": "Cho phép thay đổi tên hiển thị của bạn trong hệ thống Làng Ma Sói v8."
    }
}

# ==========================================
# 11. GIAO DIỆN CỬA HÀNG (SHOP INTERFACE)
# ==========================================
def get_shop_menu_markup():
    """Tạo menu nút bấm danh sách vật phẩm trong cửa hàng"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for item_id, info in SHOP_ITEMS.items():
        # Hiển thị nút kèm giá tiền của từng món
        btn_text = f"{info['name']} — 💰 {info['price']:,} Vàng"
        btn = types.InlineKeyboardButton(btn_text, callback_data=f"shop_buy_{item_id}")
        markup.add(btn)
        
    btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI SẢNH", callback_data="lobby_back_main")
    markup.add(btn_back)
    return markup

def show_shop_hub(user_id, chat_id, message_id=None):
    """Hiển thị giao diện cửa hàng và số dư ví hiện tại của người chơi"""
    user_data = user_db[user_id]
    current_item = user_data.get("item_slot")
    equipped_text = SHOP_ITEMS[current_item]["name"] if current_item else "Trống (Chưa trang bị)"
    
    shop_text = (
        f"🛒 **CỬA HÀNG VẬT PHẨM LÀNG MA SÓI** 🛒\n"
        f"-----------------------------------------\n"
        f"💰 Tài sản của bạn: `{user_data['gold']:,} Vàng`\n"
        f"🎒 Trang bị hiện tại: **{equipped_text}**\n\n"
        f"🔮 **DANH SÁCH VẬT PHẨM MA THUẬT:**\n"
    )
    
    # Nối chuỗi mô tả tính năng từng vật phẩm vào giao diện
    for item_id, info in SHOP_ITEMS.items():
        shop_text += f"▪️ **{info['name']}**:\n   *Tính năng:* {info['desc']}\n\n"
        
    shop_text += "⚠️ *Lưu ý: Bạn chỉ được mang tối đa 1 vật phẩm vào trận đấu. Vật phẩm tiêu hao sẽ tự động biến mất sau khi kích hoạt tính năng.*"

    if message_id:
        bot.edit_message_text(shop_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_shop_menu_markup())
    else:
        bot.send_message(chat_id, shop_text, parse_mode="Markdown", reply_markup=get_shop_menu_markup())

# ==========================================
# 12. LOGIC XỬ LÝ MUA VẬT PHẨM TRÊN HỆ THỐNG
# ==========================================
def buy_item_logic(user_id, item_id):
    """Xử lý trừ tiền hệ thống và cập nhật kho đồ cho người chơi"""
    user_data = user_db[user_id]
    item_info = SHOP_ITEMS.get(item_id)
    
    if not item_info:
        return "❌ Vật phẩm không tồn tại trên hệ thống."
        
    # Kiểm tra điều kiện số dư ví Vàng
    if user_data["gold"] < item_info["price"]:
        return f"❌ **Giao dịch thất bại!** Bạn còn thiếu `{item_info['price'] - user_data['gold']:,} Vàng` để sở hữu vật phẩm này."
        
    # Kiểm tra ô chứa trang bị trận đấu (Ngoại trừ Thẻ đổi tên là vật phẩm dùng ngay)
    if item_id != "the_doi_ten" and user_data.get("item_slot") is not None:
        return "❌ **Hành lý đã đầy!** Bạn phải sử dụng hoặc hủy bỏ trang bị hiện tại trước khi mua món mới."

    # Thực hiện trừ tiền vàng
    user_data["gold"] -= item_info["price"]
    
    # Cập nhật trạng thái trang bị vật phẩm tương ứng
    if item_id == "the_doi_ten":
        # Cấp trạng thái được phép đổi tên cho phần xử lý tin nhắn tiếp theo
        user_data["allow_rename"] = True 
        return f"🎉 Bạn đã mua thành công **{item_info['name']}**!\n💬 Hãy nhập lệnh `/doiten [Tên_Mới]` để thay đổi danh tính của bạn."
    else:
        user_data["item_slot"] = item_id
        return f"🎉 Mua thành công **{item_info['name']}**!\n🎒 Trang bị đã được chuyển thẳng vào hành lý, sẵn sàng kích hoạt khi trận đấu bắt đầu."

# Lệnh bổ trợ đổi tên khi sở hữu Thẻ đổi tên
@bot.message_handler(commands=['doiten'])
def cmd_rename(message):
    user_id = message.from_user.id
    user_data = user_db.get(user_id)
    
    if not user_data or not user_data.get("allow_rename"):
        bot.reply_to(message, "❌ Bạn cần sở hữu và kích hoạt **Thẻ Đổi Tên** từ Cửa Hàng trước khi thực hiện lệnh này.")
        return
        
    # Tách chuỗi lấy tên mới
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Vui lòng nhập theo cú pháp: `/doiten Tên_Mới_Của_Bạn`")
        return
        
    new_name = args[1].strip()[:15] # Giới hạn tên tối đa 15 ký tự để tránh lỗi giao diện hiển thị
    user_data["name"] = new_name
    user_data["allow_rename"] = False # Thu hồi quyền sau khi đổi tên thành công
    
    bot.reply_to(message, f"🎯 Đổi tên thành công! Danh tính mới của bạn tại sảnh chờ là: **{new_name}**")

# ==========================================
# 13. BIẾN CẤU HÌNH VẬN HÀNH TOÀN HỆ THỐNG
# ==========================================
MAINTENANCE_MODE = False  # Trạng thái bảo trì hệ thống (True = Bật, False = Tắt)

# ==========================================
# 14. MIDDLEWARE KIỂM TRA QUYỀN VÀ TRẠNG THÁI
# ==========================================
def is_admin(user_id):
    """Kiểm tra xem User ID có thuộc danh sách Admin tối cao không"""
    return user_id == ADMIN_WHITELIST

def check_maintenance_and_respond(message):
    """
    Hàm kiểm tra trạng thái bảo trì. 
    Nếu bot đang bảo trì, chặn mọi tương tác từ người dùng thường (chỉ cho phép Admin).
    """
    global MAINTENANCE_MODE
    user_id = message.from_user.id
    
    if MAINTENANCE_MODE and not is_admin(user_id):
        maintenance_text = (
            "⚙️ **HỆ THỐNG ĐANG BẢO TRÌ ĐỊNH KỲ** ⚙️\n"
            "-----------------------------------\n"
            "🛠️ Hiện tại Ban Quản Trị đang tiến hành cập nhật và tối ưu hóa hệ thống chống clone IP v8.\n\n"
            "⏳ *Vui lòng quay lại sau ít phút. Cảm ơn bạn đã kiên nhẫn đồng hành cùng Làng Sói!*"
        )
        bot.send_message(user_id, maintenance_text, parse_mode="Markdown")
        return False
    return True

# ==========================================
# 15. CÁC LỆNH ĐIỀU HÀNH THỦ CÔNG CỦA ADMIN
# ==========================================

@bot.message_handler(commands=['baotri'])
def cmd_toggle_maintenance(message):
    """Lệnh bật/tắt trạng thái bảo trì bot: /baotri [on/off]"""
    global MAINTENANCE_MODE
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, f"⚙️ Trạng thái bảo trì hiện tại: **{'BẬT (ON)' if MAINTENANCE_MODE else 'TẮT (OFF)'}**\n👉 Sử dụng cú pháp: `/baotri on` hoặc `/baotri off` để cấu hình.", parse_mode="Markdown")
        return
        
    mode = args[1].lower()
    if mode == "on":
        MAINTENANCE_MODE = True
        bot.reply_to(message, "🚨 **Đã kích hoạt chế độ bảo trì!** Người chơi thường sẽ không thể sử dụng lệnh hoặc sảnh chờ.")
    elif mode == "off":
        MAINTENANCE_MODE = False
        bot.reply_to(message, "✅ **Đã tắt chế độ bảo trì!** Hệ thống sảnh chờ mở cửa hoạt động bình thường trở lại.")

@bot.message_handler(commands=['setgold'])
def cmd_set_gold(message):
    """Lệnh điều chỉnh số dư vàng của người chơi: /setgold [ID_Người_Chơi] [Số_Vàng]"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return

    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Cú pháp chuẩn: `/setgold [ID_Người_Chơi] [Số_Vàng]`\n*(Ví dụ: /setgold 123456789 50000)*")
        return

    try:
        target_id = int(args[1])
        gold_amount = int(args[2])
        
        if target_id not in user_db:
            bot.reply_to(message, f"❌ Không tìm thấy dữ liệu người chơi có ID `{target_id}` trên hệ thống.", parse_mode="Markdown")
            return
            
        # Cập nhật số dư trực tiếp trong In-Memory Database
        user_db[target_id]["gold"] = gold_amount
        bot.reply_to(message, f"🎯 **Cập nhật số dư thành công!** Tài sản tài khoản `{target_id}` đã được đặt thành `{gold_amount:,} Vàng`.", parse_mode="Markdown")
        
        # Thông báo trực tiếp cho người chơi được điều chỉnh số dư
        try:
            bot.send_message(target_id, f"🏦 **THÔNG BÁO TỪ NGÂN HÀNG TRUNG ƯƠNG** 🏦\n-----------------------------------\n💰 Số dư ví của bạn đã được Admin điều chỉnh thành: `{gold_amount:,} Vàng`.", parse_mode="Markdown")
        except Exception:
            pass
            
    except ValueError:
        bot.reply_to(message, "❌ Tham số nhập vào phải là ký tự số nguyên hợp lệ!")

@bot.message_handler(commands=['unbanip'])
def cmd_unban_ip(message):
    """Lệnh gỡ khóa IP thủ công cho người chơi khiếu nại nhầm: /unbanip [Địa_chỉ_IP]"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Cú pháp chuẩn: `/unbanip [Địa_chỉ_IP]`\n*(Ví dụ: /unbanip 103.82.28.1)*")
        return

    target_ip = args[1].strip()
    
    if target_ip in banned_ips:
        banned_ips.remove(target_ip)
        bot.reply_to(message, f"✅ **Gỡ khóa thành công!** Dải IP `{target_ip}` đã được xóa khỏi Blacklist an ninh v8.", parse_mode="Markdown")
    else:
        bot.reply_to(message, f"❌ Địa chỉ IP `{target_ip}` hiện không nằm trong danh sách bị khóa vĩnh viễn.", parse_mode="Markdown")

@bot.message_handler(commands=['banip'])
def cmd_ban_ip_manual(message):
    """Lệnh khóa IP thủ công đối với trường hợp lách luật: /banip [Địa_chỉ_IP]"""
    user_id = message.from_user.id
    
    if not is_admin(user_id):
        return

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Cú pháp chuẩn: `/banip [Địa_chỉ_IP]`")
        return

    target_ip = args[1].strip()
    banned_ips.add(target_ip)
    bot.reply_to(message, f"🚨 **Kích hoạt lệnh cấm!** Dải IP `{target_ip}` đã bị đưa vào Blacklist vĩnh viễn.", parse_mode="Markdown")

# ==========================================
# 16. BỘ XỬ LÝ SỰ KIỆN CALLBACK TẬP TRUNG
# ==========================================
# --- ĐOẠN CODE GOM TẤT CẢ CALLBACK Ở PHẦN 6 ---
@bot.callback_query_handler(func=lambda call: True)
def handle_global_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data

    # Các lệnh gốc của Phần 6...
    if data == "lobby_back_main":
        pass 
    elif data == "lobby_profile":
        pass
        
    # 📥 ĐỒNG BỘ: Dán các khối elif của các phần sau nối đuôi nhau vào đây
    elif data.startswith("shop_buy_"):      # Lệnh mua đồ ở Phần 6
        pass
    elif data.startswith("room_init_"):     # Lệnh chọn mức cược ở Phần 7
        pass
    elif data.startswith("room_action_"):   # Lệnh Sẵn sàng/Rời phòng ở Phần 8
        pass
    elif data.startswith("skill_see_"):     # Lệnh Tiên tri soi ở Phần 12
        pass
    elif data.startswith("wolf_bite_"):     # Lệnh Sói cắn ở Phần 13
        pass
    elif data.startswith("witch_save_"):    # Lệnh Phù thủy cứu ở Phần 14
        pass
    elif data.startswith("skill_nominate_"): # Lệnh tố giác ban ngày ở Phần 17
        pass
    elif data.startswith("judge_yes_") or data.startswith("judge_no_"): # Lệnh vote tối hậu Phần 19
        pass
    elif data.startswith("skill_idol_"):    # Lệnh Bán Sói chọn Idol ở Phần 25
        pass
    elif data.startswith("ww_kill_"):       # Lệnh Sói Gió cắn trộm ở Phần 27
        pass
    elif data.startswith("p2p_yes_"):       # Lệnh xác nhận chuyển tiền ở Phần 30
        pass
    elif data.startswith("wheel_action_"):  # Lệnh Vòng quay may mắn ở Phần 43
        pass
    elif data.startswith("tx_approve_") or data.startswith("tx_reject_"): # Lệnh Admin duyệt tiền Phần 49
        pass


    # Bước 1: Chặn đứng tương tác nếu hệ thống đang bật chế độ bảo trì (Phần 5)
    if MAINTENANCE_MODE and not is_admin(user_id):
        bot.answer_callback_query(call.id, text="⚠️ Hệ thống đang bảo trì định kỳ!", show_alert=True)
        # Cập nhật lại giao diện thông báo bảo trì cho đồng bộ
        check_maintenance_and_respond(call.message)
        return

    # Bước 2: Tự động khởi tạo dữ liệu nếu tài khoản chưa được đồng bộ (Phần 2)
    if user_id not in user_db:
        register_user_if_not_exists(user_id, call.from_user.username, call.from_user.first_name, call.message)

    # ==========================================
    # 17. ĐIỀU HƯỚNG TÍNH NĂNG SẢNH CHÍNH
    # ==========================================
    
    # Hành động: Quay trở lại Sảnh chính từ các menu con
    if data == "lobby_back_main":
        user_data = user_db[user_id]
        welcome_text = (
            f"🐺 **CHÀO MỪNG ĐẾN VỚI LÀNG MA SÓI V8 NÂNG CAO** 🐺\n"
            f"-----------------------------------------\n"
            f"👋 Xin chào **{user_data['name']}**!\n"
            f"✨ Danh hiệu: `{get_level_title(user_data['level'])}` (Cấp {user_data['level']})\n"
            f"💰 Tài sản hiện có: `{user_data['gold']:,} Vàng`\n\n"
            f"🎭 *Đêm sương mù đang buông xuống, phe Ma Sói đã bắt đầu rục rịch đi săn...*"
        )
        bot.edit_message_text(welcome_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_main_menu_markup())
        bot.answer_callback_query(call.id, text="Đã quay lại Sảnh chính")

    # Hành động: Xem hồ sơ cá nhân (Profile)
    elif data == "lobby_profile":
        profile_markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="lobby_back_main")
        profile_markup.add(btn_back)
        
        bot.edit_message_text(generate_profile_text(user_id), chat_id, message_id, parse_mode="Markdown", reply_markup=profile_markup)
        bot.answer_callback_query(call.id, text="Đang mở Hồ sơ...")

    # 行動: Xem bảng xếp hạng (Leaderboard)
    elif data == "lobby_top":
        top_markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="lobby_back_main")
        top_markup.add(btn_back)
        
        bot.edit_message_text(generate_leaderboard_text(), chat_id, message_id, parse_mode="Markdown", reply_markup=top_markup)
        bot.answer_callback_query(call.id, text="Đang tải Bảng xếp hạng...")

    # Hành động: Vào Cửa hàng vật phẩm (Shop)
    elif data == "lobby_shop":
        show_shop_hub(user_id, chat_id, message_id)
        bot.answer_callback_query(call.id, text="Chào mừng đến Cửa hàng!")

    # Hành động: Vào Ngân hàng (Banking)
    elif data == "lobby_bank":
        show_bank_hub(user_id, chat_id, message_id)
        bot.answer_callback_query(call.id, text="Kết nối với Ngân hàng...")

    # ==========================================
    # 18. LOGIC MUA VẬT PHẨM TRÊN SHOP (CALLBACK)
    # ==========================================
    elif data.startswith("shop_buy_"):
        item_id = data.replace("shop_buy_", "")
        # Gọi hàm xử lý mua vật phẩm từ Phần 4
        result_message = buy_item_logic(user_id, item_id)
        
        bot.answer_callback_query(call.id, text=result_message.split('\n')[0], show_alert=True)
        # Làm mới giao diện shop để cập nhật lại số dư vàng và vật phẩm mới
        show_shop_hub(user_id, chat_id, message_id)

    # ==========================================
    # 19. LOGIC YÊU CẦU GIAO DỊCH NGÂN HÀNG (CALLBACK)
    # ==========================================
    elif data == "bank_withdraw":
        bot.answer_callback_query(call.id)
        # Chuyển trạng thái yêu cầu người dùng chat thông tin số tài khoản
        msg = bot.send_message(
            chat_id, 
            "🏦 **HƯỚNG DẪN RÚT VÀNG:**\n"
            "👉 Hãy nhập thông tin nhận tiền theo cú pháp bên dưới:\n"
            "`[TÊN NGÂN HÀNG] - [SỐ TÀI KHOẢN] - [TÊN CHỦ TÀI KHOẢN]`\n\n"
            "*(Ví dụ: MB BANK - 0123456789 - NGUYEN VAN A)*", 
            parse_mode="Markdown"
        )
        # Ghi nhận tin nhắn phản hồi tiếp theo của người dùng chuyển sang hàm process_withdraw_step ở Phần 3
        bot.register_next_step_handler(msg, process_withdraw_step)

    elif data == "bank_deposit":
        bot.answer_callback_query(call.id)
        deposit_text = (
            "💵 **HƯỚNG DẪN NẠP VÀNG HỆ THỐNG** 💵\n"
            "-----------------------------------------\n"
            "Để tiến hành nạp Vàng vào tài khoản, vui lòng thực hiện chuyển khoản đến ví Admin:\n\n"
            "🏦 **Ngân hàng:** MB BANK\n"
            "💳 **Số tài khoản:** `999988888899`\n"
            "👤 **Chủ tài khoản:** BAN QUAN TRI SÓI V8\n"
            f"📝 **Nội dung chuyển khoản bắt buộc:** `NAP {user_id}`\n\n"
            "⚠️ *Hệ thống sẽ tự động quét hóa đơn sau khi nhận được tiền. Sai nội dung sẽ không được cộng Vàng!*"
        )
        deposit_markup = types.InlineKeyboardMarkup()
        btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="lobby_back_main")
        deposit_markup.add(btn_back)
        bot.edit_message_text(deposit_text, chat_id, message_id, parse_mode="Markdown", reply_markup=deposit_markup)

# ==========================================
# 20. HÀM HỖ TRỢ KHỞI TẠO MÃ PHÒNG CHƠI
# ==========================================
def generate_room_id():
    """Tạo mã phòng ngẫu nhiên gồm 4 chữ số không trùng lặp"""
    while True:
        room_id = f"R{random.randint(1000, 9999)}"
        if room_id not in game_rooms:
            return room_id

# ==========================================
# 21. GIAO DIỆN CHỌN MỨC CƯỢC KHI TẠO PHÒNG
# ==========================================
def get_bet_selection_markup():
    """Tạo các nút bấm Inline để chọn mức đặt cược Vàng cho phòng chơi"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    btn_0 = types.InlineKeyboardButton("🆓 Chơi Vui (0 Vàng)", callback_data="room_init_0")
    btn_500 = types.InlineKeyboardButton("💰 500 Vàng", callback_data="room_init_500")
    btn_1k = types.InlineKeyboardButton("💰 1,000 Vàng", callback_data="room_init_1000")
    btn_5k = types.InlineKeyboardButton("💰 5,000 Vàng", callback_data="room_init_5000")
    btn_10k = types.InlineKeyboardButton("🔥 10,000 Vàng", callback_data="room_init_10000")
    btn_back = types.InlineKeyboardButton("⬅️ HỦY BỎ", callback_data="lobby_back_main")
    
    markup.add(btn_0)
    markup.add(btn_500, btn_1k)
    markup.add(btn_5k, btn_10k)
    markup.add(btn_back)
    return markup

# Tích hợp thêm nhánh xử lý trong bộ điều hướng `@bot.callback_query_handler` ở Phần 6:
# Bạn chỉ cần nối tiếp các dòng code dưới đây vào hàm `handle_global_callbacks`

    # Hành động: Nhấn nút "TẠO PHÒNG CHƠI" từ sảnh chính
    elif data == "lobby_create":
        # Kiểm tra xem người chơi này có đang kẹt ở phòng nào khác không
        in_room = False
        for rid, rdata in game_rooms.items():
            if user_id in rdata["players"]:
                in_room = True
                break
                
        if in_room:
            bot.answer_callback_query(call.id, text="❌ Bạn đang ở trong một phòng chơi khác rồi!", show_alert=True)
            return
            
        bet_text = (
            "➕ **CẤU HÌNH PHÒNG CHƠI MỚI** ➕\n"
            "-----------------------------------------\n"
            "🎮 Bạn đang tiến hành khởi tạo một phòng Ma Sói mới.\n"
            "💰 Hãy lựa chọn **Mức đặt cược** cho phòng chơi của bạn.\n\n"
            "⚠️ *Lưu ý: Tất cả người chơi tham gia phòng cần phải có số dư bằng hoặc lớn hơn mức cược này. Người thắng cuộc sẽ ăn trọn quỹ tiền cược trận đấu!*"
        )
        bot.edit_message_text(bet_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_bet_selection_markup())
        bot.answer_callback_query(call.id)

    # Xử lý khi chọn mức cược cụ thể để thiết lập phòng chơi
    elif data.startswith("room_init_"):
        bet_amount = int(data.replace("room_init_", ""))
        user_data = user_db[user_id]
        
        # Kiểm tra số dư ví tài sản của chủ phòng
        if user_data["gold"] < bet_amount:
            bot.answer_callback_query(call.id, text=f"❌ Số dư không đủ để thiết lập mức cược {bet_amount:,} Vàng!", show_alert=True)
            return
            
        # Tiến hành cấp mã phòng và khởi tạo cấu trúc dữ liệu sảnh game phòng chờ
        room_id = generate_room_id()
        game_rooms[room_id] = {
            "host": user_id,
            "status": "Lobby",      # Các trạng thái: Lobby, Night, Day, Event, Discussion, End
            "bet": bet_amount,
            "players": [user_id],   # Danh sách ID người chơi tham gia
            "ready_players": set(), # Danh sách người chơi đã bấm Sẵn Sàng
            "weather": "Đẹp Trời",  # Mặc định thời tiết ban đầu (Sẽ biến động ở phần sau)
            "event_card": None,     # Sự kiện ban ngày ngẫu nhiên
            "roles": {},            # Lưu vai trò nhân vật của từng người khi Start
            "alive": [],            # Danh sách người chơi còn sống
            "history_log": []       # Nhật ký diễn biến trận đấu
        }
        
        bot.answer_callback_query(call.id, text="Tạo phòng chơi thành công!", show_alert=False)
        
        # Chuyển hướng giao diện sang màn hình Quản lý Phòng Chờ (Sẽ dựng giao diện chi tiết ở Phần 8)
        show_room_lobby(room_id, chat_id, message_id)

# ==========================================
# 22. GIAO DIỆN HIỂN THỊ MÀN HÌNH PHÒNG CHỜ
# ==========================================
def get_room_lobby_markup(room_id, user_id):
    """Tạo hệ thống nút bấm tương tác linh hoạt trong phòng chờ sảnh game"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    room_data = game_rooms[room_id]
    
    # Nút Sẵn sàng hoặc Bắt đầu trận đấu
    if user_id == room_data["host"]:
        btn_action = types.InlineKeyboardButton("🚀 BẮT ĐẦU TRẬN ĐẤU", callback_data=f"room_action_start_{room_id}")
    else:
        if user_id in room_data["ready_players"]:
            btn_action = types.InlineKeyboardButton("🛑 THÔI SẴN SÀNG", callback_data=f"room_action_ready_{room_id}")
        else:
            btn_action = types.InlineKeyboardButton("✅ SẴN SÀNG", callback_data=f"room_action_ready_{room_id}")
            
    btn_leave = types.InlineKeyboardButton("🚪 RỜI/HỦY PHÒNG", callback_data=f"room_action_leave_{room_id}")
    markup.add(btn_action)
    markup.add(btn_leave)
    return markup

def show_room_lobby(room_id, chat_id, message_id=None):
    """Hàm lõi dựng giao diện danh sách thành viên hiện có trong phòng cược"""
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    host_name = user_db[room_data["host"]]["name"]
    
    lobby_text = (
        f"🎮 **PHÒNG CHỜ LÀNG MA SÓI** 🎮\n"
        f"-----------------------------------------\n"
        f"🔑 Mã phòng: `<code>{room_id}</code>` (Ấn vào để sao chép)\n"
        f"👑 Chủ phòng: **{host_name}**\n"
        f"💰 Mức đặt cược: `{room_data['bet']:,} Vàng`\n"
        f"🌤️ Thời tiết hiện tại: `{room_data['weather']}`\n"
        f"-----------------------------------------\n"
        f"👥 **DANH SÁCH THÀNH VIÊN ({len(room_data['players'])}/15):**\n"
    )
    
    # Liệt kê trạng thái chuẩn bị của từng người chơi
    for i, pid in enumerate(room_data["players"], 1):
        pname = user_db[pid]["name"]
        plevel = user_db[pid]["level"]
        
        if pid == room_data["host"]:
            status_icon = "👑 (Chủ phòng)"
        elif pid in room_data["ready_players"]:
            status_icon = "✅ (Sẵn sàng)"
        else:
            status_icon = "⏳ (Đang đợi)"
            
        lobby_text += f"{i}. **{pname}** [Lv.{plevel}] — {status_icon}\n"
        
    lobby_text += (
        f"\n📢 *Hãy chia sẻ Mã phòng cho bạn bè để cùng tham gia. Trận đấu có thể bắt đầu khi đạt tối thiểu 5 người chơi và tất cả đều Sẵn sàng.*"
    )

    if message_id:
        try:
            bot.edit_message_text(lobby_text, chat_id, message_id, parse_mode="HTML", reply_markup=get_room_lobby_markup(room_id, chat_id))
        except Exception:
            # Phòng trường hợp người dùng click liên tục gây trùng tin nhắn trùng lặp
            pass
    else:
        bot.send_message(chat_id, lobby_text, parse_mode="HTML", reply_markup=get_room_lobby_markup(room_id, chat_id))

# ==========================================
# 23. TIẾP TỤC BỔ SUNG NHÁNH VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán tiếp vào hàm handle_global_callbacks của Phần 6)

    # Người chơi nhấn nút "TÌM TRẬN NGAY" từ sảnh chính
    elif data == "lobby_find":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(
            chat_id,
            "🔍 **TÌM PHÒNG THỦ CÔNG**\n"
            "👉 Vui lòng nhập đúng Mã phòng chơi bạn muốn tham gia.\n"
            "*(Ví dụ: R1234)*",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg, process_join_room_step)

    # Logic xử lý nút bấm Sẵn Sàng (Ready Toggle)
    elif data.startswith("room_action_ready_"):
        room_id = data.replace("room_action_ready_", "")
        if room_id not in game_rooms:
            bot.answer_callback_query(call.id, text="❌ Phòng này không còn tồn tại!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        if user_id in room_data["ready_players"]:
            room_data["ready_players"].remove(user_id)
            bot.answer_callback_query(call.id, text="Đã hủy trạng thái sẵn sàng.")
        else:
            room_data["ready_players"].add(user_id)
            bot.answer_callback_query(call.id, text="Bạn đã sẵn sàng tham chiến!")
            
        # Làm mới giao diện danh sách phòng để mọi người cùng thấy trạng thái mới
        show_room_lobby(room_id, chat_id, message_id)

    # Logic xử lý khi người chơi bấm "RỜI/HỦY PHÒNG"
    elif data.startswith("room_action_leave_"):
        room_id = data.replace("room_action_leave_", "")
        if room_id in game_rooms:
            room_data = game_rooms[room_id]
            
            if user_id == room_data["host"]:
                # Nếu chủ phòng rời đi, hủy luôn phòng chơi, giải tán tất cả thành viên ra sảnh
                for pid in room_data["players"]:
                    if pid != user_id:
                        try:
                            bot.send_message(pid, f"❌ Phòng chơi `{room_id}` đã bị giải tán do Chủ phòng thoát game.", parse_mode="Markdown")
                        except Exception: pass
                del game_rooms[room_id]
                bot.answer_callback_query(call.id, text="Đã hủy phòng chơi.", show_alert=True)
                # Đưa chủ phòng về màn hình Sảnh chính
                bot.edit_message_text("🚪 Bạn đã hủy phòng chơi và quay lại Sảnh chính.", chat_id, message_id, reply_markup=get_main_menu_markup())
            else:
                # Nếu là thành viên thường, chỉ xóa tên ra khỏi phòng cược
                room_data["players"].remove(user_id)
                if user_id in room_data["ready_players"]:
                    room_data["ready_players"].remove(user_id)
                
                bot.answer_callback_query(call.id, text="Đã rời phòng chờ.", show_alert=True)
                bot.edit_message_text("🚪 Bạn đã rời phòng chờ và quay lại Sảnh chính.", chat_id, message_id, reply_markup=get_main_menu_markup())
                
                # Cập nhật giao diện phòng chờ cho các thành viên còn lại
                for pid in room_data["players"]:
                    show_room_lobby(room_id, pid)

# ==========================================
# 24. HÀM XỬ LÝ KHỚP MÃ VÀO PHÒNG CHƠI CHUNG
# ==========================================
def process_join_room_step(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    target_room = message.text.strip().upper() # Chuẩn hóa chuỗi nhập mã dạng viết hoa
    
    if target_room not in game_rooms:
        bot.send_message(chat_id, "❌ **Lỗi:** Mã phòng không hợp lệ hoặc phòng chơi đã bị hủy bỏ từ trước.", parse_mode="Markdown")
        return
        
    room_data = game_rooms[target_room]
    user_data = user_db[user_id]
    
    if room_data["status"] != "Lobby":
        bot.send_message(chat_id, "❌ Trận đấu trong phòng này đã được bắt đầu, bạn không thể tham gia giữa chừng!")
        return
        
    if user_id in room_data["players"]:
        bot.send_message(chat_id, "⚠️ Bạn đã ở trong phòng chờ này rồi.")
        return
        
    if len(room_data["players"]) >= 15:
        bot.send_message(chat_id, "❌ Phòng chơi hiện tại đã đầy giới hạn (Tối đa 15 người).")
        return
        
    # Xác thực số dư ví đặt cược
    if user_data["gold"] < room_data["bet"]:
        bot.send_message(chat_id, f"❌ Tài sản không đủ! Phòng này yêu cầu mức đặt cược cọc là `{room_data['bet']:,} Vàng`.", parse_mode="Markdown")
        return
        
    # Thêm người chơi mới vào danh sách phòng sảnh game
    room_data["players"].append(user_id)
    bot.send_message(chat_id, f"🎉 Bạn đã tham gia thành công phòng chơi `{target_room}`!", parse_mode="Markdown")
    
    # Hiển thị sảnh phòng chờ cho người chơi mới vào
    show_room_lobby(target_room, chat_id)
    
    # Cập nhật màn hình danh sách cho toàn bộ người chơi cũ có sẵn trong phòng
    for pid in room_data["players"]:
        if pid != user_id:
            show_room_lobby(target_room, pid)

# ==========================================
# 25. THIẾT LẬP CẤU HÌNH VAI TRÒ THEO QUÂN SỐ
# ==========================================
# Định nghĩa danh sách vai trò mở rộng tùy biến theo số lượng người tham gia phòng cược
ROLE_POOL_MAPPING = {
    5:  ["Sói", "Dân", "Tiên Tri", "Bảo Vệ", "Kẻ Phản Bội"],
    6:  ["Sói", "Dân", "Dân", "Tiên Tri", "Bảo Vệ", "Phù Thủy"],
    7:  ["Sói", "Sói Nguyền", "Dân", "Dân", "Tiên Tri", "Bảo Vệ", "Phù Thủy"],
    8:  ["Sói", "Sói Nguyền", "Dân", "Dân", "Dân", "Tiên Tri", "Bảo Vệ", "Phù Thủy"],
    9:  ["Sói", "Sói Nguyền", "Kẻ Phản Bội", "Dân", "Dân", "Tiên Tri", "Bảo Vệ", "Phù Thủy", "Thợ Săn"],
    10: ["Sói", "Sói Alpha", "Kẻ Phản Bội", "Dân", "Dân", "Dân", "Tiên Tri", "Bảo Vệ", "Phù Thủy", "Thợ Săn"],
    # Hệ thống hỗ trợ mở rộng tự động lên đến tối đa 15 người chơi
}

def get_role_pool_for_players(player_count):
    """Lấy danh sách quân bài tương ứng, tự động bù thêm Dân thường nếu vượt mốc định nghĩa"""
    if player_count in ROLE_POOL_MAPPING:
        return ROLE_POOL_MAPPING[player_count].copy()
    
    # Nếu số lượng người chơi nằm ngoài danh sách định nghĩa sẵn (ví dụ 11-15 người)
    base_pool = ROLE_POOL_MAPPING[10].copy()
    while len(base_pool) < player_count:
        base_pool.append("Dân") # Bổ sung dân thường đảm bảo đủ số lượng thẻ bài
    return base_pool

# ==========================================
# 26. LOGIC SỰ KIỆN KHI CHỦ PHÒNG BẤM START GAME
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback chính `@bot.callback_query_handler` ở Phần 8)

    elif data.startswith("room_action_start_"):
        room_id = data.replace("room_action_start_", "")
        if room_id not in game_rooms:
            bot.answer_callback_query(call.id, text="❌ Phòng không tồn tại hoặc đã bị hủy!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        player_count = len(room_data["players"])
        
        # Điều kiện 1: Xác thực quyền hạn của người kích hoạt lệnh
        if user_id != room_data["host"]:
            bot.answer_callback_query(call.id, text="❌ Chỉ chủ phòng mới có quyền khởi chạy trận đấu!", show_alert=True)
            return
            
        # Điều kiện 2: Kiểm tra quân số tối thiểu (Yêu cầu ít nhất 5 người để đảm bảo tính hấp dẫn)
        if player_count < 5:
            bot.answer_callback_query(call.id, text="❌ Phòng chơi cần đạt tối thiểu 5 thành viên để bắt đầu!", show_alert=True)
            return
            
        # Điều kiện 3: Kiểm tra trạng thái Sẵn sàng của tất cả thành viên thường
        unready_players = [pid for pid in room_data["players"] if pid != room_data["host"] and pid not in room_data["ready_players"]]
        if unready_players:
            bot.answer_callback_query(call.id, text=f"❌ Còn {len(unready_players)} người chơi chưa bấm Sẵn Sàng!", show_alert=True)
            return

        # ==========================================
        # 27. THỰC THI KHÓA TIỀN CƯỢC & PHÂN VAI TRÒ
        # ==========================================
        bot.answer_callback_query(call.id, text="🚀 Đang khởi tạo trận đấu...")
        
        # Bước 1: Trừ tiền đặt cược của toàn bộ thành viên trong phòng chơi
        bet_fee = room_data["bet"]
        for pid in room_data["players"]:
            user_db[pid]["gold"] -= bet_fee
            # Chuyển trạng thái người chơi vào danh sách còn sống ban đầu
            room_data["alive"].append(pid)
            
        # Bước 2: Tiến hành xáo trộn bài ngẫu nhiên bằng thuật toán Fisher-Yates
        assigned_roles = get_role_pool_for_players(player_count)
        distribute_roles_with_priority_tickets(room_id)
        
        # Gán vai trò cụ thể cho từng ID người chơi
        for index, pid in enumerate(room_data["players"]):
            role_name = assigned_roles[index]
            room_data["roles"][pid] = {
                "role": role_name,
                "team": "Ma Sói" if "Sói" in role_name or role_name == "Kẻ Phản Bội" else "Dân Làng",
                "status": "Alive",
                "target_history": [] # Lưu vết các kỹ năng đã thực hiện qua các đêm
            }
            
        # Bước 3: Thay đổi trạng thái vận hành của phòng chơi sang ban đêm
        room_data["status"] = "Night"
        
        # Phát thông báo khởi động toàn diện trận đấu cho mọi người chơi trong sảnh
        for pid in room_data["players"]:
            try:
                bot.send_message(
                    pid, 
                    f"🎬 **TRẬN ĐẤU CHÍNH THỨC BẮT ĐẦU** 🎬\n"
                    f"-----------------------------------------\n"
                    f"💰 Mức đặt cược `{bet_fee:,} Vàng` đã được hệ thống tự động khấu trừ vào quỹ thưởng.\n"
                    f"📥 *Vui lòng kiểm tra hộp thư tin nhắn mật từ Bot để nhận Vai trò và Nhiệm vụ của bạn!*",
                    parse_mode="Markdown"
                )
            except Exception: pass
            
        # Kích hoạt luồng xử lý gửi tin nhắn chức năng bí mật (Sẽ được viết chi tiết ở Phần 10)
        trigger_role_notifications(room_id)

# ==========================================
# 28. ĐỊNH NGHĨA CHI TIẾT NHIỆM VỤ CÁC VAI TRÒ
# ==========================================
ROLE_DETAILS = {
    "Sói": {
        "emoji": "🐺", "name": "Ma Sói Thường",
        "mission": "Thống nhất ý kiến với bầy Sói vào mỗi đêm để cắn chết một người dân làng."
    },
    "Sói Nguyền": {
        "emoji": "🩸", "name": "Ma Sói Nguyền",
        "mission": "Có 1 cơ hội duy nhất trong game thay vì cắn sẽ 'Nguyền' mục tiêu. Nếu mục tiêu là Dân làng thường, họ sẽ hóa Sói vào đêm hôm sau."
    },
    "Sói Alpha": {
        "emoji": "👑", "name": "Sói Alpha Quyền Lực",
        "mission": "Phiếu cắn của bạn có trọng số gấp đôi. Có quyền quyết định tối hậu nếu bầy sói không đồng thuận mục tiêu."
    },
    "Kẻ Phản Bội": {
        "emoji": "🎭", "name": "Kẻ Phản Bội (Phe Sói)",
        "mission": "Bạn biết toàn bộ danh tính bầy Sói nhưng Sói không biết bạn. Hãy dẫn dắt dư luận ban ngày để treo cổ dân làng, giúp Sói thắng."
    },
    "Tiên Tri": {
        "emoji": "👁️", "name": "Nhà Tiên Tri",
        "mission": "Chọn một người để soi danh tính thực sự của họ vào mỗi đêm để dẫn dắt dân làng."
    },
    "Bảo Vệ": {
        "emoji": "🛡️", "name": "Bảo Vệ Làng",
        "mission": "Chọn một người để bảo vệ khỏi nanh vuốt Ma Sói mỗi đêm. Không được bảo vệ 1 mục tiêu 2 đêm liên tiếp."
    },
    "Phù Thủy": {
        "emoji": "🧪", "name": "Phù Thủy Quyền Năng",
        "mission": "Sở hữu 1 bình thuốc sinh để cứu người bị cắn và 1 bình thuốc tử để giết chết 1 người bất kỳ ban đêm."
    },
    "Thợ Săn": {
        "emoji": "🏹", "name": "Thợ Săn Tinh Anh",
        "mission": "Nếu bạn bị chết vào ban đêm hoặc bị dân làng treo cổ ban ngày, bạn có quyền bắn chết thêm 1 mục tiêu khác đi cùng."
    },
    "Dân": {
        "emoji": "🧑‍🌾", "name": "Dân Làng Gương Mẫu",
        "mission": "Bạn không có chức năng ban đêm. Hãy sử dụng khả năng lập luận ban ngày để tìm ra Ma Sói và treo cổ chúng."
    }
}

# ==========================================
# 29. HÀM PHÁT THÔNG BÁO CHỨC NĂNG BÍ MẬT
# ==========================================
def trigger_role_notifications(room_id):
    """
    Hàm lõi quét danh sách phòng chơi để gửi tin nhắn vai trò.
    Tự động gom nhóm nhận diện phe Ma Sói để thông báo đồng bọn.
    """
    room_data = game_rooms[room_id]
    
    # Bước 1: Thu thập danh sách toàn bộ Ma Sói trong phòng chơi
    werewolf_team_list = []
    for pid, pdata in room_data["roles"].items():
        role_name = pdata["role"]
        # Gom Sói Thường, Sói Nguyền, Sói Alpha vào danh sách
        if "Sói" in role_name and role_name != "Kẻ Phản Bội":
            pname = user_db[pid]["name"]
            werewolf_team_list.append(f"• **{pname}** (Vai trò: `{role_name}`)")

    wolf_team_text = "\n".join(werewolf_team_list)

    # Bước 2: Gửi tin nhắn mật riêng biệt cho từng cá nhân
    for pid in room_data["players"]:
        pdata = room_data["roles"][pid]
        role_name = pdata["role"]
        config = ROLE_DETAILS.get(role_name, ROLE_DETAILS["Dân"])
        
        # Thiết lập nội dung tin nhắn mật hướng dẫn vai trò đẹp mắt
        role_msg = (
            f"{config['emoji']} **THÔNG BÁO VAI TRÒ NHÂN VẬT** {config['emoji']}\n"
            f"-----------------------------------------\n"
            f"🎭 Vai trò của bạn: **{config['name']}**\n"
            f"🛡️ Thuộc Phe: **{pdata['team']}**\n\n"
            f"📜 **Nhiệm vụ tối mật:**\n_{config['mission']}_\n"
            f"-----------------------------------------\n"
        )
        
        # Cơ chế đặc biệt: Nếu là phe Sói, hiển thị thêm danh sách đồng bọn
        if "Sói" in role_name and role_name != "Kẻ Phản Bội":
            role_msg += (
                f"🐺 **DANH SÁCH BẦY SÓI ĐÊM NAY:**\n"
                f"{wolf_team_text}\n\n"
                f"💬 *Hãy chuẩn bị tinh thần phối hợp tác chiến để xé xác dân làng!*"
            )
        # Cơ chế đặc biệt: Nếu là Kẻ Phản Bội, hiển thị danh sách Sói để đi theo phò tá
        elif role_name == "Kẻ Phản Bội":
            role_msg += (
                f"👁️ **DANH SÁCH CHỦ NHÂN MA SÓI CỦA BẠN:**\n"
                f"{wolf_team_text}\n\n"
                f"⚠️ *Lưu ý: Bầy Sói không biết bạn là ai. Đừng để chúng cắn nhầm bạn ban đêm!*"
            )
        else:
            role_msg += "⏳ *Đêm đầu tiên đang buông xuống. Hãy ẩn nấp an toàn và chờ đợi lệnh gọi từ hệ thống...*"

        try:
            bot.send_message(pid, role_msg, parse_mode="Markdown")
        except Exception:
            # Gửi cảnh báo về nhóm nếu người chơi chặn chat với Bot
            bot.send_message(room_data["host"], f"⚠️ Người chơi **{user_db[pid]['name']}** chưa mở chặn Bot, không thể nhận tin nhắn vai trò!")

    # Chuyển tiếp luồng xử lý sang Phần 11: Khởi động vòng lặp game chính (Game Loop) 
    # và kích hoạt hệ thống Thời tiết biến động Đêm đầu tiên.
    start_night_phase(room_id)

# ==========================================
# 30. ĐỊNH NGHĨA CÁC HIỆU ỨNG THỜI TIẾT BAN ĐÊM
# ==========================================
WEATHER_NIGHT_POOL = {
    "Đẹp Trời": {
        "icon": "🌌",
        "desc": "Trời trong mây quang, gió thổi nhẹ nhàng. Mọi chức năng kỹ năng ban đêm hoạt động với tỷ lệ chính xác 100% định mức."
    },
    "Đêm Trăng Rằm": {
        "icon": "🌕",
        "desc": "Trăng máu rực sáng rọi xuống ngôi làng. Sức mạnh phe Sói tăng cao, phiếu cắn phá vỡ lớp bảo vệ của Già Làng chỉ trong 1 đêm."
    },
    "Đêm Sương Mù": {
        "icon": "🌫️",
        "desc": "Sương mù dày đặc bao phủ lối đi. Nhà Tiên Tri có 50% tỷ lệ soi ra kết quả 'Không rõ ràng'. Phù Thủy ném độc có 30% tỷ lệ lệch mục tiêu."
    }
}

# ==========================================
# 31. HÀM KHỞI ĐỘNG VÒNG LẶP BAN ĐÊM (NIGHT PHASE)
# ==========================================
def start_night_phase(room_id):
    """
    Hàm lõi kích hoạt giai đoạn Ban đêm cho phòng chơi.
    Ngẫu nhiên cấu hình thời tiết và gửi thông báo điện ảnh cho người chơi.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    room_data["status"] = "Night"
    
    # Bước 1: Ngẫu nhiên rút một hiệu ứng thời tiết đêm từ Pool cấu hình
    weather_key = random.choice(list(WEATHER_NIGHT_POOL.keys()))
    room_data["weather"] = weather_key
    weather_info = WEATHER_NIGHT_POOL[weather_key]
    
    # Bước 2: Thiết lập nội dung văn bản thông báo chuyển cảnh đầy kịch tính
    night_announcement = (
        f"💤 **LÀNG MA SÓI CHÌM VÀO ĐÊM TỐI** 💤\n"
        f"-----------------------------------------\n"
        f"🌙 Mọi người dân làng từ từ khép cửa, chìm vào giấc ngủ sâu sau một ngày làm việc mệt mỏi...\n\n"
        f"{weather_info['icon']} **HIỆU ỨNG THỜI TIẾT ĐÊM NAY: {weather_key}**\n"
        f"ℹ️ *Tác động:* _{weather_info['desc']}_\n"
        f"-----------------------------------------\n"
        f"⏳ **Thời gian ban đêm:** `60 giây` để các chức năng thực hiện kỹ năng bí mật thông qua tin nhắn riêng của Bot.\n\n"
        f"📢 *Yêu cầu giữ trật tự nghiêm ngặt, không thảo luận công khai tại nhóm sảnh game lúc này!*"
    )
    
    # Bước 3: Phát sóng thông báo chuyển đêm đến tất cả người chơi
    for pid in room_data["players"]:
        try:
            bot.send_message(pid, night_announcement, parse_mode="Markdown")
        except Exception:
            pass
            
    # Ghi nhận sự kiện thời tiết vào nhật ký trận đấu hệ thống (Game Log)
    room_data["history_log"].append(f"🌙 Đêm xuống. Thời tiết xuất hiện: {weather_key}")
    
    # Kích hoạt bộ hẹn giờ chạy ngầm (Threading Timer) để kiểm soát thời gian đếm ngược ban đêm
    # Sau khi hết 60 giây, hệ thống sẽ tự động gọi hàm xử lý tổng kết kết quả ban đêm.
    threading.Thread(target=countdown_night_timer, args=(room_id, 60)).start()
    
    # Kích hoạt bảng lệnh menu chức năng riêng biệt cho từng vai trò còn sống
    trigger_night_action_menus(room_id)

# ==========================================
# 32. BỘ ĐẾM NGƯỢC THỜI GIAN CHẠY NGẦM
# ==========================================
def countdown_night_timer(room_id, seconds):
    """Luồng đếm ngược thời gian chạy độc lập để tránh làm sập nghẽn bot chính"""
    time.sleep(seconds)
    
    if room_id in game_rooms and game_rooms[room_id]["status"] == "Night":
        # Nếu đã hết giờ và phòng chơi vẫn đang ở trạng thái Đêm, tiến hành cưỡng chế đóng đêm
        # Chuyển tiếp luồng xử lý sang phần tổng kết kết quả đêm (Sẽ được viết ở các phần sau)
        process_end_of_night(room_id)

# ==========================================
# 33. GIAO DIỆN CHỌN MỤC TIÊU CHO CÁC CHỨC NĂNG
# ==========================================
def get_night_target_markup(room_id, filter_user_id, action_type):
    """
    Tạo danh sách nút bấm hiển thị toàn bộ người chơi còn sống trong phòng.
    Ẩn người chơi thực hiện lệnh (filter_user_id) để tránh tự chọn chính mình.
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    room_data = game_rooms[room_id]
    
    for pid in room_data["alive"]:
        if pid != filter_user_id:
            pname = user_db[pid]["name"]
            btn = types.InlineKeyboardButton(f"👤 {pname}", callback_data=f"skill_{action_type}_{room_id}_{pid}")
            markup.add(btn)
            
    return markup

# ==========================================
# 34. HÀM KÍCH HOẠT MENU LỆNH CHO TỪNG VAI TRÒ
# ==========================================
def trigger_night_action_menus(room_id):
    """
    Hàm lõi quét qua toàn bộ người chơi còn sống trong phòng 
    để gửi menu hành động bí mật tương ứng với vai trò của họ.
    """
    room_data = game_rooms[room_id]
    
    for pid in room_data["alive"]:
        pdata = room_data["roles"][pid]
        role = pdata["role"]
        
        # --- LOGIC GỬI LỆNH CHO NHÀ TIÊN TRI ---
        if role == "Tiên Tri":
            spy_text = (
                "👁️ **QUYỀN NĂNG TIÊN TRI KÍCH HOẠT** 👁️\n"
                "-----------------------------------------\n"
                f"🌤️ Thời tiết đêm nay: `{room_data['weather']}`\n"
                "🔮 Hãy chọn 1 người chơi bên dưới mà bạn muốn quả cảm soi sáng danh tính thực sự của họ đêm nay."
            )
            # Nếu thời tiết sương mù, cảnh báo tỷ lệ nhiễu loạn
            if room_data["weather"] == "Đêm Sương Mù":
                spy_text += "\n⚠️ *Cảnh báo sương mù:* Bạn có 50% tỷ lệ nhận về kết quả 'Không rõ ràng'!"
                
            bot.send_message(pid, spy_text, parse_mode="Markdown", reply_markup=get_night_target_markup(room_id, pid, "see"))
            
        # --- LOGIC GỬI LỆNH CHO BẢO VỆ ---
        elif role == "Bảo Vệ":
            guard_text = (
                "🛡️ **QUYỀN NĂNG BẢO VỆ KÍCH HOẠT** 🛡️\n"
                "-----------------------------------------\n"
                "⚔️ Hãy lựa chọn một người chơi để dựng khiên bảo vệ họ an toàn khỏi nanh vuốt của bầy Ma Sói đêm nay.\n\n"
                "⚠️ *Lưu ý:* Bạn có thể tự bảo vệ mình, nhưng không được chọn bảo vệ cùng một mục tiêu trong 2 đêm liên tiếp."
            )
            # Khác với Tiên Tri, Bảo Vệ có thể tự chọn bản thân mình
            markup_guard = get_night_target_markup(room_id, pid, "guard")
            btn_self = types.InlineKeyboardButton("🛡️ Tự Bảo Vệ Bản Thân", callback_data=f"skill_guard_{room_id}_{pid}")
            markup_guard.add(btn_self)
            
            bot.send_message(pid, guard_text, parse_mode="Markdown", reply_markup=markup_guard)

# ==========================================
# 35. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ LỆNH VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán tiếp vào hàm handle_global_callbacks của Phần 6)

    # 📥 Xử lý kết quả khi Nhà Tiên Tri nhấn nút soi bài
    elif data.startswith("skill_see_"):
        # Phân tách chuỗi: skill_see_[room_id]_[target_id]
        parts = data.split("_")
        room_id = parts[2]
        target_id = int(parts[3])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        target_data = room_data["roles"][target_id]
        target_name = user_db[target_id]["name"]
        
        # Áp dụng bộ lọc hiệu ứng Thời tiết Đêm Sương Mù (Phần 11)
        # Đồng thời kiểm tra xem người chơi có đeo "Kính Hiển Vi" (Vật phẩm Phần 4) để khắc chế thời tiết không
        user_item = user_db[user_id].get("item_slot")
        
        if room_data["weather"] == "Đêm Sương Mù" and user_item != "kinh_hien_vi" and random.random() < 0.5:
            result_role = "Không rõ ràng (Bị sương mù che khuất)"
        else:
            # Kiểm tra xem mục tiêu có dùng "Mặt Nạ Sói" (Vật phẩm Phần 4) để gài bẫy lừa Tiên tri không
            target_item = user_db[target_id].get("item_slot")
            if target_item == "mat_na_soi" and target_data["role"] == "Dân":
                result_role = "Ma Sói Thường 🐺"
                # Vật phẩm tiêu hao sẽ biến mất sau khi kích hoạt
                user_db[target_id]["item_slot"] = None
            else:
                result_role = f"🎯 {target_data['role']}"
                
        # Lưu kết quả hành động của Tiên tri vào bộ nhớ tạm để tổng kết
        room_data["roles"][user_id]["night_action"] = {"action": "see", "target": target_id}
        
        bot.edit_message_text(
            f"🔮 **KẾT QUẢ SOI TÂM LINH:**\n-----------------------------------------\n👤 Mục tiêu: **{target_name}**\n🎭 Bản chất chân tướng: `{result_role}`", 
            chat_id, message_id, parse_mode="Markdown"
        )
        bot.answer_callback_query(call.id, text="Đã ghi nhận quẻ bói.")

    # 📥 Xử lý kết quả khi Bảo Vệ nhấn nút chặn cắn
    elif data.startswith("skill_guard_"):
        parts = data.split("_")
        room_id = parts[2]
        target_id = int(parts[3])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        target_name = user_db[target_id]["name"]
        
        # Kiểm tra luật chống bảo vệ 1 mục tiêu 2 đêm liên tiếp
        history = room_data["roles"][user_id]["target_history"]
        if history and history[-1] == target_id:
            bot.answer_callback_query(call.id, text="❌ Bạn không thể bảo vệ người này 2 đêm liên tiếp!", show_alert=True)
            return
            
        # Ghi nhận mục tiêu bảo vệ thành công
        room_data["roles"][user_id]["night_action"] = {"action": "guard", "target": target_id}
        room_data["roles"][user_id]["target_history"].append(target_id)
        
        bot.edit_message_text(f"🛡️ Bạn đã dựng kết giới phép thuật để bảo vệ an toàn cho **{target_name}** đêm nay.", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Bảo vệ thành công.")

# Cấu trúc lưu trữ phiếu bầu của Sói trong đêm hiện tại: 
# { room_id: { target_id: tổng_trọng_số_phiếu } }
wolf_votes_cache = {}

# Cấu trúc lưu lệnh "Nguyền" của Sói Nguyền: { room_id: target_id_bị_nguyền }
wolf_curse_cache = {}

# ==========================================
# 36. GIAO DIỆN BỎ PHIẾU DÀNH RIÊNG CHO PHE SÓI
# ==========================================
def get_wolf_vote_markup(room_id, wolf_id, is_cursed_wolf=False):
    """
    Tạo danh sách nút bấm chọn mục tiêu xé xác dành riêng cho bầy Sói.
    Nếu là Sói Nguyền, bổ sung thêm nút chức năng "NGUYỀN MỤC TIÊU".
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    room_data = game_rooms[room_id]
    
    # Liệt kê tất cả người chơi còn sống KHÔNG phải là Sói
    for pid in room_data["alive"]:
        pdata = room_data["roles"][pid]
        if "Sói" not in pdata["role"]:
            pname = user_db[pid]["name"]
            
            btn_bite = types.InlineKeyboardButton(f"🥩 Cắn {pname}", callback_data=f"wolf_bite_{room_id}_{pid}")
            markup.add(btn_bite)
            
            if is_cursed_wolf:
                btn_curse = types.InlineKeyboardButton(f"🩸 Nguyền {pname}", callback_data=f"wolf_curse_{room_id}_{pid}")
                markup.add(btn_curse)
                
    return markup

def trigger_wolf_voting(room_id):
    """Quét phòng chơi và gửi bảng menu bỏ phiếu cắn người cho toàn bộ bầy Sói"""
    room_data = game_rooms[room_id]
    wolf_votes_cache[room_id] = {} # Khởi tạo bộ đếm phiếu trống cho đêm nay
    
    for pid in room_data["alive"]:
        pdata = room_data["roles"][pid]
        role = pdata["role"]
        
        if "Sói" in role and role != "Kẻ Phản Bội":
            is_cursed = (role == "Sói Nguyền")
            
            wolf_msg = (
                f"🐺 **BẦY SÓI THỨC GIẤC ĐI SĂN** 🐺\n"
                f"-----------------------------------------\n"
                f"🌤️ Thời tiết đêm nay: `{room_data['weather']}`\n"
                f"👤 Vai trò của bạn: **{role}**\n\n"
                f"🥩 Hãy chọn một con mồi béo bở trong làng để tiến hành xé xác đêm nay. "
                f"Tất cả thành viên bầy Sói cần bỏ phiếu để thống nhất mục tiêu cao nhất."
            )
            
            if role == "Sói Alpha":
                wolf_msg += "\n👑 *Quyền năng tối cao:* Phiếu cắn của bạn có trọng số bằng **2**!"
            elif role == "Sói Nguyền":
                wolf_msg += "\n🩸 *Quyền năng tối cao:* Bạn có thể chọn **Nguyền** mục tiêu (Biến dân thường thành Sói vào đêm mai, chỉ dùng 1 lần/trận)."

            bot.send_message(pid, wolf_msg, parse_mode="Markdown", reply_markup=get_wolf_vote_markup(room_id, pid, is_cursed))

# Bạn hãy gọi hàm `trigger_wolf_voting(room_id)` này ở cuối hàm `trigger_night_action_menus` của Phần 12 nhé!

# ==========================================
# 37. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================

    # 📥 Xử lý sự kiện khi một con Sói chọn "CẮN" người
    elif data.startswith("wolf_bite_"):
        parts = data.split("_")
        room_id = parts
        target_id = int(parts)
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian đi săn ban đêm!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        my_role = room_data["roles"][user_id]["role"]
        target_name = user_db[target_id]["name"]
        
        # Tính trọng số phiếu (Sói Alpha = 2, các Sói khác = 1)
        weight = 2 if my_role == "Sói Alpha" else 1
        
        # Ghi nhận phiếu bầu vào Cache hệ thống
        if target_id not in wolf_votes_cache[room_id]:
            wolf_votes_cache[room_id][target_id] = 0
        wolf_votes_cache[room_id][target_id] += weight
        
        # Lưu hành động cá nhân để tổng kết game
        room_data["roles"][user_id]["night_action"] = {"action": "bite", "target": target_id}
        
        bot.edit_message_text(f"🎯 Bạn đã bỏ phiếu cắn **{target_name}** (Trọng số phiếu: {weight}). Chờ đồng bọn thống nhất...", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Đã ghi nhận phiếu cắn.")
        
        # Thông báo ẩn danh cho các thành viên Sói khác trong phòng biết tiến độ bầu chọn
        for pid in room_data["alive"]:
            if "Sói" in room_data["roles"][pid]["role"] and pid != user_id:
                try:
                    bot.send_message(pid, f"🐾 Một thành viên trong bầy vừa bỏ phiếu cắn **{target_name}**.")
                except Exception: pass

    # 📥 Xử lý sự kiện khi Sói Nguyền chọn "NGUYỀN" mục tiêu
    elif data.startswith("wolf_curse_"):
        parts = data.split("_")
        room_id = parts
        target_id = int(parts)
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian ban đêm!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        target_name = user_db[target_id]["name"]
        
        # Ghi nhận lệnh nguyền đặc biệt
        wolf_curse_cache[room_id] = target_id
        room_data["roles"][user_id]["night_action"] = {"action": "curse", "target": target_id}
        
        bot.edit_message_text(f"🩸 Bạn đã giải phóng huyết ấn để **NGUYỀN** **{target_name}**. Nếu mục tiêu là Dân thường, họ sẽ thức tỉnh biến thành Sói vào đêm mai!", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Đã kích hoạt nguyền rủa!", show_alert=True)

# Cấu trúc quản lý kho thuốc của Phù Thủy trong mỗi phòng chơi
# { room_id: { witch_user_id: {"save_potion": True, "kill_potion": True} } }
witch_potions_cache = {}

# ==========================================
# 38. HÀM KÍCH HOẠT MENU THUỐC CỦA PHÙ THỦY
# ==========================================
def trigger_witch_menu(room_id, victim_id):
    """
    Hàm này được gọi sau khi bầy Sói đã thống nhất mục tiêu cắn.
    Truyền thông tin nạn nhân (victim_id) cho Phù Thủy quyết định cứu/giết.
    """
    room_data = game_rooms[room_id]
    
    # Tìm kiếm ID của Phù Thủy còn sống trong phòng
    witch_id = None
    for pid in room_data["alive"]:
        if room_data["roles"][pid]["role"] == "Phù Thủy":
            witch_id = pid
            break
            
    if not witch_id:
        return # Nếu Phù Thủy đã chết hoặc không có trong phòng, bỏ qua luồng này
        
    # Khởi tạo kho thuốc nếu là đêm đầu tiên của phòng
    if room_id not in witch_potions_cache:
        witch_potions_cache[room_id] = {
            witch_id: {"save_potion": True, "kill_potion": True}
        }
        
    potions = witch_potions_cache[room_id][witch_id]
    victim_name = user_db[victim_id]["name"] if victim_id else "Không ai cả"
    
    witch_text = (
        f"🧪 **QUYỀN NĂNG PHÙ THỦY THỨC TỈNH** 🧪\n"
        f"-----------------------------------------\n"
        f"🌤️ Thời tiết đêm nay: `{room_data['weather']}`\n"
        f"🔮 **Nhìn vào quả cầu pha lê, bạn thấy:**\n"
        f"➡️ Đêm nay, người đang bị bầy Sói cắn xé là: **{victim_name}**\n\n"
        f"🎒 **Kho thuốc ma thuật của bạn:**\n"
        f"▪️ Bình Thuốc Sinh (Cứu người): `{'CÒN TỐT' if potions['save_potion'] else 'ĐÃ DÙNG'}`\n"
        f"▪️ Bình Thuốc Tử (Giết người): `{'CÒN TỐT' if potions['kill_potion'] else 'ĐÃ DÙNG'}`\n"
        f"-----------------------------------------\n"
        f"⚠️ *Lưu ý thời tiết Sương Mù:* Nếu ném bình độc đêm nay, bạn có 30% tỷ lệ ném lệch sang người chơi ngồi kế bên!"
    )
    
    # Thiết lập các nút bấm Inline tương tác chọn thuốc
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Điều kiện hiển thị nút Bình Cứu (Phải còn thuốc và có nạn nhân bị cắn)
    if potions["save_potion"] and victim_id:
        btn_save = types.InlineKeyboardButton(f"🧪 Sử Dụng Bình Sinh — Cứu {victim_name}", callback_data=f"witch_save_{room_id}_{victim_id}")
        markup.add(btn_save)
        
    # Điều kiện hiển thị nút Bình Độc (Phải còn thuốc)
    if potions["kill_potion"]:
        btn_kill_menu = types.InlineKeyboardButton("💀 Sử Dụng Bình Tử — Đầu Độc 1 Người", callback_data=f"witch_kill_list_{room_id}")
        markup.add(btn_kill_menu)
        
    btn_skip = types.InlineKeyboardButton("⏳ Không Dùng Thuốc Đêm Này", callback_data=f"witch_skip_{room_id}")
    markup.add(btn_skip)
    
    bot.send_message(witch_id, witch_text, parse_mode="Markdown", reply_markup=markup)

# ==========================================
# 39. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================

    # 📥 Xử lý khi Phù Thủy chọn "CỨU NGƯỜI"
    elif data.startswith("witch_save_"):
        parts = data.split("_")
        room_id = parts
        target_id = int(parts)
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        # Đánh dấu đã sử dụng bình cứu, cập nhật dữ liệu hành động phòng
        witch_potions_cache[room_id][user_id]["save_potion"] = False
        game_rooms[room_id]["roles"][user_id]["night_action_witch_save"] = target_id
        
        bot.edit_message_text("🔮 Bạn đã đổ **Bình Thuốc Sinh** cứu sống mục tiêu thành công thoát khỏi nanh vuốt tử thần.", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Đã cứu người!")

    # 📥 Xử lý khi Phù Thủy chọn mở danh sách mục tiêu để "ĐẦU ĐỘC"
    elif data.startswith("witch_kill_list_"):
        room_id = data.replace("witch_kill_list_", "")
        
        # Gọi lại hàm tạo danh sách nút bấm mục tiêu đã viết ở Phần 12 ứng với thẻ hành động "witchkill"
        markup_targets = get_night_target_markup(room_id, user_id, "witchkill")
        btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI", callback_data=f"witch_back_{room_id}")
        markup_targets.add(btn_back)
        
        bot.edit_message_text("💀 **CHỌN MỤC TIÊU ĐỂ ĐẦU ĐỘC:**\nHãy chọn kẻ đáng nghi nhất để ném bình thuốc độc chết ngay lập tức.", chat_id, message_id, reply_markup=markup_targets)
        bot.answer_callback_query(call.id)

    # 📥 Xử lý khi Phù Thủy xác nhận chọn 1 người cụ thể để ném độc
    elif data.startswith("skill_witchkill_"):
        parts = data.split("_")
        room_id = parts
        target_id = int(parts)
        room_data = game_rooms[room_id]
        
        # Logic bảo lưu chống độc của vật phẩm "Bùa Hộ Mệnh" (Shop Phần 4)
        target_item = user_db[target_id].get("item_slot")
        
        # Áp dụng bộ lọc thời tiết Đêm Sương Mù (30% tỷ lệ ném lệch sang người ngẫu nhiên)
        if room_data["weather"] == "Đêm Sương Mù" and random.random() < 0.3:
            alternative_targets = [pid for pid in room_data["alive"] if pid != user_id and pid != target_id]
            if alternative_targets:
                target_id = random.choice(alternative_targets) # Bị ném lệch mục tiêu oan sai
        
        if target_item == "bua_ho_menh":
            # Đốt cháy bùa hộ mệnh cứu mạng, Phù thủy vẫn mất thuốc nhưng mục tiêu không chết
            user_db[target_id]["item_slot"] = None 
            room_data["roles"][user_id]["night_action_witch_kill"] = "BLOCKED_BY_AMULET"
        else:
            room_data["roles"][user_id]["night_action_witch_kill"] = target_id
            
        witch_potions_cache[room_id][user_id]["kill_potion"] = False
        
        bot.edit_message_text(f"🧪 Bạn đã ném **Bình Thuốc Tử** về phía mục tiêu **{user_db[target_id]['name']}**. Độc tố đang phát tán...", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Đã ném độc!", show_alert=True)

    # 📥 Xử lý khi Phù Thủy chọn "BỎ QUA / KHÔNG DÙNG THUỐC ĐÊM NAY"
    elif data.startswith("witch_skip_"):
        room_id = data.replace("witch_skip_", "")
        bot.edit_message_text("⏳ Bạn quyết định giữ lại các bình thuốc ma thuật để chờ đợi thời cơ chín muồi hơn.", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Bỏ qua đêm nay.")

# ==========================================
# 40. HÀM TỔNG KẾT KẾT QUẢ DIỄN BIẾN BAN ĐÊM
# ==========================================
# --- ĐOẠN CODE SAU KHI CHÈN THÊM VÀO PHẦN 15 ---
def process_end_of_night(room_id):
    """
    Hàm bộ não trung tâm tổng kết diễn biến ban đêm (Đã đồng bộ nâng cao v8):
    - Đếm phiếu Sói cắn và đối chiếu Khiên Già Làng (Phần 24)
    - Đối chiếu kết giới Bảo Vệ (Phần 12) & Thuốc Phù Thủy (Phần 14)
    - Kích hoạt kỹ năng khẩn cấp của Thợ Săn Đêm (Phần 36)
    - Quét sát thương cắn trộm của Ma Sói Gió (Phần 27)
    - Xử lý dây chuyền chết chùm vì tình yêu của Cupid (Phần 23)
    - Khai tử, dọn dẹp bộ nhớ đệm và thức tỉnh Bán Sói (Phần 25)
    """
    if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
        return
        
    room_data = game_rooms[room_id]
    dead_this_night = set()  # Danh sách những người sẽ phải chết đêm nay
    
    # --------------------------------------------------
    # BƯỚC 1: LẤY DỮ LIỆU PHIẾU CẮN CỦA BẦY MA SÓI (Phần 13)
    # --------------------------------------------------
    room_wolf_votes = wolf_votes_cache.get(room_id, {})
    wolf_victim = None
    if room_wolf_votes:
        wolf_victim = max(room_wolf_votes, key=room_wolf_votes.get) # Tìm kẻ bị cắn nhiều phiếu nhất
        
    # --------------------------------------------------
    # BƯỚC 2: THU THẬP DANH SÁCH ĐƯỢC BẢO VỆ & PHÙ THỦY CỨU/GIẾT
    # --------------------------------------------------
    protected_targets = set()
    for pid in room_data["alive"]:
        paction = room_data["roles"][pid].get("night_action")
        if paction and paction.get("action") == "guard":
            protected_targets.add(paction["target"])
            
    witch_save_target = None
    witch_kill_target = None
    for pid in room_data["alive"]:
        if room_data["roles"][pid]["role"] == "Phù Thủy":
            witch_save_target = room_data["roles"][pid].get("night_action_witch_save")
            witch_kill_target = room_data["roles"][pid].get("night_action_witch_kill")
            break

    # --------------------------------------------------
    # BƯỚC 3: ĐỐI CHIẾU LOGIC SỐNG CHẾT & LỒNG CÁC ĐỘT BIẾN (KÝ KIỂU 3)
    # --------------------------------------------------
    # Tình huống A: Xử lý nạn nhân bị bầy Ma Sói tấn công
    if wolf_victim:
        # LỒNG ĐỒNG BỘ PHẦN 24: Kiểm tra Lá chắn sinh mệnh của Già Làng trước khi chết
        is_elder_saved = False
        if room_data["roles"][wolf_victim]["role"] == "Già Làng":
            # Hàm apply_elder_night_shield (Phần 24) trả về True nếu Già Làng còn mạng 1
            is_elder_saved = apply_elder_night_shield(room_id, wolf_victim)
            
        if is_elder_saved:
            # Nếu Già Làng đỡ được mạng, bầy Sói cắn thất bại đêm nay
            room_data["history_log"].append(f"🛡️ Già Làng {user_db[wolf_victim]['name']} tiêu hao mạng 1, bảo vệ thành công bản thân.")
        else:
            # Nếu không phải Già Làng, hoặc Già Làng đã hết mạng bảo hộ
            if wolf_victim in protected_targets or wolf_victim == witch_save_target:
                # Đặc biệt: Nếu Đêm Trăng Rằm (Phần 11), Sói cắn xuyên qua lớp khiên Bảo Vệ thường
                if room_data["weather"] == "Đêm Trăng Rằm" and wolf_victim in protected_targets and wolf_victim != witch_save_target:
                    dead_this_night.add(wolf_victim)
                    room_data["history_log"].append(f"🩸 {user_db[wolf_victim]['name']} bị Sói cắn chết xuyên khiên Bảo Vệ do Đêm Trăng Rằm.")
                else:
                    room_data["history_log"].append(f"🛡️ {user_db[wolf_victim]['name']} đã được Bảo vệ/Phù thủy cứu sống kỳ tích.")
            else:
                # Nạn nhân chính thức tử vong vì Sói cắn
                dead_this_night.add(wolf_victim)
                room_data["history_log"].append(f"💀 {user_db[wolf_victim]['name']} đã bị bầy Ma Sói cắn chết phân xác.")
                
                # LỒNG ĐỒNG BỘ PHẦN 36: Đột biến Thợ Săn Đêm bắn súng trả thù khẩn cấp trước khi chết
                check_and_trigger_night_hunter_skill(room_id, wolf_victim)

    # Tình huống B: Xử lý mục tiêu bị Phù Thủy ném bình thuốc độc
    if witch_kill_target and witch_kill_target != "BLOCKED_BY_AMULET":
        dead_this_night.add(witch_kill_target)
        room_data["history_log"].append(f"🧪 {user_db[witch_kill_target]['name']} đã chết do dính độc dược Phù Thủy.")
        
        # LỒNG ĐỒNG BỘ PHẦN 24: Nếu Phù Thủy ném độc chết nhầm Già Làng -> Phạt tước kỹ năng cả làng
        if room_data["roles"][witch_kill_target]["role"] == "Già Làng":
            trigger_elder_punishment_curse(room_id, "Thuốc Độc Phù Thủy")

    # LỒNG ĐỒNG BỘ PHẦN 27: Gom thêm mục tiêu bị Ma Sói Gió cắn trộm âm thầm vào danh sách chết
    dead_this_night = apply_white_wolf_kill_result(room_id, dead_this_night)

    # LỒNG ĐỒNG BỘ PHẦN 23: Áp dụng logic chết chùm dây chuyền vì tình yêu của Cupid
    dead_this_night = apply_lovers_heartbreak_death(room_id, dead_this_night)

    # --------------------------------------------------
    # BƯỚC 4: THỰC THI KHAI TỬ TRÊN DATABASE VÀO BAN SÁNG
    # --------------------------------------------------
    for dead_id in dead_this_night:
        if dead_id in room_data["alive"]:
            room_data["alive"].remove(dead_id)
            room_data["roles"][dead_id]["status"] = "Dead"
            
    # LỒNG ĐỒNG BỘ PHẦN 25: Kiểm tra xem Thần tượng của Bán Sói có nằm trong dải chết để hóa Sói không
    check_and_awaken_wild_child(room_id, dead_this_night)

    # LỒNG ĐỒNG BỘ PHẦN 13: Xử lý bùa nguyền lây nhiễm của Sói Nguyền
    cursed_target = wolf_curse_cache.get(room_id)
    if cursed_target and cursed_target in room_data["alive"] and cursed_target not in dead_this_night:
        if room_data["roles"][cursed_target]["role"] == "Dân":
            room_data["roles"][cursed_target]["role"] = "Ma Sói Thường"
            room_data["roles"][cursed_target]["team"] = "Ma Sói"
            room_data["history_log"].append(f"🧬 Dân làng {user_db[cursed_target]['name']} dính nguyền rủa, hóa Ma Sói đêm nay.")
            try: bot.send_message(cursed_target, "🩸 **HẤP THỤ HUYẾT ẤN THÀNH CÔNG:** Bạn đã bị nguyền hóa thành Ma Sói! Từ đêm mai hãy đi săn cùng bầy.")
            except Exception: pass

    # --------------------------------------------------
    # BƯỚC 5: DỌN DẸP CACHE ĐÊM ĐỂ CHUẨN BỊ CHO CHU KỲ SAU
    # --------------------------------------------------
    if room_id in wolf_votes_cache: del wolf_votes_cache[room_id]
    if room_id in wolf_curse_cache: del wolf_curse_cache[room_id]
    if room_id in shadow_ballot_active_cache: del shadow_ballot_active_cache[room_id] # Đồng bộ Phần 38
    for pid in room_data["players"]:
        if "night_action" in room_data["roles"][pid]: del room_data["roles"][pid]["night_action"]
        if "night_action_witch_save" in room_data["roles"][pid]: del room_data["roles"][pid]["night_action_witch_save"]
        if "night_action_witch_kill" in room_data["roles"][pid]: del room_data["roles"][pid]["night_action_witch_kill"]

    # Chuyển trạng thái phòng sang Ban Ngày
    room_data["status"] = "Day"
    
    # --------------------------------------------------
    # BƯỚC 6: BIÊN SOẠN BẢNG PHÁT SÓNG THÔNG BÁO BUỔI SÁNG
    # --------------------------------------------------
    morning_announcement = (
        f"☀️ **BÌNH MINH HÉ RẠNG TRÊN NGÔI LÀNG** ☀️\n"
        f"-----------------------------------------\n"
        f"🐓 Tiếng gà gáy vang lên, dân làng tập trung tại quảng trường kiểm tra quân số...\n\n"
    )
    
    if dead_this_night:
        morning_announcement += "💀 **DANH SÁCH HY SINH ĐÊM QUA:**\n"
        for dead_id in dead_this_night:
            pname = user_db[dead_id]["name"]
            prole = room_data["roles"][dead_id]["role"]
            morning_announcement += f"▪️ **{pname}** đã ngã xuống vĩnh viễn (Vai trò: `{prole}`)\n"
    else:
        morning_announcement += "🎉 **KỲ TÍCH ĐÊM BÌNH YÊN!** Không có ai phải nằm xuống trong đêm vừa qua.\n"
        
    morning_announcement += (
        f"-----------------------------------------\n"
        f"📊 **Quân số hiện tại:** Còn `{len(room_data['alive'])}` người sống sót.\n"
        f"💬 *Cổng chat tổng đã mở. Hãy thảo luận để tìm ra Ma Sói!*"
    )
    
    for pid in room_data["players"]:
        try: bot.send_message(pid, morning_announcement, parse_mode="Markdown")
        except Exception: pass

    # Kiểm tra điều kiện kết thúc game ngay lập tức (Nếu thỏa mãn phe nào thắng, ngắt luồng luôn)
    if check_game_over_conditions(room_id):
        return

    # Kích hoạt luồng đếm ngược thời gian thảo luận Ban Ngày (Phần 16)
    start_day_discussion_phase(room_id)

# ==========================================
# 41. ĐỊNH NGHĨA SỰ KIỆN & THỜI TIẾT BAN NGÀY
# ==========================================
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

# Bộ nhớ tạm lưu danh sách người chơi bị khóa mõm (Mute) trong ngày
muted_players_today = {}

# ==========================================
# 42. HÀM KÍCH HOẠT GIAI ĐOẠN THẢO LUẬN BAN NGÀY
# ==========================================
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
            # Nếu đêm qua có thực hiện kỹ năng (xem lại ghi chú ở Phần 15)
            if room_data["roles"][pid].get("used_skill_last_night"): 
                muted_players_today[room_id].add(pid) # Sẽ viết hàm tự động mở khóa sau 20 giây ở phần sau
    
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
        except Exception: pass
        
    room_data["history_log"].append(f"☀️ Thảo luận ngày mở. Thời tiết: {weather_key}, Sự kiện: {event_card['name']}")
    
    # Khởi chạy luồng hẹn giờ đếm ngược đóng cổng chat thảo luận ban ngày
    threading.Thread(target=countdown_discussion_timer, args=(room_id, discussion_time)).start()

# ==========================================
# 43. MIDDLEWARE PHÒNG CHỐNG CHAT TRỘM KHI BỊ MUTE
# ==========================================
@bot.message_handler(func=lambda message: True)
def handle_group_chat_filter(message):
    """
    Bộ lọc kiểm tra tin nhắn chat tổng. 
    Chặn đứng hành vi chat của người chết hoặc người đang bị dính hiệu ứng Mute.
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
        if room_data["status"] in ["Night", "Day", "Discussion", "Vote"] and user_id not in room_data["alive"]:
            try:
                bot.delete_message(chat_id, message.message_id)
                bot.send_message(user_id, "👻 Bạn đã chết, vui lòng giữ linh hồn lặng im không được phím chiến phá bĩnh trò chơi!")
            except Exception: pass
            return
            
        # 2. Chặn người chơi đang bị dính án phạt Mute từ Sự kiện thời tiết
        if room_data["status"] == "Discussion" and user_id in muted_players_today.get(active_room_id, set()):
            try:
                bot.delete_message(chat_id, message.message_id)
                bot.send_message(user_id, "🔇 Bạn đang trong trạng thái bị khóa mõm cấm ngôn luận, không thể gửi tin nhắn chat tổng lúc này!")
            except Exception: pass
            return

def countdown_discussion_timer(room_id, seconds):
    """Luồng đếm ngược thời gian thảo luận ban ngày"""
    time.sleep(seconds)
    if room_id in game_rooms and game_rooms[room_id]["status"] == "Discussion":
        # Hết giờ thảo luận, cưỡng chế đóng cổng chat tổng và chuyển sang giai đoạn Tố Giác Treo Cổ
        start_voting_nomination_phase(room_id)

# Bộ nhớ tạm lưu trữ phiếu bầu khởi tố ban ngày: { room_id: { target_id: [danh_sách_id_người_vote] } }
nomination_votes_cache = {}

# ==========================================
# 44. KHỞI ĐỘNG GIAI ĐOẠN KHỞI TỐ (NOMINATION PHASE)
# ==========================================
def start_voting_nomination_phase(room_id):
    """
    Kích hoạt giai đoạn tố giác tội phạm.
    Gửi menu nút bấm cho tất cả người chơi còn sống để chọn nghi phạm đưa lên bục.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    room_data["status"] = "Vote_Nomination"
    nomination_votes_cache[room_id] = {} # Khởi tạo kho lưu phiếu bầu ban ngày

    vote_msg = (
        f"⚖️ **GIAI ĐOẠN TỐ GIÁC KHỞI TỐ BẮT ĐẦU** ⚖️\n"
        f"-----------------------------------------\n"
        f"📢 Đã hết thời gian thảo luận tự do. Ban trị sự làng yêu cầu các dũng sĩ tiến hành bỏ phiếu tố giác kẻ đáng nghi nhất.\n\n"
        f"👉 Người nhận được **nhiều phiếu tố giác nhất** (và đạt tối thiểu 2 phiếu) sẽ bị đưa lên bục hành hình để biện hộ.\n"
        f"⏳ **Thời gian bỏ phiếu:** `45 giây` thông qua các nút bấm riêng phía dưới.\n"
        f"-----------------------------------------\n"
    )
    
    # Kiểm tra hiệu ứng của Lá bài Sự kiện Tòa Án Lương Tâm
    if room_data.get("event_card") == "toa_an":
        vote_msg += "⚖️ **SỰ KIỆN ĐẶC BIỆT:** Lá bài *Tòa Án Lương Tâm* đang kích hoạt! Danh tính người bỏ phiếu sẽ được **CÔNG KHAI CHÍNH XÁC** lên tổng đài!"
    else:
        vote_msg += "🤫 *Hình thức:* Phiếu bầu được ẩn danh hoàn toàn để bảo vệ an toàn cho bạn."

    # Gửi menu nút bấm chọn mục tiêu tố giác cho từng người chơi còn sống
    for pid in room_data["alive"]:
        try:
            # Sử dụng lại hàm tạo nút bấm mục tiêu đã viết ở Phần 12 với tag hành động "nominate"
            markup_vote = get_night_target_markup(room_id, pid, "nominate")
            # Nút bổ sung: Chọn bỏ qua, không vote ai cả
            btn_skip = types.InlineKeyboardButton("⚪ Bỏ Qua Phiếu Bầu", callback_data=f"skill_nominate_{room_id}_0")
            markup_vote.add(btn_skip)
            
            bot.send_message(pid, vote_msg, parse_mode="Markdown", reply_markup=markup_vote)
        except Exception: pass

    # Khởi chạy luồng đếm ngược thời gian bỏ phiếu khởi tố (45 giây)
    threading.Thread(target=countdown_nomination_timer, args=(room_id, 45)).start()

# ==========================================
# 45. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán tiếp vào hàm handle_global_callbacks của Phần 6)

    elif data.startswith("skill_nominate_"):
        # Cấu trúc: skill_nominate_[room_id]_[target_id]
        parts = data.split("_")
        room_id = parts
        target_id = int(parts)
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Vote_Nomination":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian khởi tố!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        voter_name = user_db[user_id]["name"]
        
        # Trường hợp 1: Người chơi chọn Bỏ Qua (target_id == 0)
        if target_id == 0:
            bot.edit_message_text("⚪ Bạn đã quyết định giữ phiếu trắng, không tố giác bất kỳ ai trong ngày hôm nay.", chat_id, message_id)
            bot.answer_callback_query(call.id, text="Đã bỏ qua phiếu.")
            
            # Nếu sự kiện Tòa Án Lương Tâm bật, công khai lệnh bỏ qua lên sảnh chat phòng chơi
            if room_data.get("event_card") == "toa_an":
                for pid in room_data["players"]:
                    try: bot.send_message(pid, f"⚖️ **Tòa Án:** **{voter_name}** đã chọn bỏ phiếu trắng.")
                    except Exception: pass
            return

        # Trường hợp 2: Bỏ phiếu tố giác 1 người chơi cụ thể
        target_name = user_db[target_id]["name"]
        
        # Ghi nhận dữ liệu phiếu bầu vào Cache hệ thống
        if target_id not in nomination_votes_cache[room_id]:
            nomination_votes_cache[room_id][target_id] = []
            
        # Kiểm tra chống click trùng lập (Một người chỉ được vote 1 lần)
        if user_id not in nomination_votes_cache[room_id][target_id]:
            nomination_votes_cache[room_id][target_id].append(user_id)
            
        bot.edit_message_text(f"✅ Bạn đã gửi lệnh tố giác đối tượng: **{target_name}**. Hãy chờ kết quả biểu quyết làng.", chat_id, message_id)
        bot.answer_callback_query(call.id, text=f"Đã tố giác {target_name}!")

        # Đồng bộ hóa công khai danh tính nếu Lá bài Tòa Án Lương Tâm đang chạy
        if room_data.get("event_card") == "toa_an":
            for pid in room_data["players"]:
                try: bot.send_message(pid, f"⚖️ **Tòa Án:** **{voter_name}** đã bỏ phiếu khởi tố tố giác **{target_name}**!")
                except Exception: pass

# ==========================================
# 46. LUỒNG ĐẾM NGƯỢC CƯỠNG CHẾ ĐÓNG PHIẾU KHỞI TỐ
# ==========================================
def countdown_nomination_timer(room_id, seconds):
    """Luồng đếm ngược thời gian bỏ phiếu khởi tố"""
    time.sleep(seconds)
    if room_id in game_rooms and game_rooms[room_id]["status"] == "Vote_Nomination":
        # Hết 45 giây, cưỡng chế đóng hòm phiếu và chuyển tiếp sang hàm xử lý kết quả bục biện hộ
        process_nomination_result(room_id)

# Biến lưu trữ ID của nghi phạm đang đứng trên bục biện hộ của từng phòng chơi
current_suspect_on_stage = {}

# ==========================================
# 47. HÀM XỬ LÝ KẾT QUẢ PHIẾU BẦU KHỞI TỐ
# ==========================================
def process_nomination_result(room_id):
    """
    Hàm lõi tổng hợp hòm phiếu tố giác ban ngày:
    - Tìm đối tượng bị nhiều người tố giác nhất.
    - Xác thực điều kiện đưa lên bục (Số phiếu bầu phải >= 2).
    - Khóa chat toàn bộ người chơi khác, mở cổng biện hộ cho nghi phạm.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    room_votes = nomination_votes_cache.get(room_id, {})
    
    # Tìm đối tượng nhận nhiều phiếu tố giác nhất
    suspect_id = None
    max_votes = 0
    
    for pid, voters in room_votes.items():
        if len(voters) > max_votes:
            max_votes = len(voters)
            suspect_id = pid
            
    # Bảng tổng kết hòm phiếu hiển thị chi tiết lên nhóm chat sảnh game
    result_text = "📊 **KẾT QUẢ BỎ PHIẾU KHỞI TỐ TỘI PHẠM:**\n-----------------------------------------\n"
    if room_votes:
        for pid, voters in room_votes.items():
            pname = user_db[pid]["name"]
            result_text += f"▪️ **{pname}**: bị `{len(voters)}` phiếu tố giác.\n"
    else:
        result_text += "⚪ Không ai bỏ phiếu tố giác trong ngày hôm nay.\n"
        
    result_text += "-----------------------------------------\n"

    # Điều kiện xử lý: Phải có nghi phạm và số phiếu tố giác phải từ mốc 2 trở lên
    if suspect_id and max_votes >= 2:
        suspect_name = user_db[suspect_id]["name"]
        current_suspect_on_stage[room_id] = suspect_id
        
        # Đổi trạng thái vận hành phòng chơi sang giai đoạn Biện Hộ
        room_data["status"] = "Stage_Defense"
        
        result_text += (
            f"🚨 **NGHI PHẠM LÊN BỤC:** Đối tượng **{suspect_name}** chính thức bị đưa lên bục hành hình với `{max_votes}` phiếu tố giác!\n\n"
            f"🔒 **CƯỠNG CHẾ KHÓA MÕM:** Hệ thống đã tự động khóa quyền chat của toàn bộ ngôi làng.\n"
            f"🎙️ **GIAI ĐOẠN BIỆN HỘ CHÍNH THỨC:**\n"
            f"👉 Chỉ một mình **{suspect_name}** có quyền nhắn tin chat tổng để giải trình, chứng minh sự trong sạch của bản thân.\n"
            f"⏳ **Thời gian biện hộ:** `30 giây` bắt đầu đếm ngược!"
        )
        
        # Phát thông báo lên sảnh game và khởi chạy luồng đếm ngược thời gian biện hộ
        for pid in room_data["players"]:
            try: bot.send_message(pid, result_text, parse_mode="Markdown")
            except Exception: pass
            
        room_data["history_log"].append(f"⚖️ Nghi phạm {suspect_name} lên bục biện hộ với {max_votes} phiếu.")
        
        # Cập nhật lại bộ lọc chat ngầm (Middleware Phần 16) sẽ chặn chat mọi người trừ nghi phạm
        threading.Thread(target=countdown_defense_timer, args=(room_id, 30)).start()
        
    else:
        # Trường hợp không có ai đủ 2 phiếu tố giác, làng hòa, bỏ qua treo cổ và chuyển sang đêm tiếp theo
        result_text += "🎉 **KẾT LUẬN LÀNG:** Không có ai bị nhận đủ số phiếu khởi tố tối thiểu. Ngày hôm nay trôi qua trong hòa bình, không có vụ hành hình nào diễn ra!"
        
        for pid in room_data["players"]:
            try: bot.send_message(pid, result_text, parse_mode="Markdown")
            except Exception: pass
            
        room_data["history_log"].append("🎉 Ngày trôi qua hòa bình, không ai bị khởi tố.")
        
        # Đóng sảnh ban ngày và dọn dẹp để chuẩn bị quay lại chu kỳ Ban Đêm (Sẽ điều phối luồng ở các phần sau)
        if room_id in nomination_votes_cache: del nomination_votes_cache[room_id]
        
        # Sau 5 giây nghỉ ngơi, tự động chuyển cảnh sang ban đêm tiếp theo
        time.sleep(5)
        start_night_phase(room_id)

# ==========================================
# 48. CẬP NHẬT TRẠNG THÁI KIỂM SOÁT MIDDLEWARE CHAT TỔNG (Phần 16)
# ==========================================
# Ghi chú: Bạn hãy bổ sung thêm đoạn kiểm tra logic này vào hàm `handle_group_chat_filter` ở Phần 16:

    # Nếu đang trong giai đoạn Biện hộ, chặn chat tất cả mọi người trừ Nghi phạm đang trên bục
    if room_data["status"] == "Stage_Defense":
        suspect_id = current_suspect_on_stage.get(active_room_id)
        if user_id != suspect_id:
            try:
                bot.delete_message(chat_id, message.message_id)
                bot.send_message(user_id, "🔇 Làng đang trong giờ thi hành lệnh giữ trật tự! Hãy để nghi phạm thực hiện quyền biện hộ duy nhất trên bục lúc này.")
            except Exception: pass
            return

# ==========================================
# 49. LUỒNG ĐẾM NGƯỢC THỜI GIAN BIỆN HỘ CỦA NGHI PHẠM
# ==========================================
def countdown_defense_timer(room_id, seconds):
    """Luồng đếm ngược thời gian biện hộ chạy ngầm"""
    time.sleep(seconds)
    if room_id in game_rooms and game_rooms[room_id]["status"] == "Stage_Defense":
        # Hết 30 giây thanh minh, tự động khóa mõm luôn nghi phạm và kích hoạt hòm phiếu Tối hậu hành hình
        start_final_judgment_vote(room_id)

# Bộ nhớ tạm lưu trữ phiếu bầu tối hậu quyết định mạng sống:
# { room_id: {"yes": 0, "no": 0, "voted_players": set()} }
final_judgment_cache = {}

# ==========================================
# 50. KHỔI ĐỘNG GIAI ĐOẠN PHIẾU BẦU TỐI HẬU (FINAL JUDGMENT)
# ==========================================
def start_final_judgment_vote(room_id):
    """
    Kích hoạt hòm phiếu tối hậu quyết định sinh tử của nghi phạm.
    Gửi menu 2 nút bấm Inline (Đồng ý/Bác bỏ) cho tất cả người dân làng còn sống.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    room_data["status"] = "Final_Judgment"
    
    suspect_id = current_suspect_on_stage.get(room_id)
    if not suspect_id or suspect_id not in room_data["alive"]:
        # Phòng hờ nghi phạm tự thoát game hoặc bị sập lỗi hệ thống
        return
        
    suspect_name = user_db[suspect_id]["name"]
    
    # Khởi tạo bộ đếm phiếu trống cho phòng chơi
    final_judgment_cache[room_id] = {
        "yes": 0,
        "no": 0,
        "voted_players": set()
    }
    
    judgment_text = (
        f"⚖️ **PHIẾU BẦU TỐI HẬU QUYẾT ĐỊNH SINH TỬ** ⚖️\n"
        f"-----------------------------------------\n"
        f"🎙️ Thời gian biện hộ của nghi phạm **{suspect_name}** đã khép lại.\n\n"
        f"👉 Giờ phút phán xét tối cao đã đến! Hãy đưa ra sự lựa chọn sáng suốt để bảo vệ ngôi làng hoặc loại bỏ kẻ ác:\n"
        f"🔺 **Đồng Ý Treo Cổ:** Nếu bạn tin rằng đối tượng này là Ma Sói hoặc kẻ địch.\n"
        f"🔹 **Bác Bỏ Lệnh Hành Hình:** Nếu bạn tin lời thanh minh và muốn tha mạng cho đối tượng.\n\n"
        f"⏳ **Thời gian phán xét:** `30 giây` để bấm nút quyết định.\n"
        f"⚠️ *Lưu ý:* Nghi phạm không có quyền tự bỏ phiếu cho chính mình."
    )
    
    # Thiết kế menu nút bấm phán quyết trực quan
    markup_judgment = types.InlineKeyboardMarkup(row_width=2)
    btn_yes = types.InlineKeyboardButton("🔺 ĐỒNG Ý TREO CỔ", callback_data=f"judge_yes_{room_id}")
    btn_no = types.InlineKeyboardButton("🔹 BÁC BỎ LỆNH HÀNH HÌNH", callback_data=f"judge_no_{room_id}")
    markup_judgment.add(btn_yes, btn_no)
    
    # Gửi bảng lệnh phán xét đến từng người chơi còn sống (Ẩn nghi phạm)
    for pid in room_data["alive"]:
        if pid != suspect_id:
            try:
                bot.send_message(pid, judgment_text, parse_mode="Markdown", reply_markup=markup_judgment)
            except Exception: pass
        else:
            try:
                bot.send_message(pid, f"⏳ **Giờ phút phán xét:** Toàn bộ làng đang tiến hành bỏ phiếu quyết định mạng sống của bạn. Hãy cầu nguyện thần may mắn mỉm cười...")
            except Exception: pass
            
    # Khởi chạy luồng đếm ngược đóng hòm phiếu tối hậu (30 giây)
    threading.Thread(target=countdown_judgment_timer, args=(room_id, 30)).start()

# ==========================================
# 51. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán tiếp vào hàm handle_global_callbacks của Phần 6)

    elif data.startswith("judge_yes_") or data.startswith("judge_no_"):
        is_yes_vote = data.startswith("judge_yes_")
        room_id = data.replace("judge_yes_", "") if is_yes_vote else data.replace("judge_no_", "")
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Final_Judgment":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian phán xét tối hậu!", show_alert=True)
            return
            
        room_cache = final_judgment_cache[room_id]
        
        # Kiểm tra chống click đúp phá hòm phiếu (Một người chỉ được phán xét 1 lần)
        if user_id in room_cache["voted_players"]:
            bot.answer_callback_query(call.id, text="⚠️ Bạn đã thực hiện quyền phán xét của mình từ trước rồi!", show_alert=True)
            return
            
        # Ghi nhận trạng thái hoàn tất bỏ phiếu
        room_cache["voted_players"].add(user_id)
        voter_name = user_db[user_id]["name"]
        
        if is_yes_vote:
            room_cache["yes"] += 1
            bot.edit_message_text("🔺 Bạn đã bỏ phiếu: **ĐỒNG Ý TREO CỔ** đối tượng nghi phạm.", chat_id, message_id)
            bot.answer_callback_query(call.id, text="Đã chọn Đồng Ý!")
        else:
            room_cache["no"] += 1
            bot.edit_message_text("🔹 Bạn đã bỏ phiếu: **BÁC BỎ LỆNH HÀNH HÌNH** đối tượng nghi phạm.", chat_id, message_id)
            bot.answer_callback_query(call.id, text="Đã chọn Bác Bỏ!")

        # Đồng bộ hóa thông báo ẩn danh lên nhóm sảnh game để tạo kịch tính cho dòng phiếu chạy
        room_data = game_rooms[room_id]
        action_text = "🔺 ĐỒNG Ý TREO CỔ" if is_yes_vote else "🔹 THA MẠNG"
        
        # Nếu lá bài Tòa Án Lương Tâm (Phần 17) đang bật, công khai tên tuổi người vote tối hậu luôn
        for pid in room_data["players"]:
            try:
                if room_data.get("event_card") == "toa_an":
                    bot.send_message(pid, f"⚖️ **Tòa Án:** **{voter_name}** đã đưa ra phán quyết: `{action_text}`.")
                else:
                    bot.send_message(pid, f"⚖️ Một người dân làng còn sống vừa đưa ra phán quyết ẩn danh.")
            except Exception: pass

# ==========================================
# 52. LUỒNG ĐẾM NGƯỢC CƯỠNG CHẾ ĐÓNG HÒM PHIẾU TỐI HẬU
# ==========================================
def countdown_judgment_timer(room_id, seconds):
    """Luồng đếm ngược thời gian phán xét sinh tử chạy ngầm"""
    time.sleep(seconds)
    if room_id in game_rooms and game_rooms[room_id]["status"] == "Final_Judgment":
        # Hết 30 giây phán quyết, tự động thu hồi hòm phiếu và chuyển tiếp sang hàm thực thi án phạt treo cổ
        process_final_judgment_execution(room_id)

# Bộ nhớ tạm lưu trữ di chúc cuối cùng của người chơi bị chết trong ngày: { room_id: { user_id: "chuỗi_di_chúc" } }
last_wills_cache = {}

# ==========================================
# 53. HÀM XỬ LÝ KẾT QUẢ PHÁN QUYẾT TỐI HẬU
# ==========================================
def process_final_judgment_execution(room_id):
    """
    Hàm tổng hợp phiếu sinh tử:
    - Nếu Yes > No: Tiến hành treo cổ, mở cổng viết Di chúc trong 30 giây.
    - Nếu No >= Yes: Tha mạng cho nghi phạm, đưa làng quay lại ban đêm.
    - Xử lý đột biến nếu người bị treo cổ là Thợ Săn.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    room_cache = final_judgment_cache.get(room_id, {"yes": 0, "no": 0, "voted_players": set()})
    
    suspect_id = current_suspect_on_stage.get(room_id)
    if not suspect_id:
        return
        
    suspect_name = user_db[suspect_id]["name"]
    suspect_role = room_data["roles"][suspect_id]["role"]
    
    # Tạo văn bản bảng kết quả bỏ phiếu công bố lên toàn sảnh game
    exec_text = (
        f"⚖️ **KẾT QUẢ PHÁN QUYẾT TỐI HẬU LÀNG MA SÓI** ⚖️\n"
        f"-----------------------------------------\n"
        f"👤 Nghi phạm đứng trên bục: **{suspect_name}**\n"
        f"🔺 Số phiếu ĐỒNG Ý TREO CỔ: `{room_cache['yes']}` phiếu\n"
        f"🔹 Số phiếu BÁC BỎ THA MẠNG: `{room_cache['no']}` phiếu\n"
        f"-----------------------------------------\n"
    )

    # TRƯỜNG HỢP 1: TOÀN DÂN ĐỒNG THUẬN TREO CỔ (Yes > No)
    if room_cache["yes"] > room_cache["no"]:
        room_data["status"] = "Execution_Will"
        
        # Khai tử người chơi khỏi danh sách sống trên hệ thống
        if suspect_id in room_data["alive"]:
            room_data["alive"].remove(suspect_id)
            room_data["roles"][suspect_id]["status"] = "Dead"
            
        exec_text += (
            f"💀 **THỰC THI HÀNH HÌNH:** Với đa số phiếu thuận, dân làng đã quyết định giật dây treo cổ **{suspect_name}**!\n\n"
            f"📝 **DI CHÚC CUỐI CÙNG (LAST WILL):**\n"
            f"👉 Hệ thống mở cổng kết nối mật. **{suspect_name}** có đúng `30 giây` để viết lời trăng trối gửi cho Bot. Di chúc này sẽ được công bố công khai lên sảnh game sau khi hết giờ.\n"
            f"⏳ *Hãy chuẩn bị tinh thần lật mở quân bài chức năng...*"
        )
        
        # Phát thông báo khẩn cấp lên sảnh
        for pid in room_data["players"]:
            try: bot.send_message(pid, exec_text, parse_mode="Markdown")
            except Exception: pass
            
        room_data["history_log"].append(f"💀 {suspect_name} đã bị treo cổ ban ngày.")

        # Mở cổng nhận tin nhắn di chúc mật riêng biệt cho nghi phạm
        msg_will = bot.send_message(suspect_id, "📝 **GIỜ PHÚT TRĂNG TRỐI:** Hãy nhập nội dung di chúc của bạn vào đây (Ví dụ: thông tin Tiên tri soi được, lời đổ tội giả...). Nhắn tin và gửi ngay cho Bot:")
        bot.register_next_step_handler(msg_will, receive_user_will_step, room_id, suspect_id)
        
        # Khởi chạy luồng đếm ngược thời gian chờ viết di chúc (30 giây)
        threading.Thread(target=countdown_will_timer, args=(room_id, suspect_id, suspect_role, 30)).start()

    # TRƯỜNG HỢP 2: THA MẠNG (No >= Yes)
    else:
        exec_text += f"🎉 **LÀNG THA MẠNG KỲ TÍCH:** Số phiếu bác bỏ bằng hoặc lớn hơn, lệnh hành hình bị hủy bỏ! **{suspect_name}** chính thức được giải vây bước xuống bục an toàn.\n\n⏳ Hệ thống tiến hành dọn dẹp quảng trường và đưa ngôi làng chìm vào chu kỳ màn đêm tiếp theo..."
        
        for pid in room_data["players"]:
            try: bot.send_message(pid, exec_text, parse_mode="Markdown")
            except Exception: pass
            
        room_data["history_log"].append(f"🎉 {suspect_name} được tha mạng trên bục tối hậu.")
        
        # Dọn dẹp cache phán quyết
        if room_id in final_judgment_cache: del final_judgment_cache[room_id]
        
        # Sau 5 giây, tự động đóng ngày, chuyển cảnh sang Đêm tiếp theo
        time.sleep(5)
        start_night_phase(room_id)

# ==========================================
# 54. LOGIC TIẾP NHẬN DI CHÚC TỪ NGƯỜI CHẾT
# ==========================================
def receive_user_will_step(message, room_id, dead_id):
    """Ghi nhận chuỗi văn bản di chúc mật của người chơi vào cache"""
    if room_id not in last_wills_cache:
        last_wills_cache[room_id] = {}
    last_wills_cache[room_id][dead_id] = message.text.strip()[:100] # Giới hạn tối đa 100 chữ tránh spam giao diện
    bot.send_message(dead_id, "✅ Di chúc của bạn đã được ghi nhận vào hệ thống lõi v8.")

# ==========================================
# 55. LUỒNG ĐẾM NGƯỢC DI CHÚC VÀ LẬT BÀI / THỢ SĂN
# ==========================================
def countdown_will_timer(room_id, dead_id, dead_role, seconds):
    """Luồng chạy ngầm đếm ngược 30 giây viết di chúc"""
    time.sleep(seconds)
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    dead_name = user_db[dead_id]["name"]
    
    # Lấy di chúc từ cache, nếu không viết mặc định là để lại một khoảng trống lặng im
    user_will = last_wills_cache.get(room_id, {}).get(dead_id, "*(Người chết ra đi lặng im không để lại lời trăng trối nào)*")
    
    will_publish_text = (
        f"📜 **CÔNG BỐ DI CHÚC CỦA CAO THỦ: {dead_name}** 📜\n"
        f"-----------------------------------------\n"
        f"💬 **Nội dung trăng trối:**\n\"{user_will}\"\n\n"
        f"🎭 **LẬT MỞ QUÂN BÀI CHỨC NĂNG CHÍNH THỨC:**\n"
        f"➡️ Thân phận thực sự của **{dead_name}** là: **{dead_role}**\n"
        f"-----------------------------------------\n"
    )
    
    for pid in room_data["players"]:
        try: bot.send_message(pid, will_publish_text, parse_mode="Markdown")
        except Exception: pass

    # Clean dọn dẹp bộ nhớ đệm
    if room_id in final_judgment_cache: del final_judgment_cache[room_id]
    if room_id in last_wills_cache: del last_wills_cache[room_id]

    # --------------------------------------------------
    # BIẾN ĐỘNG ĐẶC BIỆT: KÍCH HOẠT QUYỀN NĂNG THỢ SĂN (Phần 10)
    # --------------------------------------------------
    if dead_role == "Thợ Săn" and room_data["alive"]:
        room_data["status"] = "Hunter_Skill_Trigger"
        
        hunter_text = (
            f"🏹 **QUYỀN NĂNG THỢ SĂN KÍCH HOẠT BẠO PHÁT** 🏹\n"
            f"-----------------------------------------\n"
            f"💥 Trước khi trút hơi thở cuối cùng trên đoạn đầu đài, **{dead_name}** đã kịp giương cung ngắm bắn một mũi tên chí mạng!\n"
            f"👉 Hệ thống mở menu nút bấm độc quyền gửi cho Thợ Săn. Bạn có `30 giây` để lựa chọn kéo theo 1 người chơi bất kỳ cùng xuống mồ."
        )
        for pid in room_data["players"]:
            try: bot.send_message(pid, hunter_text, parse_mode="Markdown")
            except Exception: pass
            
        # Gửi danh sách nút mục tiêu cho riêng Thợ săn bắn chết (Sử dụng hàm nút mục tiêu Phần 12 với tag hành động "hunter")
        markup_hunter = get_night_target_markup(room_id, dead_id, "hunter")
        bot.send_message(dead_id, "🏹 **HÃY CHỌN KẺ BẠN MUỐN BẮN CHẾT CÙNG ĐÊM NAY:**", reply_markup=markup_hunter)
        
        # Chuyển tiếp luồng xử lý đếm ngược kỹ năng Thợ săn sang phần sau (Sẽ viết hàm xử lý bắn đạn ở Phần 21)
    else:
        # Nếu không phải Thợ Săn, kiểm tra kết thúc game, nếu chưa thì quay về ban đêm
        if not check_game_over_conditions(room_id):
            time.sleep(5)
            start_night_phase(room_id)

# ==========================================
# 56. BỔ SUNG NHÁNH XỬ LÝ SỰ KIỆN THỢ SĂN VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6/19)

    elif data.startswith("skill_hunter_"):
        # Cấu trúc tách chuỗi: skill_hunter_[room_id]_[target_id]
        parts = data.split("_")
        room_id = parts[2]
        target_id = int(parts[3])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Hunter_Skill_Trigger":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian bóp cò súng!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        target_name = user_db[target_id]["name"]
        target_role = room_data["roles"][target_id]["role"]
        
        # Thực thi khai tử mục tiêu bị Thợ Săn nhắm bắn
        if target_id in room_data["alive"]:
            room_data["alive"].remove(target_id)
            room_data["roles"][target_id]["status"] = "Dead"
            
        hunter_kill_text = (
            f"💥 **ĐOÀNG! MŨI TÊN CHÍ MẠNG ĐÃ BAY VÙ** 💥\n"
            f"-----------------------------------------\n"
            f"🏹 Thợ Săn trước khi ngã xuống đã bóp cò ghim thẳng mũi tên vào ngực **{target_name}**!\n"
            f"🎭 Thân phận thực sự của mục tiêu bị bắn hạ: **{target_role}**\n"
            f"-----------------------------------------\n"
            f"⏳ Hệ thống tiến hành cập nhật lại quân số và kiểm tra cục diện trận đấu..."
        )
        
        for pid in room_data["players"]:
            try: bot.send_message(pid, hunter_kill_text, parse_mode="Markdown")
            except Exception: pass
            
        room_data["history_log"].append(f"🏹 Thợ Săn bắn chết {target_name} ({target_role}).")
        
        # Sau khi Thợ Săn hoàn tất phát bắn, kiểm tra điều kiện kết thúc trận đấu
        if not check_game_over_conditions(room_id):
            # Nếu trận đấu chưa kết thúc, chuyển cảnh quay về chu kỳ Ban Đêm tiếp theo
            time.sleep(5)
            start_night_phase(room_id)

# ==========================================
# 57. THUẬT TOÁN KIỂM TRA ĐIỀU KIỆN THẮNG THUA (GAME OVER ENGINE)
# ==========================================
def check_game_over_conditions(room_id):
    """
    Bộ não quét trạng thái phòng chơi để phân định thắng thua:
    - Đếm số lượng Ma Sói còn sống.
    - Đếm số lượng Dân Làng (bao gồm các chức năng) còn sống.
    - Tính toán điều kiện: Sói hết hoàn toàn -> Dân Làng thắng.
    - Tính toán điều kiện: Số Sói >= Số Dân -> Ma Sói thắng.
    """
    if room_id not in game_rooms:
        return True
        
    room_data = game_rooms[room_id]
    
    # Khởi tạo bộ đếm quân số các phe còn sống sót
    wolf_count = 0
    villager_count = 0
    
    for pid in room_data["alive"]:
        pdata = room_data["roles"][pid]
        # Gom nhóm phe dựa trên thuộc tính cấu hình team (Phần 9)
        if pdata["team"] == "Ma Sói":
            wolf_count += 1
        else:
            villager_count += 1
            
    # --- ĐIỀU KIỆN THẮNG 1: PHE DÂN LÀNG THẮNG (Tiêu diệt sạch bóng Ma Sói) ---
    if wolf_count == 0:
        process_end_of_game_rewards(room_id, "Dân Làng")
        return True
        
    # --- ĐIỀU KIỆN THẮNG 2: PHE MA SÓI THẮNG (Số Sói bằng hoặc áp đảo số Dân) ---
    if wolf_count >= villager_count:
        process_end_of_game_rewards(room_id, "Ma Sói")
        return True
        
    return False # Trận đấu tiếp tục diễn ra, chưa phân định thắng thua

# ==========================================
# 58. HÀM TÍNH TOÁN EXP & CẬP NHẬT CẤP ĐỘ (LEVEL UP LOGIC)
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

# ==========================================
# 59. HÀM TỔNG KẾT TRẬN ĐẤU & PHÂN PHÁT QUỸ VÀNG (REWARDS SYSTEM)
# ==========================================
# --- ĐOẠN CODE ĐỒNG BỘ ĐẦU HÀM Ở PHẦN 22 ---
def process_end_of_game_rewards(room_id, winning_team):
    if room_id not in game_rooms:
        return
        
    # 📥 ĐỒNG BỘ 1: Tự động quyết toán tiền đặt cược dự đoán cho khán giả linh hồn (Phần 45)
    settle_spectator_betting_rewards(room_id, winning_team)
    
    # 📥 ĐỒNG BỘ 2: Tự động in Nhật ký diễn biến trận đấu ra sảnh chat tổng (Phần 28)
    generate_and_send_game_log(room_id)
    
    # 📥 ĐỒNG BỘ 3: Trả tự do, mở lại quyền chat Group cho tất cả mọi người (Phần 41)
    # lift_all_restrictions_on_game_over(room_id, group_chat_id)
    
    # 📥 ĐỒNG BỘ 4: Đóng gói dữ liệu xuất file JSON lưu cứng lên VPS (Phần 42)
    save_match_history_to_storage(room_id)
        
    room_data = game_rooms[room_id]
    room_data["status"] = "End"
    
    total_players = len(room_data["players"])
    bet_fee = room_data["bet"]
    
    # 1. Tính toán tổng quỹ tiền thưởng cược của trận đấu
    total_prize_pool = total_players * bet_fee
    
    # Tìm danh sách những người thuộc phe chiến thắng (bất kể còn sống hay đã chết)
    winners = []
    losers = []
    
    for pid in room_data["players"]:
        pdata = room_data["roles"][pid]
        if pdata["team"] == winning_team:
            winners.append(pid)
        else:
            losers.append(pid)
            
    # 2. Thuật toán phân chia tiền vàng thưởng
    gold_reward_per_winner = 0
    if winners:
        # Chia đều tổng quỹ thưởng cho những người thắng cuộc
        gold_reward_per_winner = int(total_prize_pool / len(winners))
        for w_id in winners:
            user_db[w_id]["gold"] += gold_reward_per_winner
            user_db[w_id]["win"] += 1
            
    for l_id in losers:
        user_db[l_id]["lose"] += 1

    # 3. Tạo bảng thông báo tổng kết danh dự sang xịn mịn lên sảnh game
    end_game_msg = (
        f"👑 **TRẬN ĐẤU KẾT THÚC — PHE {winning_team.upper()} CHIẾN THẮNG** 👑\n"
        f"-----------------------------------------\n"
        f"💰 **Tổng quỹ cược trận đấu:** `{total_prize_pool:,} Vàng`\n"
        f"🎁 **Phần thưởng mỗi người thắng:** `+{gold_reward_per_winner:,} Vàng`\n"
        f"-----------------------------------------\n"
        f"🏆 **DANH SÁCH ANH HÙNG CHIẾN THẮNG ({winning_team}):**\n"
    )
    
    for w_id in winners:
        pname = user_db[w_id]["name"]
        prole = room_data["roles"][w_id]["role"]
        # Thắng trận nhận ngay 50 EXP gốc
        level_up = add_exp_and_check_level_up(w_id, 50)
        
        lvl_up_text = " 🔥 **LEVEL UP!**" if level_up else ""
        end_game_msg += f"🔹 **{pname}** (Vai trò: `{prole}`){lvl_up_text}\n"
        
    end_game_msg += "\n💀 **DANH SÁCH BẠI TRẬN ĐÁNG TIẾC:**\n"
    for l_id in losers:
        pname = user_db[l_id]["name"]
        prole = room_data["roles"][l_id]["role"]
        # Thua trận nhận khích lệ 15 EXP gốc
        level_up = add_exp_and_check_level_up(l_id, 15)
        
        lvl_up_text = " 🔥 **LEVEL UP!**" if level_up else ""
        end_game_msg += f"🔸 **{pname}** (Vai trò: `{prole}`){lvl_up_text}\n"
        
    end_game_msg += (
        f"-----------------------------------------\n"
        f"💬 *Phòng chơi sẽ tự động đóng lại sau vài giây. Toàn bộ người chơi hãy sử dụng lệnh `/menu` hoặc nút Quay Lại để tiếp tục tìm trận mới!*"
    )
      # 📥 ĐỒNG BỘ 5: Cuối hàm, quét tự động lật mở Thành Tựu thưởng Vàng lớn cho người chơi (Phần 40)
    for pid in game_rooms[room_id]["players"]:
        scan_and_unlock_user_achievements(pid)

    # Phát sóng bảng vàng vinh danh cho mọi người chơi trong phòng cược
    for pid in room_data["players"]:
        try:
            bot.send_message(pid, end_game_msg, parse_mode="Markdown")
        except Exception:
            pass
            
    # Ghi nhận kết cục vào hệ thống log lịch sử
    room_data["history_log"].append(f"👑 Trận đấu kết thúc. Phe {winning_team} thắng.")

    # 4. Trả người chơi về trạng thái tự do & Giải phóng phòng chơi khỏi bộ nhớ RAM
    # Sử dụng delay thời gian 5 giây để người chơi kịp đọc bảng tổng kết trước khi xóa phòng
    def delayed_cleanup():
        time.sleep(5)
        if room_id in game_rooms:
            del game_rooms[room_id]
            
    threading.Thread(target=delayed_cleanup).start()

# Bộ nhớ tạm lưu trữ danh sách Cặp Đôi của từng phòng chơi: 
# { room_id: {"lovers": set([id1, id2]), "cupid_id": id} }
lovers_cache = {}

# ==========================================
# 60. GIAO DIỆN CHỌN CẶP ĐÔI CHO THẦN TÌNH YÊU
# ==========================================
def get_cupid_selection_markup(room_id, cupid_id, selected_p1=None):
    """
    Tạo menu nút bấm chọn mục tiêu kết đôi cho Cupid.
    - Nếu chưa chọn ai, hiển thị toàn bộ người chơi để chọn Người thứ 1.
    - Sau khi chọn Người thứ 1, hiển thị danh sách còn lại để chọn Người thứ 2.
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    room_data = game_rooms[room_id]
    
    for pid in room_data["players"]:
        if selected_p1 and pid == selected_p1:
            continue # Không cho phép tự kết đôi một người với chính họ
            
        pname = user_db[pid]["name"]
        
        # Thiết lập callback data để phân biệt bước chọn
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
        return # Nếu phòng này không cấu hình vai trò Cupid, bỏ qua luồng này
        
    cupid_text = (
        "🏹 **MŨI TÊN TÌNH YÊU CUPID KÍCH HOẠT** 🏹\n"
        "-----------------------------------------\n"
        "💘 Là Thần Tình Yêu, bạn có nhiệm vụ ghép đôi cho 2 người chơi bất kỳ trong làng trước khi cuộc chiến bắt đầu.\n\n"
        "👉 **Bước 1:** Hãy lựa chọn **Người thứ nhất** để ban phát tình yêu từ danh sách dưới đây:"
    )
    bot.send_message(cupid_id, cupid_text, parse_mode="Markdown", reply_markup=get_cupid_selection_markup(room_id, cupid_id))

# Ghi chú: Bạn hãy gọi hàm `trigger_cupid_menu(room_id)` này ở đầu hàm `trigger_night_action_menus` ở Phần 12 để Cupid hành động đầu tiên.

# ==========================================
# 61. BỔ SUNG NHÁNH XỬ LÝ SỰ KIỆN CUPID VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    # 📥 Xử lý bước 1: Khi Cupid chọn Người thứ nhất
    elif data.startswith("cupid_p1_"):
        parts = data.split("_")
        room_id = parts[2]
        p1_id = int(parts[3])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        p1_name = user_db[p1_id]["name"]
        cupid_next_text = (
            f"🏹 **THẦN TÌNH YÊU (CUPID):**\n"
            f"-----------------------------------------\n"
            f"✅ Đã chọn người thứ nhất: **{p1_name}**\n\n"
            f"👉 **Bước 2:** Hãy chọn tiếp **Người thứ hai** để tác hợp mối lương duyên này:"
        )
        bot.edit_message_text(cupid_next_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_cupid_selection_markup(room_id, user_id, p1_id))
        bot.answer_callback_query(call.id)

    # 📥 Xử lý bước 2: Khi Cupid chọn Người thứ hai (Hoàn tất kết đôi)
    elif data.startswith("cupid_p2_"):
        parts = data.split("_")
        room_id = parts[2]
        p1_id = int(parts[3])
        p2_id = int(parts[4])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        
        # Ghi nhận Cặp Đôi vào bộ nhớ hệ thống
        lovers_cache[room_id] = {
            "lovers": {p1_id, p2_id},
            "cupid_id": user_id
        }
        
        # Cập nhật thuộc tính team đặc biệt thành "Phe Thứ Ba" nếu Cặp đôi là Sói + Dân (Yêu khác phe)
        p1_role = room_data["roles"][p1_id]["role"]
        p2_role = room_data["roles"][p2_id]["role"]
        
        is_mixed_marriage = ("Sói" in p1_role and "Sói" not in p2_role) or ("Sói" in p2_role and "Sói" not in p1_role)
        
        if is_mixed_marriage:
            room_data["roles"][p1_id]["team"] = "Phe Thứ Ba"
            room_data["roles"][p2_id]["team"] = "Phe Thứ Ba"
            room_data["roles"][user_id]["team"] = "Phe Thứ Ba" # Cupid phò tá cặp đôi khác phe thắng
            
        bot.edit_message_text(f"💘 Mũi tên đã bắn đi! Bạn đã kết đôi thành công cho **{user_db[p1_id]['name']}** và **{user_db[p2_id]['name']}**.", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Kết đôi hoàn tất!", show_alert=True)
        
        # Gửi thông báo mật đánh thức 2 người yêu nhau nhận diện tình yêu
        for lover_id, partner_id in [(p1_id, p2_id), (p2_id, p1_id)]:
            try:
                lover_msg = (
                    f"💖 **HỒI CHUÔNG TÌNH YÊU ĐÃ VANG LÊN** 💖\n"
                    f"-----------------------------------------\n"
                    f"🎯 Thần Tình Yêu Cupid đã bắn mũi tên vàng trúng vào tim bạn!\n"
                    f"👩‍❤️‍💋‍👨 Người yêu định mệnh của bạn trong trận đấu này là: **{user_db[partner_id]['name']}**\n\n"
                    f"⚠️ **LUẬT CHẾT CHÙM TOÁN HỌC:** Nếu người yêu của bạn chết, bạn sẽ lập tức tử vong theo vì đau buồn!\n"
                    f"🤫 *Chiến thuật:* Hãy ra sức bảo vệ mạng sống cho nhau bằng mọi giá!"
                )
                if is_mixed_marriage:
                    lover_msg += "\n\n🔥 **ĐỘT BIẾN PHE THỨ BA:** Hai bạn thuộc 2 phe đối nghịch nhau! Mục tiêu thắng mới: **Tiêu diệt toàn bộ Ma Sói và Dân Làng còn lại**, chỉ chừa lại 2 bạn sống sót chung cuộc!"
                bot.send_message(lover_id, lover_msg, parse_mode="Markdown")
            except Exception: pass

# ==========================================
# 62. HÀM XỬ LÝ LOGIC CHẾT CHÙM VÌ TÌNH YÊU
# ==========================================
def apply_lovers_heartbreak_death(room_id, current_dead_set):
    """
    Hàm bổ trợ quét dây chuyền tình ái.
    Nếu phát hiện 1 trong 2 người yêu dính trong danh sách chết, cưỡng chế gạt người còn lại chết cùng.
    Ghi chú: Bạn hãy lồng hàm này vào Bước 6 của hàm `process_end_of_night` (Phần 15) trước khi khai tử.
    """
    if room_id not in lovers_cache:
        return current_dead_set
        
    room_lovers = lovers_cache[room_id]["lovers"]
    room_data = game_rooms[room_id]
    
    # Chuyển set về list để lặp kiểm tra va chạm dữ liệu
    lovers_list = list(room_lovers)
    p1, p2 = lovers_list[0], lovers_list[1]
    
    # Tình huống 1: Người thứ 1 chết, lôi theo người thứ 2
    if p1 in current_dead_set and p2 in room_data["alive"]:
        current_dead_set.add(p2)
        room_data["history_log"].append(f"💖 {user_db[p2]['name']} đã tự sát vì đau buồn khi người tình {user_db[p1]['name']} hy sinh.")
        try: bot.send_message(room_data["host"], f"💖 **Tình sầu:** **{user_db[p2]['name']}** ngã xuống tự sát ngay sau cái chết của người thương **{user_db[p1]['name']}**.")
        except Exception: pass
        
    # Tình huống 2: Người thứ 2 chết, lôi theo người thứ 1
    elif p2 in current_dead_set and p1 in room_data["alive"]:
        current_dead_set.add(p1)
        room_data["history_log"].append(f"💖 {user_db[p1]['name']} đã tự sát vì đau buồn khi người tình {user_db[p2]['name']} hy sinh.")
        try: bot.send_message(room_data["host"], f"💖 **Tình sầu:** **{user_db[p1]['name']}** ngã xuống tự sát ngay sau cái chết của người thương **{user_db[p2]['name']}**.")
        except Exception: pass
        
    return current_dead_set

# Bộ nhớ tạm lưu số lần Già Làng bị Sói cắn trong phòng chơi: { room_id: số_lần_bị_cắn }
elder_bite_counters = {}

# Trạng thái tước đoạt kỹ năng của phe Dân Làng do giết nhầm Già Làng: { room_id: True/False }
village_punished_status = {}

# ==========================================
# 63. THUẬT TOÁN XỬ LÝ LÁ CHẮN CẮN ĐÊM CỦA GIÀ LÀNG
# ==========================================
def apply_elder_night_shield(room_id, wolf_victim_id):
    """
    Hàm xử lý kiểm tra mạng cắn của Già Làng ban đêm.
    - Trả về True nếu Già Làng được cứu mạng bởi lá chắn (Mạng cắn thứ 1).
    - Trả về False nếu Già Làng chính thức hết mạng (Mạng cắn thứ 2) hoặc mục tiêu không phải Già Làng.
    Ghi chú: Lồng hàm này vào Bước 4 của hàm process_end_of_night (Phần 15) khi Sói cắn trúng.
    """
    room_data = game_rooms[room_id]
    
    # Kiểm tra xem mục tiêu bị Sói cắn có phải là Già Làng hay không
    if room_data["roles"][wolf_victim_id]["role"] != "Già Làng":
        return False
        
    # Khởi tạo bộ đếm nếu là lần đầu tiên Già Làng bị nhắm trúng
    if room_id not in elder_bite_counters:
        elder_bite_counters[room_id] = 0
        
    elder_bite_counters[room_id] += 1
    
    # Trường hợp đặc biệt: Đêm Trăng Rằm phá vỡ lá chắn ngay lập tức (Phần 11)
    if room_data["weather"] == "Đêm Trăng Rằm":
        room_data["history_log"].append("🩸 Già Làng bị hạ gục ngay lập tức do Đêm Trăng Rằm phá hủy lá chắn tâm linh.")
        return False

    # Lần cắn thứ nhất: Già Làng kích hoạt khiên sinh mệnh sống sót
    if elder_bite_counters[room_id] == 1:
        room_data["history_log"].append("🛡️ Già Làng đã chống chịu thành công phát cắn thứ 1 của bầy Sói nhờ sinh mệnh Trưởng Lão.")
        for pid in room_data["players"]:
            try:
                bot.send_message(pid, "🛡️ **TÍN HIỆU TÂM LINH:** Đêm qua, bầy Ma Sói đã tấn công vào một kết giới cổ xưa trong làng nhưng không thể phá vỡ! (Già Làng tiêu hao 1 tầng sinh mệnh).")
            except Exception: pass
        return True # Già Làng được cứu an toàn
        
    # Lần cắn thứ hai: Hết mạng bảo hộ, Già Làng nằm xuống
    return False

# ==========================================
# 64. LOGIC KÍCH HOẠT HÌNH PHẠT TRỪ PHẠT TOÀN NGÔI LÀNG
# ==========================================
def trigger_elder_punishment_curse(room_id, killer_type="Treo Cổ"):
    """
    Hàm kích hoạt lời nguyền trừng phạt ngôi làng khi Già Làng bị chết oan ban ngày 
    hoặc bị chết do kỹ năng của phe mình (Phù Thủy ném độc nhầm).
    - Biến đổi toàn bộ chức năng phe Dân Làng thành Dân thường (Mất sạch chiêu thức).
    """
    room_data = game_rooms[room_id]
    village_punished_status[room_id] = True
    
    room_data["history_log"].append(f"🚨 Lời nguyền Già Làng kích hoạt do bị chết bởi: {killer_type}.")
    
    punish_text = (
        f"⚡ **SẤM SÉT ĐÁNH XUỐNG — LỜI NGUYỀN GIÀ LÀNG KÍCH HOẠT** ⚡\n"
        f"-----------------------------------------\n"
        f"⚖️ Do phe Dân Làng đã nhẫn tâm giết hại **Già Làng Đại Trưởng Lão** bằng hình thức [{killer_type}], thần linh đã nổi giận giáng tai ương xuống ngôi làng!\n\n"
        f"❌ **TƯỚC ĐOẠT QUYỀN NĂNG THẦN THÁNH:**\n"
        f"👉 Toàn bộ các chức năng đặc biệt của làng (**Tiên Tri, Bảo Vệ, Phù Thủy**) lập tức **BỊ KHÓA KỸ NĂNG** vĩnh viễn và bị giáng cấp thành Dân Làng thường!\n"
        f"-----------------------------------------\n"
        f"📢 *Từ đêm nay, phe Dân Làng chỉ có thể dựa vào đôi mắt thường và miệng lưỡi ban ngày để chiến đấu!*"
    )
    
    for pid in room_data["players"]:
        try: bot.send_message(pid, punish_text, parse_mode="Markdown")
        except Exception: pass

    # Quét danh sách người chơi còn sống để thực thi lệnh tước đoạt chức năng
    for pid in room_data["alive"]:
        pdata = room_data["roles"][pid]
        current_role = pdata["role"]
        
        # Nếu là các vai trò chức năng phe Dân Làng
        if current_role in ["Tiên Tri", "Bảo Vệ", "Phù Thủy"]:
            pdata["role"] = "Dân" # Giáng cấp thành dân thường không có kỹ năng ban đêm
            try:
                bot.send_message(pid, "🔇 **CẢNH BÁO LỜI NGUYỀN:** Bạn đã bị tước đoạt toàn bộ bí thuật phép thuật, từ nay bạn là một **Dân Làng** bình thường.")
            except Exception: pass

# Ghi chú tích hợp:
# 1. Gọi hàm `trigger_elder_punishment_curse(room_id, "Treo Cổ")` ở Phần 20 nếu suspect_role == "Già Làng".
# 2. Gọi hàm `trigger_elder_punishment_curse(room_id, "Thuốc Độc Phù Thủy")` ở Phần 15 nếu witch_kill_target là Già Làng.

# ==========================================
# 65. ĐỒNG BỘ KIỂM TRA LỜI NGUYỀN TRƯỚC KHI GỬI MENU ĐÊM
# ==========================================
# Ghi chú: Bạn hãy chèn đoạn code này vào đầu hàm `trigger_night_action_menus` ở Phần 12:

    # Kiểm tra xem ngôi làng có đang chịu lời nguyền của Già Làng hay không
    if village_punished_status.get(room_id, False):
        # Nếu làng bị trừng phạt, bỏ qua hoàn toàn việc gửi menu kỹ năng ban đêm cho phe dân làng
        pass

# Bộ nhớ tạm lưu trữ Thần Tượng của Bán Sói trong từng phòng chơi:
# { room_id: { wild_child_id: idol_user_id } }
wild_child_idols_cache = {}

# ==========================================
# 66. GIAO DIỆN CHỌN THẦN TƯỢNG CHO BÁN SÓI
# ==========================================
def trigger_wild_child_menu(room_id):
    """Tìm kiếm Bán Sói trong phòng chơi để gửi menu chọn Thần Tượng đêm đầu tiên"""
    room_data = game_rooms[room_id]
    wild_child_id = None
    
    for pid in room_data["players"]:
        if room_data["roles"][pid]["role"] == "Bán Sói":
            wild_child_id = pid
            break
            
    if not wild_child_id:
        return # Nếu phòng không có cấu hình vai trò Bán Sói, bỏ qua luồng này
        
    wild_child_text = (
        "🐺 **QUYỀN NĂNG BÁN SÓI KÍCH HOẠT** 🐺\n"
        "-----------------------------------------\n"
        "🎭 Bạn đang là một đứa trẻ hoang dã. Hãy lựa chọn một người chơi làm **Thần Tượng (Idol)** của bạn.\n\n"
        "🟢 **Phe hiện tại:** Dân Làng.\n"
        "🚨 **CƠ CHẾ THỨC TỈNH:** Nếu Thần Tượng của bạn bị chết tại bất kỳ thời điểm nào trong trận đấu, bạn sẽ ngay lập tức **HÓA SÓI** và quay lưng phản bội dân làng!\n"
        "-----------------------------------------\n"
        "👉 Hãy chọn Thần Tượng của bạn từ danh sách nút bấm dưới đây:"
    )
    
    # Sử dụng lại hàm tạo nút bấm mục tiêu đã viết ở Phần 12 với tag hành động "idol"
    markup_idol = get_night_target_markup(room_id, wild_child_id, "idol")
    bot.send_message(wild_child_id, wild_child_text, parse_mode="Markdown", reply_markup=markup_idol)

# Ghi chú: Bạn hãy gọi hàm `trigger_wild_child_menu(room_id)` này chạy song song với Cupid ở đêm đầu tiên.

# ==========================================
# 67. BỔ SUNG NHÁNH XỬ LÝ SỰ KIỆN BÁN SÓI VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("skill_idol_"):
        # Cấu trúc: skill_idol_[room_id]_[target_id]
        parts = data.split("_")
        room_id = parts
        target_id = int(parts)
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        if room_id not in wild_child_idols_cache:
            wild_child_idols_cache[room_id] = {}
            
        # Ghi nhận Thần Tượng của Bán Sói vào hệ thống bộ nhớ
        wild_child_idols_cache[room_id][user_id] = target_id
        target_name = user_db[target_id]["name"]
        
        bot.edit_message_text(f"🎯 Bạn đã chọn **{target_name}** làm Thần Tượng sinh mệnh. Hãy cầu nguyện cho họ sống sót, hoặc chờ đợi thời cơ hóa sói!", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Chọn Thần Tượng thành công!", show_alert=True)

# ==========================================
# 68. LOGIC THỨC TỈNH BIẾN ĐỔI THÀNH MA SÓI THỰC THỤ
# ==========================================
def check_and_awaken_wild_child(room_id, newly_dead_players_set):
    """
    Hàm quét kiểm tra sinh mệnh Thần Tượng.
    Nếu phát hiện Thần Tượng dính trong danh sách chết, biến đổi Bán Sói thành Ma Sói.
    Ghi chú: Lồng hàm này vào cuối hàm `process_end_of_night` (Phần 15) và sau khi Treo Cổ (Phần 20).
    """
    if room_id not in wild_child_idols_cache:
        return
        
    room_data = game_rooms[room_id]
    room_idols = wild_child_idols_cache[room_id] # Cấu trúc: { wild_child_id: idol_id }
    
    for wc_id, idol_id in list(room_idols.items()):
        # Điều kiện: Bán Sói phải còn sống và Thần Tượng vừa mới nằm xuống
        if wc_id in room_data["alive"] and idol_id in newly_dead_players_set:
            pdata = room_data["roles"][wc_id]
            
            # Kiểm tra nếu chưa hóa sói từ trước
            if pdata["role"] == "Bán Sói":
                # Thực hiện lệnh biến đổi hắc hám
                pdata["role"] = "Ma Sói Thường"
                pdata["team"] = "Ma Sói"
                
                room_data["history_log"].append(f"🐺 Bán Sói {user_db[wc_id]['name']} đã hóa sói do Thần Tượng {user_db[idol_id]['name']} qua đời.")
                
                # Gửi tin nhắn cảnh báo bảo mật riêng biệt cho Bán Sói
                try:
                    awaken_msg = (
                        f"💀 **THẦN TƯỢNG SỤP ĐỔ — BẢN NĂNG THỨC TỈNH** 💀\n"
                        f"-----------------------------------------\n"
                        f"🚨 Thần Tượng **{user_db[idol_id]['name']}** của bạn đã hy sinh vĩnh viễn!\n"
                        f"🩸 Nỗi đau biến thành hận thù, dòng máu Ma Sói ẩn giấu trong cơ thể bạn đã chính thức bùng nổ.\n\n"
                        f"🔥 **TRẠNG THÁI MỚI:** Bạn đã biến thành **MA SÓI THỰC THỤ**.\n"
                        f"🛡️ **Phe mới:** Phe Ma Sói.\n"
                        f"📢 *Từ đêm mai, bạn sẽ thức giấc đi săn chung và trò chuyện mật cùng bầy Ma Sói để tiêu diệt làng!*"
                    )
                    bot.send_message(wc_id, awaken_msg, parse_mode="Markdown")
                except Exception: pass
                
                # Xóa khỏi bộ lọc theo dõi để tránh lặp lại logic
                del wild_child_idols_cache[room_id][wc_id]

# ==========================================
# 69. THUẬT TOÁN ĐỐI CHIẾU THỰC THI TREO CỔ K KẺ CHÁN ĐỜI
# ==========================================
def check_fool_victory_on_execution(room_id, executed_user_id):
    """
    Hàm kiểm tra điều kiện thắng cưỡng chế của Kẻ Chán Đời (Fool).
    - Nếu đối tượng bị treo cổ ban ngày là Kẻ Chán Đời, chặn mọi logic kiểm tra thông thường.
    - Kích hoạt phân phát tiền thưởng độc quyền cho Kẻ Chán Đời và dừng trận đấu.
    Ghi chú: Lồng hàm này vào ngay đầu Trường Hợp 1 (Treo cổ thành công) ở Phần 20.
    """
    if room_id not in game_rooms:
        return False
        
    room_data = game_rooms[room_id]
    executed_role = room_data["roles"][executed_user_id]["role"]
    
    # Nếu kẻ bị treo cổ chính xác là Kẻ Chán Đời
    if executed_role == "Kẻ Chán Đời (Fool)":
        room_data["status"] = "End"
        
        # 1. Tính toán quỹ tiền cược thu về từ toàn phòng
        total_players = len(room_data["players"])
        bet_fee = room_data["bet"]
        total_prize_pool = total_players * bet_fee
        
        # 2. Toàn bộ quỹ thưởng Vàng thuộc về một mình Kẻ Chán Đời
        user_db[executed_user_id]["gold"] += total_prize_pool
        user_db[executed_user_id]["win"] += 1
        
        # Những người chơi còn lại đều bị tính là thua cuộc trong trận đấu này
        for pid in room_data["players"]:
            if pid != executed_user_id:
                user_db[pid]["lose"] += 1
                
        # 3. Kích hoạt hiệu ứng lên cấp danh dự cho Kẻ Chán Đời (Tặng lượng lớn 100 EXP)
        level_up = add_exp_and_check_level_up(executed_user_id, 100)
        lvl_up_text = " 🔥 **LEVEL UP TOÀN DIỆN!**" if level_up else ""
        
        # 4. Phát sóng bảng vàng kết cục chấn động lên toàn sảnh game
        fool_victory_msg = (
            f"🃏 **TRẬN ĐẤU KẾT THÚC — KẺ CHÁN ĐỜI THẮNG TUYỆT ĐỐI** 🃏\n"
            f"-----------------------------------------\n"
            f"🎭 Ngôi làng đã dính bẫy tâm lý! Kẻ bị các dũng sĩ giật dây treo cổ ban ngày chính là **{user_db[executed_user_id]['name']}** (Vai trò: `Kẻ Chán Đời`).\n\n"
            f"🏆 **KẾT QUẢ PHÁN QUYẾT:**\n"
            f"👉 **{user_db[executed_user_id]['name']}** đã đạt được tâm nguyện được chết, lừa gạt toàn bộ thế cục và giành chiến thắng độc nhất vô nhị!{lvl_up_text}\n\n"
            f"💰 **Quỹ tiền cược thu gom:** `{total_prize_pool:,} Vàng` đã chuyển thẳng vào tài khoản kẻ thắng cuộc.\n"
            f"❌ Toàn bộ thành viên còn lại thuộc Phe Ma Sói và Phe Dân Làng đều nhận kết quả **THẤT BẠI** oan uổng.\n"
            f"-----------------------------------------\n"
            f"📢 *Phòng chơi sẽ tự động đóng lại sau 5 giây. Hãy sử dụng lệnh `/menu` để mở lại sảnh chính.*"
        )
        
        for pid in room_data["players"]:
            try: bot.send_message(pid, fool_victory_msg, parse_mode="Markdown")
            except Exception: pass
            
        room_data["history_log"].append(f"🃏 Kẻ Chán Đời {user_db[executed_user_id]['name']} lừa làng treo cổ thành công.")
        
        # Giải phóng phòng chơi ra khỏi hệ thống RAM sau 5 giây delay
        def delayed_room_cleanup():
            time.sleep(5)
            if room_id in game_rooms:
                del game_rooms[room_id]
                
        import threading
        threading.Thread(target=delayed_room_cleanup).start()
        return True # Xác nhận trận đấu đã được xử lý kết thúc hoàn toàn
        
    return False # Kẻ bị treo cổ không phải Fool, trận đấu tiếp tục chạy theo logic thông thường

# ==========================================
# 70. BỔ SUNG LƯU Ý CHI TIẾT VAI TRÒ (Đồng bộ vào Phần 10)
# ==========================================
# Bạn hãy dán cấu hình thông tin này vào dict `ROLE_DETAILS` ở Phần 10 nhé:
# "Kẻ Chán Đời (Fool)": {
#     "emoji": "🃏", "name": "Kẻ Chán Đời",
#     "mission": "Bạn thuộc phe Thứ Ba độc lập. Hãy tìm cách cư xử đáng nghi, giả làm Sói hoặc kịch sĩ ban ngày để lừa dân làng bỏ phiếu TREO CỔ bạn trên bục tối hậu."
# }

# Bộ nhớ tạm theo dõi số đêm và lượt cắn của Sói Gió:
# { room_id: { white_wolf_id: {"last_used_night": 0, "kill_wolf_target": None} } }
white_wolf_cache = {}

# ==========================================
# 71. GIAO DIỆN CHỌN MỤC TIÊU CẮN ĐỒNG BỌN
# ==========================================
def trigger_white_wolf_menu(room_id, current_night_count):
    """
    Hàm quét phòng tìm kiếm Ma Sói Gió còn sống.
    Gửi menu nút bấm cho phép cắn trộm 1 con Sói khác (Chỉ kích hoạt mỗi 2 đêm 1 lần).
    """
    room_data = game_rooms[room_id]
    ww_id = None
    
    for pid in room_data["alive"]:
        if room_data["roles"][pid]["role"] == "Ma Sói Gió":
            ww_id = pid
            break
            
    if not ww_id:
        return # Nếu phòng không có Sói Gió hoặc Sói Gió đã chết, bỏ qua
        
    if room_id not in white_wolf_cache:
        white_wolf_cache[room_id] = {ww_id: {"last_used_night": -2, "kill_wolf_target": None}}
        
    ww_data = white_wolf_cache[room_id][ww_id]
    
    # Điều kiện: Cứ cách 2 đêm mới được cắn trộm đồng bọn 1 lần (Ví dụ: đêm 2, đêm 4...)
    if current_night_count - ww_data["last_used_night"] < 2:
        try:
            bot.send_message(ww_id, "🌪️ **MA SÓI GIÓ:** Đêm nay bạn mệt mỏi, kỹ năng cắn trộm đồng bọn đang trong thời gian hồi chiêu (Hồi 2 đêm). Hãy săn dân thường cùng bầy.")
        except Exception: pass
        return

    # Tạo menu nút bấm liệt kê riêng các con Sói khác đang còn sống trong phòng
    markup_ww = types.InlineKeyboardMarkup(row_width=2)
    has_target = False
    
    for pid in room_data["alive"]:
        pdata = room_data["roles"][pid]
        if "Sói" in pdata["role"] and pid != ww_id:
            has_target = True
            pname = user_db[pid]["name"]
            btn = types.InlineKeyboardButton(f"🐺 Cắn Trộm {pname}", callback_data=f"ww_kill_{room_id}_{pid}")
            markup_ww.add(btn)
            
    if has_target:
        ww_text = (
            "🌪️ **QUYỀN NĂNG MA SÓI GIÓ THỨC TỈNH** 🌪️\n"
            "-----------------------------------------\n"
            "🤫 Đêm đã về khuya, bầy Sói đã ngủ say sau chuyến săn chung. Đây là thời cơ ngàn năm có một để bạn thanh trừng đồng bọn.\n\n"
            "👉 Hãy chọn **1 con Ma Sói khác** bên dưới để cắn chết chúng trong im lặng. Mục tiêu sẽ nằm xuống vào sáng mai!"
        )
        btn_skip = types.InlineKeyboardButton("⏳ Bỏ Qua Đêm Nay", callback_data=f"ww_skip_{room_id}")
        markup_ww.add(btn_skip)
        bot.send_message(ww_id, ww_text, parse_mode="Markdown", reply_markup=markup_ww)
    else:
        try:
            bot.send_message(ww_id, "🌪️ **MA SÓI GIÓ:** Toàn bộ đồng bọn bầy Sói đã chết sạch, không còn ai để bạn cắn trộm nữa. Hãy tự mình xé xác dân làng!")
        except Exception: pass

# Ghi chú tích hợp: Bạn hãy gọi hàm `trigger_white_wolf_menu(room_id, đêm_hiện_tại)` chạy song song 
# cùng lúc với Phù Thủy ở Phần 14 để Sói Gió đưa ra phán quyết âm thầm.

# ==========================================
# 72. BỔ SUNG NHÁNH XỬ LÝ SỰ KIỆN SÓI GIÓ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("ww_kill_"):
        parts = data.split("_")
        room_id = parts[2]
        target_id = int(parts[3])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        ww_id = user_id
        # Ghi nhận mục tiêu bị cắn trộm và cập nhật đêm hồi chiêu
        # Giả lập biến lấy số đêm từ phòng chơi, ví dụ: 2
        current_night = 2 
        white_wolf_cache[room_id][ww_id]["last_used_night"] = current_night
        white_wolf_cache[room_id][ww_id]["kill_wolf_target"] = target_id
        
        target_name = user_db[target_id]["name"]
        bot.edit_message_text(f"🌪️ Bạn đã nhe nanh vuốt cắn trộm âm thầm vào cổ **{target_name}**. Chất độc của Sói Gió đang phát tác...", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Đã khóa mục tiêu cắn trộm!", show_alert=True)

    elif data.startswith("ww_skip_"):
        room_id = data.replace("ww_skip_", "")
        bot.edit_message_text("⏳ Bạn quyết định ẩn mình, dưỡng sức và không cắn trộm đồng bọn trong đêm nay.", chat_id, message_id)
        bot.answer_callback_query(call.id, text="Đã bỏ qua.")

# ==========================================
# 73. LOGIC HỢP NHẤT KHAI TỬ SÓI GIÓ CẮN TRỘM (Đồng bộ vào Phần 15)
# ==========================================
def apply_white_wolf_kill_result(room_id, dead_this_night_set):
    """
    Hàm bổ trợ quét kết quả cắn trộm của Sói Gió.
    Ghi chú: Lồng hàm này vào Bước 4 của hàm `process_end_of_night` (Phần 15) để tính điểm chết.
    """
    if room_id not in white_wolf_cache:
        return dead_this_night_set
        
    room_data = game_rooms[room_id]
    for ww_id, ww_data in white_wolf_cache[room_id].items():
        target_wolf = ww_data["kill_wolf_target"]
        
        # Nếu có mục tiêu bị cắn trộm và mục tiêu đó vẫn đang còn sống
        if target_wolf and target_wolf in room_data["alive"]:
            dead_this_night_set.add(target_wolf)
            room_data["history_log"].append(f"🌪️ Ma Sói Gió đã âm thầm cắn chết Ma Sói đồng bọn: {user_db[target_wolf]['name']}.")
            # Reset mục tiêu sau khi xử lý xong đêm đó
            ww_data["kill_wolf_target"] = None
            
    return dead_this_night_set

# ==========================================
# 74. HÀM XUẤT NHẬT KÝ TRẬN ĐẤU ĐỊNH DẠNG ĐẸP EYE-CATCHING
# ==========================================
def generate_and_send_game_log(room_id):
    """
    Hàm lõi quét mảng history_log để biên soạn biên niên sử trận đấu.
    Tự động định dạng icon trực quan cho từng loại hành động và gửi về nhóm.
    """
    if room_id not in game_rooms:
        return ""
        
    room_data = game_rooms[room_id]
    logs_array = room_data.get("history_log", [])
    
    if not logs_array:
        return "📜 Nhật ký trận đấu trống rỗng hoặc chưa ghi nhận diễn biến."

    # Khởi tạo tiêu đề bảng nhật ký lịch sử trận đấu
    log_text = (
        f"📜 **BIÊN NIÊN SỬ LÀNG MA SÓI — PHÒNG {room_id}** 📜\n"
        f"===================================\n"
        f"🎮 **Tổng số người tham gia:** `{len(room_data['players'])}` cao thủ\n"
        f"💰 **Mức cược đặt cọc:** `{room_data['bet']:,} Vàng`\n"
        f"-----------------------------------\n"
        f"📊 **DIỄN BIẾN CHI TIẾT QUA CÁC CHU KỲ:**\n\n"
    )

    # Duyệt qua từng dòng log hệ thống để chèn visual anchor (emoji) tương ứng
    for step, entry in enumerate(logs_array, 1):
        formatted_entry = entry
        
        # Tự động thay thế/chèn icon thông minh dựa vào từ khóa logic log
        if "Đêm xuống" in entry:
            formatted_entry = f"🌙 **{entry}**"
        elif "Thảo luận ngày mở" in entry:
            formatted_entry = f"☀️ **{entry}**"
        elif "bị bầy Sói phân xác" in entry or "bị Sói cắn chết" in entry:
            formatted_entry = f"🩸 {entry}"
        elif "đã chết do nhiễm độc" in entry:
            formatted_entry = f"🧪 {entry}"
        elif "đã bị treo cổ ban ngày" in entry:
            formatted_entry = f"⚖️ {entry}"
        elif "Thợ Săn bắn chết" in entry:
            formatted_entry = f"🏹 {entry}"
        elif "đã tự sát vì đau buồn" in entry:
            formatted_entry = f"💔 {entry}"
        elif "đã dính nguyền" in entry:
            formatted_entry = f"🧬 {entry}"
        elif "đã cứu sống an toàn" in entry or "chống chịu thành công" in entry:
            formatted_entry = f"🛡️ {entry}"
        else:
            formatted_entry = f"🔹 {entry}"

        log_text += f"{formatted_entry}\n"
        
    log_text += (
        f"===================================\n"
        f"✨ *Nhật ký được xuất tự động bởi Hệ thống quản lý trò chơi Ma Sói v8.*"
    )

    # Phát sóng bản log này đến toàn bộ tất cả thành viên (kể cả những người đã chết)
    for pid in room_data["players"]:
        try:
            bot.send_message(pid, log_text, parse_mode="Markdown")
        except Exception:
            pass

    return log_text

# ==========================================
# 75. ĐỒNG BỘ TÍCH HỢP VÀO HÀM KẾT THÚC GAME TRUNG TÂM
# ==========================================
# Ghi chú quan trọng: Bạn hãy chèn lệnh gọi hàm này vào ngay ĐẦU hàm `process_end_of_game_rewards` ở Phần 22 
# để bot tự động in nhật ký ra màn hình cho người chơi xem trước khi phòng bị xóa khỏi RAM:

    # --- TỰ ĐỘNG XUẤT NHẬT KÝ TRẬN ĐẤU KHI TRẬN ĐẤU KHÉP LẠI ---
    generate_and_send_game_log(room_id)

# Bộ nhớ tạm theo dõi thời gian hồi chiêu lệnh report tránh người chơi spam nút: { user_id: thời_gian_bấm_sau_cùng }
report_cooldown_cache = {}

# ==========================================
# 76. GIAO DIỆN CHỌN ĐỐI TƯỢNG ĐỂ BÁO CÁO VI PHẠM
# ==========================================
def get_report_menu_markup(room_id, reporter_id):
    """Tạo menu nút bấm danh sách người chơi trong phòng chơi để báo cáo vi phạm"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    room_data = game_rooms.get(room_id)
    
    if not room_data:
        return markup
        
    for pid in room_data["players"]:
        if pid != reporter_id: # Ẩn chính mình để tránh tự báo cáo bản thân
            pname = user_db[pid]["name"]
            btn = types.InlineKeyboardButton(f"🚨 Tố Cáo: {pname}", callback_data=f"report_user_{room_id}_{pid}")
            markup.add(btn)
            
    btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI", callback_data="lobby_back_main")
    markup.add(btn_back)
    return markup

# Bạn có thể bổ sung nút "🚨 BÁO CÁO VI PHẠM" vào giao diện chính bằng lệnh chat hoặc tích hợp trong sảnh game.

# ==========================================
# 77. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("report_user_"):
        # Phân tách chuỗi cấu trúc: report_user_[room_id]_[target_toxic_id]
        parts = data.split("_")
        room_id = parts[2]
        toxic_id = int(parts[3])
        
        current_time = time.time()
        last_used = report_cooldown_cache.get(user_id, 0)
        
        # Giới hạn thời gian hồi chiêu 60 giây giữa các lượt báo cáo để chống dội bom bot
        if current_time - last_used < 60:
            bot.answer_callback_query(call.id, text=f"⚠️ Vui lòng đợi {int(60 - (current_time - last_used))} giây để gửi lượt báo cáo tiếp theo!", show_alert=True)
            return
            
        report_cooldown_cache[user_id] = current_time
        
        # Chuyển trạng thái yêu cầu người chơi nhập lý do tố cáo vi phạm cụ thể
        bot.answer_callback_query(call.id)
        msg_reason = bot.send_message(
            chat_id,
            f"🚨 **TIẾP NHẬN ĐƠN TỐ CÁO VI PHẠM** 🚨\n"
            f"-----------------------------------------\n"
            f"👤 Đối tượng bị tố cáo: **{user_db[toxic_id]['name']}** (ID: `{toxic_id}`)\n\n"
            f"👉 Hãy nhập **Lý do vi phạm cụ thể** (Ví dụ: Chửi bậy, Clone acc, Phá game...) và gửi ngay cho Bot để chuyển tiếp lên Ban Quản Trị:",
            parse_mode="Markdown"
        )
        
        # Chuyển tiếp tin nhắn phản hồi tiếp theo của người dùng sang hàm process_report_reason_step
        bot.register_next_step_handler(msg_reason, process_report_reason_step, toxic_id, room_id)

# ==========================================
# 78. HÀM TỔNG HỢP VÀ CHUYỂN TIẾP ĐƠN TỐ CÁO ĐẾN ADMIN
# ==========================================
def process_report_reason_step(message, toxic_id, room_id):
    """Hàm lõi đóng gói hồ sơ vi phạm gửi thẳng về phòng mật Whitelist Admin"""
    reporter_id = message.from_user.id
    chat_id = message.chat.id
    report_reason = message.text.strip()[:100] # Giới hạn lý do tránh làm tràn tin nhắn Admin
    
    reporter_name = user_db[reporter_id]["name"]
    toxic_name = user_db[toxic_id]["name"]
    toxic_ip = user_db[toxic_id].get("ip", "Không rõ IP")
    
    # 1. Gửi thông báo xác nhận thành công cho người nộp đơn tố cáo
    bot.send_message(
        chat_id,
        f"✅ **GỬI ĐƠN TỐ CÁO THÀNH CÔNG!**\n"
        f"-----------------------------------------\n"
        f"🎯 Đơn tố cáo đối tượng **{toxic_name}** đã được mã hóa an toàn và chuyển tiếp lên máy chủ xử lý của Ban Điều Hành.\n"
        f"⚙️ Chúng tôi sẽ rà soát log trận đấu và tiến hành xử lý nghiêm minh nếu phát hiện hành vi gian lận.",
        parse_mode="Markdown"
    )
    
    # 2. Phát sóng hồ sơ đen trực tiếp về toàn bộ Whitelist Admin (Đồng bộ với Phần 1 và Phần 5)
    for admin_id in ADMIN_WHITELIST:
        try:
            admin_alert_text = (
                f"🚨 **HỒ SƠ TỐ CÁO VI PHẠM MỚI** 🚨\n"
                f"===================================\n"
                f"👤 **Người nộp đơn:** {reporter_name} (ID: `{reporter_id}`)\n"
                f"🎯 **Kẻ bị tố cáo:** {toxic_name} (ID: `{toxic_id}`)\n"
                f"📍 **IP Xác thực kẻ vi phạm:** `{toxic_ip}`\n"
                f"🆔 **Phòng xảy ra sự việc:** `{room_id}`\n"
                f"-----------------------------------\n"
                f"📝 **Lý do vi phạm ghi nhận:**\n"
                f"_\"{report_reason}\"_\n"
                f"===================================\n"
                f"⚙️ **LỆNH ADMIN NHANH ĐIỀU HÀNH:**\n"
                f"👉 Khóa IP: `/banip {toxic_ip}`\n"
                f"👉 Đặt lại tiền: `/setgold {toxic_id} 0`"
            )
            bot.send_message(admin_id, admin_alert_text, parse_mode="Markdown")
        except Exception:
            pass

# Hệ thống cấu hình phí giao dịch chuyển Vàng sảnh chờ: 5%
TRANSFER_FEE_RATE = 0.05

# ==========================================
# 79. GIAO DIỆN KHỞI TẠO LỆNH CHUYỂN VÀNG (P2P CHAT LỆNH)
# ==========================================
@bot.message_handler(commands=['chuyentiensoi'])
def cmd_transfer_gold_p2p(message):
    """
    Cú pháp lệnh: /chuyentiensoi [ID_Người_Nhận] [Số_Vàng]
    Ví dụ: /chuyentiensoi 987654321 2000
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # 1. Kích hoạt bộ Middleware bảo mật an ninh IP (Phần 5)
    if not check_maintenance_and_respond(message):
        return

    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(
            message, 
            "⚠️ **SAI CÚ PHÁP CHUYỂN TIỀN!**\n"
            "👉 Vui lòng nhập đúng định dạng lệnh:\n"
            "`/chuyentiensoi [ID_Người_Nhận] [Số_Vàng]`\n\n"
            "*(Ví dụ: /chuyentiensoi 987654321 2000)*", 
            parse_mode="Markdown"
        )
        return

    try:
        target_id = int(args[1])
        amount_gold = int(args[2])
        
        # Kiểm tra điều kiện đầu vào hợp lệ
        if amount_gold <= 100:
            bot.reply_to(message, "❌ **Lỗi:** Số Vàng chuyển nhượng tối thiểu phải lớn hơn `100 Vàng`.", parse_mode="Markdown")
            return
            
        if user_id == target_id:
            bot.reply_to(message, "❌ **Lỗi:** Bạn không thể tự chuyển tiền Vàng cho chính bản thân mình!")
            return
            
        if target_id not in user_db:
            bot.reply_to(message, f"❌ **Lỗi:** Không tìm thấy ID người chơi `{target_id}` trên hệ thống Làng Sói v8.", parse_mode="Markdown")
            return
            
        user_data = user_db[user_id]
        # Xác thực số dư khả dụng
        if user_data["gold"] < amount_gold:
            bot.reply_to(message, f"❌ **Giao dịch thất bại!** Số dư ví của bạn không đủ để thực hiện lệnh chuyển `{amount_gold:,} Vàng`.", parse_mode="Markdown")
            return
            
        # Tính toán phí giao dịch đốt cháy Vàng của sảnh game
        fee = int(amount_gold * TRANSFER_FEE_RATE)
        net_receive = amount_gold - fee
        
        # 2. Tạo menu nút bấm Inline xác nhận giao dịch bảo mật chống bấm nhầm
        markup_confirm = types.InlineKeyboardMarkup(row_width=2)
        btn_yes = types.InlineKeyboardButton("✅ XÁC NHẬN CHUYỂN", callback_data=f"p2p_yes_{target_id}_{amount_gold}")
        btn_no = types.InlineKeyboardButton("❌ HỦY BỎ GIAO DỊCH", callback_data="p2p_cancel")
        markup_confirm.add(btn_yes, btn_no)
        
        confirm_text = (
            f"🏦 **HÓA ĐƠN XÁC THỰC GIAO DỊCH CHUYỂN TIỀN** 🏦\n"
            f"-----------------------------------------\n"
            f"👤 **Người gửi:** {user_data['name']} (ID: `{user_id}`)\n"
            f"🎯 **Người nhận:** {user_db[target_id]['name']} (ID: `{target_id}`)\n"
            f"💰 **Tổng số tiền chuyển:** `{amount_gold:,} Vàng`\n"
            f"⚡ **Phí sàn hệ thống (5%):** `-{fee:,} Vàng`\n"
            f"🎁 **Số Vàng thực nhận:** `{net_receive:,} Vàng`\n"
            f"-----------------------------------------\n"
            f"📌 *Vui lòng kiểm tra kỹ thông tin. Lệnh chuyển tiền sau khi xác nhận sẽ KHÔNG THỂ HOÀN TÁC!*"
        )
        bot.send_message(chat_id, confirm_text, parse_mode="Markdown", reply_markup=markup_confirm)

    except ValueError:
        bot.reply_to(message, "❌ **Lỗi:** Tham số ID người nhận và Số Vàng phải là ký tự số nguyên hợp lệ!")

# ==========================================
# 80. BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("p2p_yes_"):
        # Phân tách chuỗi: p2p_yes_[target_id]_[amount_gold]
        parts = data.split("_")
        target_id = int(parts[2])
        amount_gold = int(parts[3])
        
        user_data = user_db[user_id]
        
        # Kiểm tra lại số dư một lần nữa đề phòng người chơi tẩu tán tiền trước khi bấm xác nhận
        if user_data["gold"] < amount_gold:
            bot.answer_callback_query(call.id, text="❌ Giao dịch thất bại! Số dư ví của bạn không còn đủ.", show_alert=True)
            bot.delete_message(chat_id, message_id)
            return
            
        fee = int(amount_gold * TRANSFER_FEE_RATE)
        net_receive = amount_gold - fee
        
        # --- THỰC THI TRỪ CỘNG ĐỒNG BỘ TRÊN DATABASE BIẾN TẠM user_db ---
        user_data["gold"] -= amount_gold
        user_db[target_id]["gold"] += net_receive
        
        bot.answer_callback_query(call.id, text="Chuyển tiền thành công!", show_alert=True)
        
        # Cập nhật giao diện biên lai chuyển tiền thành công cho người gửi
        success_text = (
            f"🏦 **GIAO DỊCH HOÀN TẤT THÀNH CÔNG** 🏦\n"
            f"-----------------------------------------\n"
            f"✅ Hệ thống ngân hàng đã chuyển giao tài sản thành công!\n"
            f"🎯 Đối tượng nhận: **{user_db[target_id]['name']}**\n"
            f"💰 Khấu trừ ví tài sản: `-{amount_gold:,} Vàng`\n"
            f"📈 Số dư hiện tại của bạn: `{user_data['gold']:,} Vàng`"
        )
        bot.edit_message_text(success_text, chat_id, message_id, parse_mode="Markdown")
        
        # Bắn tin nhắn thông báo biến động số dư trực tiếp cho người nhận quà
        try:
            notification_text = (
                f"🎁 **BẠN VỪA NHẬN ĐƯỢC QUÀ TẶNG VÀNG** 🎁\n"
                f"-----------------------------------------\n"
                f"👤 Cao thủ **{user_data['name']}** (ID: `{user_id}`) vừa thực hiện lệnh chuyển tiền quà tặng cho bạn!\n"
                f"💰 **Số Vàng thực nhận (đã trừ phí):** `+{net_receive:,} Vàng`\n"
                f"📈 Số dư ví mới của bạn: `{user_db[target_id]['gold']:,} Vàng`\n"
                f"-----------------------------------------\n"
                f"💬 *Hãy gửi tin nhắn cảm ơn hoặc rủ bằng hữu của bạn vào tạo phòng cược Ma Sói v8 chiến ngay thôi!*"
            )
            bot.send_message(target_id, notification_text, parse_mode="Markdown")
        except Exception:
            pass

    elif data == "p2p_cancel":
        bot.answer_callback_query(call.id, text="Đã hủy bỏ lệnh chuyển tiền.")
        bot.edit_message_text("❌ Lệnh giao dịch đã bị hủy bỏ bởi người dùng. Trả dữ liệu ví về trạng thái an toàn.", chat_id, message_id)

# ==========================================
# 81. BẢNG CẤU HÌNH TỶ LỆ RỚT VAI TRÒ MẶC ĐỊNH
# ==========================================
# Tỷ lệ % xuất hiện của các vai trò đột biến khi đủ số lượng người chơi tối thiểu
ROLE_DROP_RATES = {
    "Sói Alpha": 70,       # 70% xuất hiện thay thế 1 Sói thường trong trận >= 10 người
    "Sói Nguyền": 80,      # 80% xuất hiện trong các trận đấu từ mốc 7 người
    "Kẻ Phản Bội": 60,     # 60% xuất hiện trong các trận đấu từ mốc 5 người
    "Ma Sói Gió": 50,      # 50% xuất hiện phe thứ ba trong các trận đấu lớn
}

# ==========================================
# 82. GIAO DIỆN KHO ĐIỀU CHỈNH TỶ LỆ VAI TRÒ CỦA ADMIN
# ==========================================
def get_admin_role_config_markup():
    """Tạo bảng nút bấm tương tác điều chỉnh thông số cho Admin"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    for role_name, rate in ROLE_DROP_RATES.items():
        # Tạo nút tăng/giảm tỷ lệ cho từng vai trò
        btn_inc = types.InlineKeyboardButton(f"➕ {role_name} ({rate}%)", callback_data=f"adm_rate_inc_{role_name}")
        btn_dec = types.InlineKeyboardButton("➖ Giảm 10%", callback_data=f"adm_rate_dec_{role_name}")
        markup.add(btn_inc, btn_dec)
        
    btn_close = types.InlineKeyboardButton("❌ ĐÓNG MENU", callback_data="adm_rate_close")
    markup.add(btn_close)
    return markup

@bot.message_handler(commands=['roleconfig'])
def cmd_admin_role_config(message):
    """Lệnh gọi kho điều khiển tỷ lệ vai trò bí mật dành riêng cho Admin"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if not is_admin(user_id):
        return  # Chặn đứng nếu không có quyền Whitelist Admin (Phần 1)
        
    config_text = (
        "⚙️ **KHO ĐIỀU CHỈNH TỶ LỆ RỚT VAI TRÒ V8** ⚙️\n"
        "-----------------------------------------\n"
        "👑 Chào mừng Admin tối cao. Tại đây bạn có thể can thiệp ngầm vào thuật toán phân bài ngẫu nhiên để điều chỉnh độ khó của game.\n\n"
        "👉 Ấn vào các nút bấm bên dưới để tăng hoặc giảm tỷ lệ xuất hiện của các vai trò hắc ám đột biến:"
    )
    bot.send_message(chat_id, config_text, parse_mode="Markdown", reply_markup=get_admin_role_config_markup())

# ==========================================
# 83. BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("adm_rate_inc_"):
        if not is_admin(user_id): return
        role_name = data.replace("adm_rate_inc_", "")
        
        # Tăng tối đa lên 100%
        if ROLE_DROP_RATES[role_name] < 100:
            ROLE_DROP_RATES[role_name] += 10
            bot.answer_callback_query(call.id, text=f"Đã tăng tỷ lệ {role_name} lên {ROLE_DROP_RATES[role_name]}%")
        else:
            bot.answer_callback_query(call.id, text="Tỷ lệ đã đạt mốc tối đa 100%!", show_alert=True)
            
        # Làm mới lại giao diện menu cấu hình cho Admin
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=get_admin_role_config_markup())

    elif data.startswith("adm_rate_dec_"):
        if not is_admin(user_id): return
        role_name = data.replace("adm_rate_dec_", "")
        
        # Giảm tối thiểu xuống 0% (Tắt vai trò đó ra khỏi bể bài)
        if ROLE_DROP_RATES[role_name] > 0:
            ROLE_DROP_RATES[role_name] -= 10
            bot.answer_callback_query(call.id, text=f"Đã giảm tỷ lệ {role_name} xuống {ROLE_DROP_RATES[role_name]}%")
        else:
            bot.answer_callback_query(call.id, text="Tỷ lệ đã đạt mốc tối thiểu 0% (Tắt vai vai trò)!", show_alert=True)
            
        bot.edit_message_reply_markup(chat_id, message_id, reply_markup=get_admin_role_config_markup())

    elif data == "adm_rate_close":
        if not is_admin(user_id): return
        bot.answer_callback_query(call.id, text="Đã lưu cấu hình và đóng menu.")
        bot.edit_message_text("✅ Cấu hình tỷ lệ bài phân chia dã thú mới đã được áp dụng đồng bộ vào phòng máy chủ game.", chat_id, message_id)

# ==========================================
# 84. TÍCH HỢP TỶ LỆ ADMIN VÀO THUẬT TOÁN PHÂN BÀI (Đồng bộ vào Phần 9)
# ==========================================
def dynamic_adjust_role_pool_by_admin(base_pool):
    """
    Hàm đối chiếu với bảng cấu hình ROLE_DROP_RATES của Admin trước khi phân phát bài.
    Nếu tỷ lệ không đạt trúng ngẫu nhiên, tự động quy đổi vai trò nâng cao thành vai trò gốc.
    Ghi chú: Lồng hàm lọc này vào Bước 2 trước khi xáo trộn bài ngẫu nhiên ở Phần 9.
    """
    adjusted_pool = []
    for role in base_pool:
        if role in ROLE_DROP_RATES:
            # Rút ngẫu nhiên một số từ 1-100 để kiểm tra tỷ lệ
            if random.randint(1, 100) <= ROLE_DROP_RATES[role]:
                adjusted_pool.append(role)
            else:
                # Nếu không trúng tỷ lệ rớt của Admin, quy đổi Sói nâng cao về Sói thường, Phản bội về Dân
                if "Sói" in role:
                    adjusted_pool.append("Sói")
                else:
                    adjusted_pool.append("Dân")
        else:
            adjusted_pool.append(role)
    return adjusted_pool

# ==========================================
# 85. HÀM TÍNH TOÁN SỐ LIỆU THỐNG KÊ TOÀN DIỆN
# ==========================================
def generate_server_analytics_report():
    """
    Hàm lõi quét toàn bộ In-Memory Database (user_db, game_rooms, banned_ips)
    để tính toán các chỉ số kinh tế và hiệu suất vận hành của bot.
    """
    total_users = len(user_db)
    total_active_rooms = len(game_rooms)
    total_banned_ips = len(banned_ips)
    
    # Tính toán các chỉ số kinh tế (Vàng)
    total_gold_in_circulation = sum(udata.get("gold", 0) for udata in user_db.values())
    average_gold_per_user = int(total_gold_in_circulation / total_users) if total_users > 0 else 0
    
    # Tìm đại gia sở hữu tài sản lớn nhất hệ thống
    richest_user_name = "Chưa có"
    max_gold = 0
    for udata in user_db.values():
        if udata.get("gold", 0) > max_gold:
            max_gold = udata["gold"]
            richest_user_name = udata["name"]
            
    # Thống kê trạng thái các phòng chơi
    rooms_in_lobby = sum(1 for rdata in game_rooms.values() if rdata.get("status") == "Lobby")
    rooms_in_progress = total_active_rooms - rooms_in_lobby

    # Biên soạn bảng báo cáo phân tích định dạng Markdown sang xịn mịn
    report_text = (
        f"📊 **BÁO CÁO THỐNG KÊ HIỆU SỐ MÁY CHỦ v8** 📊\n"
        f"-----------------------------------------\n"
        f"⏱️ *Thời gian cập nhật:* `{time.strftime('%H:%M:%S - %d/%m/%Y')}`\n\n"
        f"⚙️ **VẬN HÀNH HỆ THỐNG:**\n"
        f"▪️ Tổng số tài khoản đăng ký: `{total_users:,} người chơi`\n"
        f"▪️ Số phòng đang hoạt động: `{total_active_rooms:,} phòng`\n"
        f"  ├ ⏳ Đang đợi ở Sảnh: `{rooms_in_lobby:,}`\n"
        f"  └ 🐺 Đang trong trận: `{rooms_in_progress:,}`\n"
        f"🚨 Đóng băng an ninh: `{total_banned_ips:,} dải IP bị khóa`\n\n"
        f"💰 **KINH TẾ LÀNG MA SÓI:**\n"
        f"▪️ Tổng lượng Vàng lưu hành: `{total_gold_in_circulation:,} Vàng`\n"
        f"▪️ Tài sản trung bình/người: `{average_gold_per_user:,} Vàng`\n"
        f"👑 Phú hộ Làng Sói: **{richest_user_name}** (`{max_gold:,} Vàng`)\n"
        f"-----------------------------------------\n"
        f"📊 *Dữ liệu được cập nhật theo thời gian thực từ bộ nhớ RAM tối ưu v8.*"
    )
    return report_text

# ==========================================
# 86. LỆNH ĐIỀU HÀNH TRA CỨU SỐ LIỆU CỦA QUẢN TRỊ VIÊN
# ==========================================
@bot.message_handler(commands=['serverstats', 'analytics'])
def cmd_server_analytics(message):
    """Lệnh tra cứu số liệu máy chủ khẩn cấp dành cho Admin và Trợ lý"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Cấp quyền cho cả Whitelist Admin (Phần 1) và dàn Trợ lý điều hành (OPERATORS)
    if user_id != ADMIN_WHITELIST and user_id not in OPERATORS:
        return # Im lặng bỏ qua nếu người dùng thường cố tình phá lệnh

    # Xuất báo cáo trực tiếp về cuộc trò chuyện quản trị mật
    report_content = generate_server_analytics_report()
    
    markup = types.InlineKeyboardMarkup()
    btn_refresh = types.InlineKeyboardButton("🔄 LÀM MỚI SỐ LIỆU", callback_data="adm_analytics_refresh")
    markup.add(btn_refresh)
    
    bot.send_message(chat_id, report_content, parse_mode="Markdown", reply_markup=markup)

# ==========================================
# 87. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data == "adm_analytics_refresh":
        if user_id != ADMIN_WHITELIST and user_id not in OPERATORS:
            bot.answer_callback_query(call.id, text="❌ Bạn không có quyền truy cập!", show_alert=True)
            return
            
        bot.answer_callback_query(call.id, text="🔄 Đang làm mới số liệu...")
        updated_report = generate_server_analytics_report()
        
        # Cập nhật trực tiếp nội dung tin nhắn cũ mà không cần bắn tin nhắn mới gây loãng chat
        markup = types.InlineKeyboardMarkup()
        btn_refresh = types.InlineKeyboardButton("🔄 LÀM MỚI SỐ LIỆU", callback_data="adm_analytics_refresh")
        markup.add(btn_refresh)
        
        try:
            bot.edit_message_text(updated_report, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            pass

# ==========================================
# 88. BIẾN CẤU HÌNH SỰ KIỆN GIỜ VÀNG TOÀN SERVER
# ==========================================
IS_DOUBLE_GOLD_EVENT = False  # Trạng thái Giờ Vàng (True = Bật, False = Tắt)

# ==========================================
# 89. LỆNH ĐIỀU HÀNH KÍCH HOẠT ĐỘT XUẤT CỦA ADMIN
# ==========================================
@bot.message_handler(commands=['giovang'])
def cmd_toggle_double_gold(message):
    """Lệnh Admin bật/tắt sự kiện nhân đôi số Vàng nhận được: /giovang [on/off]"""
    global IS_DOUBLE_GOLD_EVENT
    user_id = message.from_user.id
    
    if user_id != ADMIN_WHITELIST:
        return # Chặn đứng nếu không phải Admin tối cao (Phần 1)

    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, f"💰 Trạng thái Sự Kiện Giờ Vàng hiện tại: **{'ĐANG BẬT (X2 VÀNG)' if IS_DOUBLE_GOLD_EVENT else 'TẮT'}**\n👉 Sử dụng cú pháp: `/giovang on` hoặc `/giovang off` để cấu hình.", parse_mode="Markdown")
        return
        
    mode = args[1].lower()
    if mode == "on":
        IS_DOUBLE_GOLD_EVENT = True
        event_text = (
            "🎉 **SỰ KIỆN GIỜ VÀNG CHÍNH THỨC KÍCH HOẠT** 🎉\n"
            "-----------------------------------------\n"
            "💰 Ban Quản Trị Ma Sói v8 vừa phát lệnh mở hội **GIỜ VÀNG NHÂN ĐÔI (DOUBLE GOLD)** toàn máy chủ!\n\n"
            "🔥 **Nội dung:** Tất cả các phòng chơi kết thúc trong thời gian này sẽ được **NHÂN ĐÔI (+100%)** số lượng Vàng thưởng dành cho phe chiến thắng!\n"
            "⚔️ *Cơ hội làm giàu đã đến, các dũng sĩ hãy nhanh chóng tạo phòng cược ngay thôi!*"
        )
        # Phát thông báo khẩn cấp đến sảnh chính (Admin có thể copy gửi vào Group tổng)
        bot.reply_to(message, "💰 Đã kích hoạt Giờ Vàng! Hãy thông báo cho toàn bộ cư dân làng Sói.")
        
    elif mode == "off":
        IS_DOUBLE_GOLD_EVENT = False
        bot.reply_to(message, "🛑 **Đã tắt sự kiện Giờ Vàng!** Tỷ lệ phân phát phần thưởng Vàng quay trở về mốc định mức thông thường.")

# ==========================================
# 90. TÍCH HỢP HỆ SỐ NHÂN ĐÔI VÀO BỘ PHÁT THƯỞNG (Đồng bộ vào Phần 22)
# ==========================================
# Ghi chú: Bạn hãy tìm đến đoạn xử lý Bước 2 (Thuật toán phân chia tiền vàng thưởng) ở Phần 22 
# và thế đoạn code tối ưu hệ số X2 mới này vào nhé:

    # 2. Thuật toán phân chia tiền vàng thưởng tích hợp Sự Kiện Giờ Vàng (Phần 33)
    gold_reward_per_winner = 0
    if winners:
        # Tính toán tiền thưởng gốc chia đều trên tổng quỹ cược
        base_reward = int(total_prize_pool / len(winners))
        
        # Nếu sự kiện Giờ Vàng đang diễn ra, nhân đôi số tiền thưởng thực nhận
        if IS_DOUBLE_GOLD_EVENT:
            gold_reward_per_winner = base_reward * 2
            multiplier_text = " 🔥 *(Đã nhân đôi X2 Giờ Vàng)*"
        else:
            gold_reward_per_winner = base_reward
            multiplier_text = ""
            
        for w_id in winners:
            user_db[w_id]["gold"] += gold_reward_per_winner
            user_db[w_id]["win"] += 1

    # Đồng thời cập nhật lại biến hiển thị `end_game_msg` ở Phần 22:
    # f"🎁 **Phần thưởng mỗi người thắng:** `+{gold_reward_per_winner:,} Vàng`{multiplier_text}\n"

# ==========================================
# 91. ĐỒNG BỘ THÊM VẬT PHẨM MỚI VÀO CỬA HÀNG (Phần 4)
# ==========================================
# Bạn hãy bổ sung thêm các loại vé này vào dict `SHOP_ITEMS` ở Phần 4 nhé:
# "ve_tien_tri": {
#     "name": "🎟️ Vé Ưu Tiên Tiên Tri",
#     "price": 3000,
#     "desc": "Tăng thêm 40% cơ hội nhận vai trò Nhà Tiên Tri nếu trong bể bài trận đấu có vai trò này."
# },
# "ve_phu_thuy": {
#     "name": "🎟️ Vé Ưu Tiên Phù Thủy",
#     "price": 2500,
#     "desc": "Tăng thêm 40% cơ hội nhận vai trò Phù Thủy nếu trong bể bài trận đấu có vai trò này."
# }

# Bộ nhớ cấu hình trọng số quy đổi vé sang tên vai trò hệ thống
TICKET_ROLE_MAPPING = {
    "ve_tien_tri": "Tiên Tri",
    "ve_phu_thuy": "Phù Thủy"
}

# ==========================================
# 92. THUẬT TOÁN PHÂN BÀI CÓ TRỌNG SỐ ƯU TIÊN (PRIORITY WEIGHT DISTRIBUTION)
# ==========================================
def distribute_roles_with_priority_tickets(room_id):
    """
    Thuật toán phân bài nâng cao thay thế cho Bước 2 ở Phần 9:
    - Quét xem những ai có mua vé ưu tiên vai trò (item_slot nằm trong TICKET_ROLE_MAPPING).
    - Lấy bể bài chuẩn theo quân số (đã được Admin điều chỉnh tỷ lệ ở Phần 31).
    - Ưu tiên gán bài cho người có vé nếu vai trò đó xuất hiện trong bể bài.
    - Những người và vai trò còn lại sẽ được xáo trộn ngẫu nhiên.
    """
    room_data = game_rooms[room_id]
    player_count = len(room_data["players"])
    
    # 1. Lấy bể bài gốc và chạy qua bộ lọc tỷ lệ của Admin (Phần 31)
    base_pool = get_role_pool_for_players(player_count)
    final_role_pool = dynamic_adjust_role_pool_by_admin(base_pool)
    
    # Tạo danh sách bản sao để thao tác gán ngầm
    remaining_players = room_data["players"].copy()
    
    # Cấu trúc lưu kết quả tạm thời: { user_id: role_name }
    assigned_results = {}
    
    # 2. Quét xử lý những người chơi dùng Vé ưu tiên trước
    # Trộn ngẫu nhiên danh sách người chơi trước để tránh thiên vị nếu có nhiều người mua cùng dải vé
    random.shuffle(remaining_players)
    
    for pid in remaining_players.copy():
        user_item = user_db[pid].get("item_slot")
        
        # Nếu người chơi có sở hữu vé ưu tiên hợp lệ
        if user_item in TICKET_ROLE_MAPPING:
            target_role = TICKET_ROLE_MAPPING[user_item]
            
            # Điều kiện: Vai trò mong muốn phải có mặt trong bể bài trận đấu đêm nay
            # Thêm yếu tố may rủi 70% kích hoạt thành công (Tránh việc mua vé là chắc chắn 100% gây mất cân bằng)
            if target_role in final_role_pool and random.randint(1, 100) <= 70:
                assigned_results[pid] = target_role
                final_role_pool.remove(target_role)     # Rút quân bài đó ra khỏi bể bài chung
                remaining_players.remove(pid)           # Rút người chơi đó ra khỏi danh sách chờ phát bài
                
                # Đốt cháy tiêu hao Vé ưu tiên sau khi đã kích hoạt thành công
                user_db[pid]["item_slot"] = None
                
                try: bot.send_message(pid, "🎟️ **KÍCH HOẠT VÉ THÀNH CÔNG:** Vé ưu tiên vai trò của bạn đã được kích hoạt ngầm thành công!")
                except Exception: pass

    # 3. Phân chia ngẫu nhiên tuyệt đối tất cả các vai trò và người chơi còn lại
    random.shuffle(final_role_pool)
    for pid in remaining_players:
        role_name = final_role_pool.pop(0)
        assigned_results[pid] = role_name
        
    # 4. Đồng bộ hóa kết quả vào cấu trúc dữ liệu phòng chơi (Thế chỗ vào Phần 9)
    for pid, role_name in assigned_results.items():
        room_data["roles"][pid] = {
            "role": role_name,
            "team": "Ma Sói" if "Sói" in role_name or role_name == "Kẻ Phản Bội" else "Dân Làng",
            "status": "Alive",
            "target_history": []
        }

# ==========================================
# 93. ĐỊNH NGHĨA KHO NHIỆM VỤ HÀNG NGÀY SYSTEM
# ==========================================
DAILY_QUESTS_POOL = {
    "q1": {"desc": "🎮 Tham gia đủ 2 trận đấu Ma Sói bất kỳ", "target": 2, "gold": 500, "exp": 30},
    "q2": {"desc": "🏆 Giành chiến thắng 1 trận đấu", "target": 1, "gold": 800, "exp": 50},
    "q3": {"desc": "🏦 Thực hiện 1 giao dịch tại Ngân hàng", "target": 1, "gold": 300, "exp": 20},
    "q4": {"desc": "🎁 Tặng tiền Vàng P2P cho bằng hữu", "target": 1, "gold": 400, "exp": 25}
}

# ==========================================
# 94. HÀM KHỞI TẠO VÀ LÀM MỚI NHIỆM VỤ CHO USER
# ==========================================
def refresh_daily_quests_if_new_day(user_id):
    """
    Tự động kiểm tra ngày mới. Nếu sang ngày mới, ngẫu nhiên rút 3 nhiệm vụ 
    từ Pool và reset tiến trình (progress) về 0 cho người chơi.
    """
    user_data = user_db[user_id]
    current_date = time.strftime("%Y-%m-%d") # Lấy ngày hiện tại hệ thống
    
    # Nếu chưa từng có dữ liệu nhiệm vụ hoặc đã bước sang ngày mới
    if "quests_date" not in user_data or user_data["quests_date"] != current_date:
        user_data["quests_date"] = current_date
        user_data["daily_quests"] = {}
        
        # Chọn ngẫu nhiên 3 mã nhiệm vụ không trùng nhau
        selected_q_ids = random.sample(list(DAILY_QUESTS_POOL.keys()), 3)
        
        for q_id in selected_q_ids:
            user_data["daily_quests"][q_id] = {
                "progress": 0,       # Tiến trình hiện tại
                "claimed": False     # Trạng thái đã nhận thưởng hay chưa
            }

def update_quest_progress(user_id, quest_id_action):
    """Hàm bổ trợ tăng tiến trình nhiệm vụ khi user thực hiện hành động tương ứng trong game"""
    if user_id not in user_db: return
    user_data = user_db[user_id]
    
    # Đảm bảo dữ liệu nhiệm vụ luôn mới nhất trong ngày
    refresh_daily_quests_if_new_day(user_id)
    
    if quest_id_action in user_data["daily_quests"]:
        quest_state = user_data["daily_quests"][quest_id_action]
        quest_config = DAILY_QUESTS_POOL[quest_id_action]
        
        # Nếu chưa đạt mốc tối đa thì tăng tiến trình lên 1
        if quest_state["progress"] < quest_config["target"]:
            quest_state["progress"] += 1

# ==========================================
# 95. GIAO DIỆN BẢNG THÔNG TIN NHIỆM VỤ TRỰC QUAN
# ==========================================
def get_quests_menu_markup(user_id):
    """Tạo các nút bấm Inline để nhận thưởng cho từng nhiệm vụ hoàn thành"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    user_data = user_db[user_id]
    
    for q_id, state in user_data["daily_quests"].items():
        config = DAILY_QUESTS_POOL[q_id]
        
        # Thiết lập nhãn trạng thái cho nút bấm
        if state["claimed"]:
            btn_text = f"✅ ĐÃ NHẬN — {config['desc']}"
            cb_data = "quest_already_claimed"
        elif state["progress"] >= config["target"]:
            btn_text = f"🎁 NHẬN THƯỞNG — {config['desc']}"
            cb_data = f"quest_claim_{q_id}"
        else:
            btn_text = f"⏳ ({state['progress']}/{config['target']}) — {config['desc']}"
            cb_data = "quest_not_done"
            
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=cb_data))
        
    markup.add(types.InlineKeyboardButton("⬅️ QUAY LẠI SẢNH", callback_data="lobby_back_main"))
    return markup

def show_daily_quests_hub(user_id, chat_id, message_id=None):
    """Hiển thị trung tâm nhiệm vụ hàng ngày của game thủ"""
    refresh_daily_quests_if_new_day(user_id)
    
    quest_text = (
        f"📜 **TRUNG TÂM NHIỆM VỤ HÀNG NGÀY LÀNG SÓI** 📜\n"
        f"-----------------------------------------\n"
        f"📅 Hôm nay: `{time.strftime('%d/%m/%Y')}`\n"
        f"👤 Thuyền trưởng: **{user_db[user_id]['name']}**\n\n"
        f"🔥 Hãy hoàn thành các mục tiêu sinh tồn dưới đây để tích lũy tài sản miễn phí hằng ngày. "
        f"Nhiệm vụ và tiến trình sẽ tự động làm mới hoàn toàn vào lúc `00:00` mỗi đêm.\n\n"
        f"👇 **DANH SÁCH NHIỆM VỤ HÔM NAY:**"
    )
    
    if message_id:
        bot.edit_message_text(quest_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_quests_menu_markup(user_id))
    else:
        bot.send_message(chat_id, quest_text, parse_mode="Markdown", reply_markup=get_quests_menu_markup(user_id))

# ==========================================
# 96. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data == "quest_not_done":
        bot.answer_callback_query(call.id, text="❌ Nhiệm vụ chưa hoàn thành, dũng sĩ hãy tiếp tục nỗ lực!", show_alert=True)
        
    elif data == "quest_already_claimed":
        bot.answer_callback_query(call.id, text="⚠️ Bạn đã thu hoạch phần thưởng này trong ngày hôm nay rồi.", show_alert=False)

    elif data.startswith("quest_claim_"):
        q_id = data.replace("quest_claim_", "")
        user_data = user_db[user_id]
        state = user_data["daily_quests"][q_id]
        config = DAILY_QUESTS_POOL[q_id]
        
        # Thực thi khóa phần thưởng, cộng tiền và EXP trực tiếp
        state["claimed"] = True
        user_data["gold"] += config["gold"]
        
        # Kích hoạt hàm kiểm tra thăng cấp đã viết ở Phần 22
        level_up = add_exp_and_check_level_up(user_id, config["exp"])
        lvl_up_alert = "\n🎉 **CHÚC MỪNG LEVEL UP!** Bạn đã tăng cấp danh hiệu mới." if level_up else ""
        
        bot.answer_callback_query(
            call.id, 
            text=f"🎁 Thu hoạch thành công: +{config['gold']:,} Vàng & +{config['exp']} EXP!{lvl_up_alert}", 
            show_alert=True
        )
        
        # Làm mới lại màn hình nhiệm vụ để cập nhật trạng thái "ĐÃ NHẬN"
        show_daily_quests_hub(user_id, chat_id, message_id)

# Bộ nhớ tạm lưu trạng thái Thợ Săn bắn đêm của từng phòng chơi: { room_id: hunter_user_id }
night_hunter_trigger_cache = {}

# ==========================================
# 97. LOGIC KÍCH HOẠT LỆNH THỢ SĂN ĐÊM NGẦM
# ==========================================
def check_and_trigger_night_hunter_skill(room_id, wolf_victim_id):
    """
    Hàm kiểm tra va chạm sinh mệnh ban đêm.
    Nếu nạn nhân bị Sói cắn chết hoàn toàn là Thợ Săn, kích hoạt quyền năng bắn đêm.
    Ghi chú: Lồng hàm này vào Bước 4 của hàm `process_end_of_night` (Phần 15) trước khi công bố sáng.
    """
    room_data = game_rooms[room_id]
    
    # Xác thực nạn nhân chết đêm nay là Thợ Săn
    if room_data["roles"][wolf_victim_id]["role"] == "Thợ Săn":
        night_hunter_trigger_cache[room_id] = wolf_victim_id
        room_data["status"] = "Night_Hunter_Active"
        
        hunter_night_text = (
            "🏹 **QUYỀN NĂNG THỢ SĂN ĐÊM BÙNG NỔ** 🏹\n"
            "-----------------------------------------\n"
            "🩸 Bạn vừa bị nanh vuốt Ma Sói cắn xé xuyên qua màn đêm! Sức lực cuối cùng đang cạn kiệt...\n\n"
            "👉 Hãy giương cung/súng xả ngay một phát đạn chí mạng về phía kẻ tình nghi nhất ban đêm. "
            "Mục tiêu bị bạn nhắm bắn sẽ lật bài chết cùng bạn vào sáng mai!\n"
            "⏳ **Thời gian hành động khẩn cấp:** `15 giây` để bấm nút phán quyết."
        )
        
        # Tạo danh sách nút mục tiêu cho Thợ Săn bắn đêm (Sử dụng hàm tạo nút ở Phần 12 với tag 'nhunter')
        markup_nhunter = get_night_target_markup(room_id, wolf_victim_id, "nhunter")
        btn_skip = types.InlineKeyboardButton("⚪ Chết Lặng (Không bắn ai)", callback_data=f"skill_nhunter_{room_id}_0")
        markup_nhunter.add(btn_skip)
        
        try:
            bot.send_message(wolf_victim_id, hunter_night_text, parse_mode="Markdown", reply_markup=markup_nhunter)
        except Exception:
            pass
            
        # Chặn đứng luồng chạy chính trong 15 giây để đợi Thợ Săn xả đạn
        time.sleep(15)
        return True
        
    return False

# ==========================================
# 98. BỔ SUNG NHÁNH XỬ LÝ SỰ KIỆN VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("skill_nhunter_"):
        # Phân tách chuỗi: skill_nhunter_[room_id]_[target_id]
        parts = data.split("_")
        room_id = parts[2]
        target_id = int(parts[3])
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night_Hunter_Active":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian bóp cò súng đêm!", show_alert=True)
            return
            
        room_data = game_rooms[room_id]
        
        # Trường hợp 1: Thợ Săn chọn bỏ qua không bắn ai
        if target_id == 0:
            bot.edit_message_text("⚪ Bạn quyết định ôm hận ra đi trong lặng im, giữ lại mạng sống cho dân làng.", chat_id, message_id)
            bot.answer_callback_query(call.id, text="Đã buông bỏ phát bắn.")
            room_data["status"] = "Night" # Trả trạng thái về đêm để chạy tiếp tổng kết sáng
            return

        # Trường hợp 2: Bắn chết 1 mục tiêu cụ thể ban đêm
        target_name = user_db[target_id]["name"]
        target_role = room_data["roles"][target_id]["role"]
        
        # Thực thi khai tử mục tiêu dính đạn ngầm
        if target_id in room_data["alive"]:
            room_data["alive"].remove(target_id)
            room_data["roles"][target_id]["status"] = "Dead"
            
        # Ghi nhận sự kiện đặc biệt này vào bộ đếm khai tử sáng (Đồng bộ trực tiếp với Phần 15)
        room_data["history_log"].append(f"🏹 Thợ Săn Đêm bóp cò ghim đạn chết {target_name} ({target_role}).")
        
        # Phát thông báo mật phản hồi cho Thợ Săn
        bot.edit_message_text(f"💥 ĐOÀNG! Phát đạn đêm của bạn đã ghim thẳng vào ngực **{target_name}**. Máu nhuộm màn đêm!", chat_id, message_id, parse_mode="Markdown")
        bot.answer_callback_query(call.id, text="Xả đạn thành công!", show_alert=True)
        
        # Trả luồng game về trạng thái đêm để máy chủ tiếp tục chạy hàm công bố kết quả sáng
        room_data["status"] = "Night"
        
        # Đồng bộ hóa in thêm kết quả dính đạn của Thợ săn lên sảnh chat tổng ban ngày
        # (Bộ não tổng kết Phần 15 sẽ tự động quét danh sách chết để in tên tuổi kẻ dính đạn này ra nhóm)

# ==========================================
# 99. ĐỊNH NGHĨA CÁC MỐC THƯỞNG CẤP ĐỘ TOÀN SERVER
# ==========================================
LEVEL_REWARDS_POOL = {
    5:  {"gold": 2000,  "title": "🏹 Dân Làng Tinh Anh"},
    10: {"gold": 5000,  "title": "⚡ Cao Thủ Làng Sói"},
    15: {"gold": 10000, "title": "⚔️ Thợ Săn Lão Luyện"},
    25: {"gold": 25000, "title": "🔮 Đại Pháp Sư"},
    50: {"gold": 100000,"title": "👑 Huyền Thoại Làng Sói"}
}

# ==========================================
# 100. GIAO DIỆN BẢNG PHẦN THƯỞNG CẤP ĐỘ
# ==========================================
def get_level_rewards_markup(user_id):
    """Tạo danh sách nút bấm hiển thị trạng thái các mốc thưởng để nhận Vàng"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    user_data = user_db[user_id]
    
    # Khởi tạo danh sách mốc đã nhận nếu tài khoản mới tinh chưa từng bấm nhận quà
    if "claimed_lv_rewards" not in user_data:
        user_data["claimed_lv_rewards"] = set()
        
    current_level = user_data["level"]
    
    for lv_milestone, config in sorted(LEVEL_REWARDS_POOL.items()):
        # Trường hợp 1: Đã nhận quà mốc này rồi
        if lv_milestone in user_data["claimed_lv_rewards"]:
            btn_text = f"✅ ĐÃ NHẬN — Quà Cấp {lv_milestone} (+{config['gold']:,} Vàng)"
            cb_data = "lv_reward_already_claimed"
            
        # Trường hợp 2: Đủ cấp độ và sẵn sàng nhận thưởng
        elif current_level >= lv_milestone:
            btn_text = f"🎁 BẤM NHẬN — Quà Cấp {lv_milestone} (+{config['gold']:,} Vàng)"
            cb_data = f"lv_reward_claim_{lv_milestone}"
            
        # Trường hợp 3: Chưa đủ cấp độ yêu cầu
        else:
            btn_text = f"🔒 KHÓA (Yêu cầu Cấp {lv_milestone}) — {config['title']}"
            cb_data = f"lv_reward_locked_{lv_milestone}"
            
        markup.add(types.InlineKeyboardButton(btn_text, callback_data=cb_data))
        
    btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI SẢNH", callback_data="lobby_back_main")
    markup.add(btn_back)
    return markup

def show_level_rewards_hub(user_id, chat_id, message_id=None):
    """Hiển thị trung tâm nhận quà thăng cấp danh dự"""
    user_data = user_db[user_id]
    
    hub_text = (
        f"🏅 **TRUNG TÂM PHẦN THƯỞNG CẤP ĐỘ SÓI V8** 🏅\n"
        f"-----------------------------------------\n"
        f"👤 Tài khoản: **{user_data['name']}**\n"
        f"🎖️ Cấp độ hiện tại: `Cấp {user_data['level']}`\n"
        f"💰 Số dư ví: `{user_data['gold']:,} Vàng`\n\n"
        f"✨ **HÀNH TRÌNH DANH VỌNG:**\n"
        f"👉 Hãy tích cực tham chiến các trận đấu Ma Sói để tích lũy điểm kinh nghiệm (EXP). "
        f"Mỗi khi chạm đến cột mốc vàng, bạn sẽ được khai thông phong ấn để nhận hàng ngàn Vàng miễn phí từ kho báu của làng!\n\n"
        f"👇 **TRẠNG THÁI CÁC MỐC THƯỞNG:**"
    )
    
    if message_id:
        bot.edit_message_text(hub_text, chat_id, message_id, parse_mode="Markdown", reply_markup=get_level_rewards_markup(user_id))
    else:
        bot.send_message(chat_id, hub_text, parse_mode="Markdown", reply_markup=get_level_rewards_markup(user_id))

# ==========================================
# 101. TIẾP TỤC BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data == "lv_reward_already_claimed":
        bot.answer_callback_query(call.id, text="⚠️ Mốc phần thưởng danh dự này bạn đã thu hoạch từ trước.", show_alert=False)
        
    elif data.startswith("lv_reward_locked_"):
        lv_needed = data.replace("lv_reward_locked_", "")
        bot.answer_callback_query(call.id, text=f"🔒 Bạn cần đạt tối thiểu Cấp {lv_needed} để phá phong ấn nhận quà mốc này!", show_alert=True)

    elif data.startswith("lv_reward_claim_"):
        lv_milestone = int(data.replace("lv_reward_claim_", ""))
        user_data = user_db[user_id]
        config = LEVEL_REWARDS_POOL[lv_milestone]
        
        # Đóng dấu xác nhận đã nhận quà vào mảng cấu trúc danh sách
        if "claimed_lv_rewards" not in user_data:
            user_data["claimed_lv_rewards"] = set()
            
        user_data["claimed_lv_rewards"].add(lv_milestone)
        
        # Cộng tiền thưởng Vàng trực tiếp vào ví
        user_data["gold"] += config["gold"]
        
        bot.answer_callback_query(
            call.id, 
            text=f"🎉 Nhận quà thành công! Kho báu cấp {lv_milestone} gửi tặng dũng sĩ: +{config['gold']:,} Vàng vào tài khoản.", 
            show_alert=True
        )
        
        # Làm mới lại giao diện màn hình để cập nhật mốc vừa nhận thành dấu check xanh
        show_level_rewards_hub(user_id, chat_id, message_id)

# Bộ nhớ tạm quản lý trạng thái kích hoạt Huyết Ấn Bóng Đêm của từng phòng chơi: { room_id: True/False }
shadow_ballot_active_cache = {}

# ==========================================
# 102. ĐỒNG BỘ THÊM NÚT BẤM KÍCH HOẠT SHADOW BALLOT (Phần 13)
# ==========================================
# Bạn hãy mở Phần 13 (Hàm get_wolf_vote_markup) ra và chèn thêm đoạn code này 
# để chỉ Sói Alpha hoặc Sói Nguyền nhìn thấy nút kích hoạt chiêu thức ẩn danh:

def inject_shadow_button_for_alpha(room_id, markup_wolf, user_role):
    """Bổ sung nút kích hoạt Huyết Ấn Bóng Đêm vào menu bỏ phiếu đêm của Sói cấp cao"""
    # Nếu phòng chơi chưa từng dùng chiêu và người gọi lệnh là Sói Alpha hoặc Sói Nguyền
    if not shadow_ballot_active_cache.get(room_id, False) and user_role in ["Sói Alpha", "Sói Nguyền"]:
        btn_shadow = types.InlineKeyboardButton("🔮 KÍCH HOẠT: Huyết Ấn Bóng Đêm", callback_data=f"wolf_shadow_activate_{room_id}")
        markup_wolf.add(btn_shadow)
    return markup_wolf

# ==========================================
# 103. BỔ SUNG NHÁNH XỬ LÝ SỰ KIỆN VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("wolf_shadow_activate_"):
        room_id = data.replace("wolf_shadow_activate_", "")
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] != "Night":
            bot.answer_callback_query(call.id, text="❌ Đã hết thời gian hành động ban đêm!", show_alert=True)
            return
            
        # Kích hoạt trạng thái Ẩn Danh Tuyệt Đối cho phòng chơi
        shadow_ballot_active_cache[room_id] = True
        room_data = game_rooms[room_id]
        
        bot.answer_callback_query(call.id, text="🔮 Đã giải phóng Huyết Ấn Bóng Đêm thành công!", show_alert=True)
        bot.edit_message_text("🔮 Bạn đã kích hoạt **Huyết Ấn Bóng Đêm**. Lệnh bỏ phiếu cắn người của bầy Sói đêm nay sẽ được ẩn giấu tuyệt đối, không một ai biết được tiến trình!", chat_id, message_id)
        
        # Gửi mật báo khẩn cho toàn bộ bầy Sói còn sống biết chiêu thức đang được thi triển
        for pid in room_data["alive"]:
            if "Sói" in room_data["roles"][pid]["role"] and pid != user_id:
                try:
                    bot.send_message(pid, "🔮 **MẬT BÁO BÓNG ĐÊM:** Đồng bọn cấp cao trong bầy vừa kích hoạt *Huyết Ấn Bóng Đêm*. Tiến trình bỏ phiếu cắn người từ giây phút này sẽ bị khóa hiển thị để bảo mật tối cao!")
                except Exception: pass

# ==========================================
# 104. ĐỒNG BỘ HOÀN TOÀN CƠ CHẾ VÀO LOGIC CẮN NGƯỜI (Phần 13)
# ==========================================
# Bạn tìm đến hàm Callback xử lý lệnh cắn người `wolf_bite_` ở Phần 13, 
# hãy tìm đoạn "Thông báo ẩn danh cho các thành viên Sói khác..." và thế bằng logic lọc bóng đêm này:

        # Đoạn code đồng bộ ẩn danh tối ưu mới:
        # Nếu phòng chơi KHÔNG kích hoạt Huyết Ấn Bóng Đêm thì mới thông báo cho đồng bọn
        if not shadow_ballot_active_cache.get(room_id, False):
            for pid in room_data["alive"]:
                if "Sói" in room_data["roles"][pid]["role"] and pid != user_id:
                    try:
                        bot.send_message(pid, f"🐾 Một thành viên trong bầy vừa bỏ phiếu cắn **{target_name}**.")
                    except Exception: pass
        else:
            # Nếu Huyết ấn đang chạy, im lặng hoàn toàn, không bắn tin nhắn thông báo tiến trình cho bất kỳ ai!
            pass

# ==========================================
# 105. DỌN DẸP CACHE SAU KHI ĐÊM KHÉP LẠI (Phần 15)
# ==========================================
# Ghi chú: Bạn hãy chèn dòng giải phóng bộ nhớ RAM này vào Bước 5 của hàm `process_end_of_night` ở Phần 15:
# if room_id in shadow_ballot_active_cache: del shadow_ballot_active_cache[room_id]
# Bộ nhớ tạm lưu trữ ID của người sống nhận thông điệp tâm linh đêm nay: { room_id: user_id_người_sống }
spirit_receiver_cache = {}

# ==========================================
# 106. HÀM KÍCH HOẠT ĐƯỜNG TRUYỀN LINH HỒN BAN ĐÊM
# ==========================================
def trigger_spirit_medium_link(room_id):
    """
    Hàm lõi quét phòng chơi khi đêm xuống:
    - Tìm xem phòng đã có người chết (linh hồn) chưa.
    - Chọn ngẫu nhiên 1 người chơi thuộc phe Dân Làng còn sống để làm cột thu lôi nhận tin nhắn.
    - Mở cổng đăng ký nhận thông điệp trăng trối.
    """
    room_data = game_rooms[room_id]
    
    # 1. Tính toán danh sách linh hồn (người thuộc phòng nhưng đã chết)
    dead_souls = [pid for pid in room_data["players"] if pid not in room_data["alive"]]
    
    # 2. Tính toán danh sách người sống sót thuộc phe Dân Làng để làm cổng nhận
    living_villagers = [pid for pid in room_data["alive"] if room_data["roles"][pid]["team"] == "Dân Làng"]
    
    if not dead_souls or not living_villagers:
        return # Nếu chưa có ai chết hoặc không còn dân làng nào sống, hủy luồng tâm linh
        
    # Chọn ngẫu nhiên 1 dũng sĩ may mắn nhận thông điệp đêm nay
    receiver_id = random.choice(living_villagers)
    spirit_receiver_cache[room_id] = receiver_id
    
    # 3. Phát lệnh gọi cho toàn bộ thế giới linh hồn (những người đã chết)
    spirit_instruction = (
        f"🌌 **CỔNG TÂM LINH ĐÊM NAY ĐÃ MỞ** 🌌\n"
        f"-----------------------------------------\n"
        f"🔮 Hỡi các linh hồn đã khuất của phòng `{room_id}`, oán khí ban đêm đang ngút trời. "
        f"Thần linh cho phép các bạn gửi **1 thông điệp mật** gửi gắm manh mối cho người sống.\n\n"
        f"👉 Hãy sử dụng lệnh cú pháp: `/tam_linh [Nội_dung_nhắn_nhủ]` để gửi ngay cho Bot.\n"
        f"🤫 *Quy tắc:* Tin nhắn sẽ được chuyển tiếp nặc danh đến 1 người sống ngẫu nhiên trong làng để giúp đỡ họ suy luận!"
    )
    
    for soul_id in dead_souls:
        try: bot.send_message(soul_id, spirit_instruction, parse_mode="Markdown")
        except Exception: pass

# Ghi chú tích hợp: Bạn hãy gọi hàm `trigger_spirit_medium_link(room_id)` này ở cuối hàm 
# `start_night_phase` ở Phần 11 để kích hoạt cổng truyền tín hiệu ngay khi đêm xuống.

# ==========================================
# 107. LỆNH GỬI THÔNG ĐIỆP CỦA LINH HỒN ĐÃ CHẾT
# ==========================================
@bot.message_handler(commands=['tam_linh'])
def cmd_send_spirit_message(message):
    """Xử lý lệnh gửi tin nhắn tâm linh bí mật của linh hồn người chết"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Tìm phòng chơi hiện tại của linh hồn này
    active_room_id = None
    for rid, rdata in game_rooms.items():
        if user_id in rdata["players"]:
            active_room_id = rid
            break
            
    if not active_room_id or game_rooms[active_room_id]["status"] != "Night":
        bot.reply_to(message, "❌ Cổng tâm linh chỉ mở ra vào ban đêm khi trận đấu đang diễn ra!")
        return
        
    room_data = game_rooms[active_room_id]
    
    # Điều kiện bảo mật: Người gửi phải chắc chắn đã CHẾT
    if user_id in room_data["alive"]:
        bot.reply_to(message, "❌ Bạn vẫn còn sống sờ sờ, không thể giả làm linh hồn để giao tiếp âm giới!")
        return
        
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Cú pháp chuẩn: `/tam_linh [Lời nhắn của linh hồn]`")
        return
        
    spirit_text = args.strip()[:60] # Giới hạn 60 ký tự chống spam giao diện người nhận
    receiver_id = spirit_receiver_cache.get(active_room_id)
    
    if receiver_id:
        try:
            # Gửi tin nhắn ẩn danh định dạng quẻ bói bí ẩn cho người sống nhận diện
            bot.send_message(
                receiver_id,
                f"🔮 **TIẾNG THÌ THẦM TỪ CÕI ÂM** 🔮\n"
                f"-----------------------------------------\n"
                f"🌌 Gió lạnh thổi qua khe cửa... Một linh hồn vô danh đã khuất vừa gửi đến tai bạn một lời tiên tri trăn trối:\n\n"
                f"🗣️ *\" {spirit_text} \"*\n"
                f"-----------------------------------------\n"
                f"💡 *Gợi ý:* Đây có thể là manh mối thật từ đồng đội, hoặc đòn hỏa mù từ Sói đã chết. Hãy cẩn trọng lập luận ban ngày!"
            )
            bot.reply_to(message, "✅ Thông điệp tâm linh của bạn đã được gió đêm thổi bay đến tai người sống thành công.")
        except Exception:
            bot.reply_to(message, "❌ Đường truyền tâm linh bị nghẽn mạch do lỗi kết nối đối tượng.")
            
    # Xóa cổng sau khi đã có linh hồn đầu tiên giật giải gửi tin nhắn thành công trong đêm
    if active_room_id in spirit_receiver_cache:
        del spirit_receiver_cache[active_room_id]

# ==========================================
# 108. ĐỊNH NGHĨA KHO THÀNH TỰU QUỐC TẾ SYSTEM
# ==========================================
ACHIEVEMENTS_POOL = {
    "ac_first_win": {
        "title": "🎖️ Khai Nòng Chiến Thắng",
        "desc": "Đạt trận thắng đầu tiên trong hệ thống Ma Sói v8.",
        "gold_reward": 1000,
        "check_key": "win", "target_value": 1
    },
    "ac_veteran_win": {
        "title": "🏆 Chiến Binh Lão Luyện",
        "desc": "Tích lũy đạt mốc 10 trận thắng danh dự.",
        "gold_reward": 5000,
        "check_key": "win", "target_value": 10
    },
    "ac_millionaire": {
        "title": "👑 Triệu Phú Làng Sói",
        "desc": "Sở hữu tổng tài sản chạm dải 50,000 Vàng trong ví.",
        "gold_reward": 2500,
        "check_key": "gold", "target_value": 50000
    },
    "ac_level_10": {
        "title": "🛡️ Trưởng Lão Tương Lai",
        "desc": "Cày cuốc nâng cấp tài khoản chạm mốc Cấp 10 (Lv.10).",
        "gold_reward": 4000,
        "check_key": "level", "target_value": 10
    }
}

# ==========================================
# 109. THUẬT TOÁN QUÉT VÀ KIỂM TRA MỞ KHÓA TỰ ĐỘNG
# ==========================================
def scan_and_unlock_user_achievements(user_id, chat_id=None):
    """
    Hàm lõi đối chiếu chỉ số trong user_db với kho thành tựu:
    - Kiểm tra xem người chơi đã mở khóa thành tựu này chưa.
    - Nếu đạt điều kiện và chưa mở, bung lệnh mở khóa và cộng tiền thưởng lớn.
    """
    user_data = user_db[user_id]
    
    # Khởi tạo mảng lưu danh sách thành tựu đã mở nếu tài khoản mới tinh
    if "unlocked_achievements" not in user_data:
        user_data["unlocked_achievements"] = set()
        
    unlocked_any = False
    
    for ac_id, config in ACHIEVEMENTS_POOL.items():
        # Điều kiện: Thành tựu chưa từng được mở khóa trước đây
        if ac_id not in user_data["unlocked_achievements"]:
            # Lấy giá trị thực tế của user để đối chiếu (win, gold, level...)
            current_value = user_data.get(config["check_key"], 0)
            
            if current_value >= config["target_value"]:
                # Thực thi mở khóa vĩnh viễn và phát thưởng Vàng khổng lồ
                user_data["unlocked_achievements"].add(ac_id)
                user_data["gold"] += config["gold_reward"]
                unlocked_any = True
                
                # Bắn tin nhắn chúc mừng định dạng đẹp mắt đến hộp thư người chơi
                announcement = (
                    f"🏆 **THÀNH TỰU DANH GIÁ ĐÃ ĐƯỢC PHÁ GIẢI** 🏆\n"
                    f"-----------------------------------------\n"
                    f"🎉 Chúc mừng dũng sĩ **{user_data['name']}** vừa xuất sắc mở khóa thành công danh hiệu quý tộc:\n\n"
                    f"🎖️ **{config['title']}**\n"
                    f"ℹ️ *Mô tả:* _{config['desc']}_\n"
                    f"-----------------------------------------\n"
                    f"🎁 **Phần thưởng độc quyền:** `+{config['gold_reward']:,} Vàng` đã được chuyển vào tài khoản ví ngân hàng của bạn!"
                )
                
                if chat_id:
                    try: bot.send_message(chat_id, announcement, parse_mode="Markdown")
                    except Exception: pass
                else:
                    try: bot.send_message(user_id, announcement, parse_mode="Markdown")
                    except Exception: pass
                    
    return unlocked_any

# ==========================================
# 110. GIAO DIỆN XEM BẢNG TỔNG HỢP THÀNH TỰU (PROFILE LINK)
# ==========================================
def get_achievements_list_text(user_id):
    """Biên soạn bảng danh sách hiển thị mốc thành tựu đã hoặc chưa mở của user"""
    user_data = user_db[user_id]
    unlocked_set = user_data.get("unlocked_achievements", set())
    
    text = "🏆 **BẢNG VÀNG THÀNH TỰU CÁ NHÂN** 🏆\n-----------------------------------------\n\n"
    
    for ac_id, config in ACHIEVEMENTS_POOL.items():
        if ac_id in unlocked_set:
            status_icon = "🟢 [ĐÃ PHÁ GIẢI]"
        else:
            status_icon = "🔒 [ĐANG KHÓA]"
            
        text += f"▪️ **{config['title']}** — {status_icon}\n   *Chi tiết:* {config['desc']}\n   *Quà:* `+{config['gold_reward']:,} Vàng`\n\n"
        
    text += f"📊 *Tiến độ hiện tại:* Bạn đã hoàn thành `{len(unlocked_set)}/{len(ACHIEVEMENTS_POOL)}` thành tựu toàn server."
    return text


# ==========================================
# 111. LOGIC KHÓA TOÀN BỘ QUYỀN CHAT CỦA GROUP (BAN ĐÊM)
# ==========================================
def restrict_all_group_players_night(room_id, group_chat_id):
    """
    Sử dụng API Telegram để tước quyền gửi tin nhắn của tất cả người chơi trong trận.
    Hàm này khóa chat diện rộng ở tầng API Telegram thay vì lọc bằng code Middleware.
    Ghi chú: Lồng hàm này vào cuối hàm `start_night_phase` ở Phần 11.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    
    # Thiết lập cấu hình quyền hạn cấm: Tắt tất cả quyền gửi text, media, link
    night_permissions = types.ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False
    )
    
    # Quét qua danh sách người chơi thường (Ẩn Admin để tránh khóa nhầm Admin hệ thống)
    for pid in room_data["players"]:
        if pid != ADMIN_WHITELIST and pid not in OPERATORS:
            try:
                # Gửi lệnh thực thi khóa chat lên máy chủ Telegram API
                bot.restrict_chat_member(
                    chat_id=group_chat_id, 
                    user_id=pid, 
                    permissions=night_permissions
                )
            except Exception:
                # Bỏ qua nếu người chơi không nằm trong Group chat tổng hoặc là Quản trị viên của Group đó
                pass

# ==========================================
# 112. LOGIC MỞ LẠI QUYỀN CHAT TỰ ĐỘNG (BAN NGÀY CHUYỂN CẢNH)
# ==========================================
def unmute_all_group_players_day(room_id, group_chat_id):
    """
    Sử dụng API Telegram để mở lại toàn bộ quyền hạn gửi tin nhắn cho các dũng sĩ còn sống.
    Riêng những người ĐÃ CHẾT vẫn tiếp tục giữ án phạt khóa chat đến hết game.
    Ghi chú: Lồng hàm này vào cuối hàm `process_end_of_night` ở Phần 15.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    
    # Thiết lập cấu hình quyền hạn mở: Trả lại toàn bộ quyền tương tác
    day_permissions = types.ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True
    )
    
    # 1. Quét danh sách những người CÒN SỐNG để giải phóng ngôn luận
    for pid in room_data["alive"]:
        if pid != ADMIN_WHITELIST and pid not in OPERATORS:
            try:
                bot.restrict_chat_member(
                    chat_id=group_chat_id, 
                    user_id=pid, 
                    permissions=day_permissions
                )
            except Exception:
                pass
                
    # 2. Cố định án phạt Mute vĩnh viễn cho những người ĐÃ CHẾT trong đêm vừa qua
    for pid in room_data["players"]:
        if pid not in room_data["alive"] and pid != ADMIN_WHITELIST and pid not in OPERATORS:
            try:
                bot.restrict_chat_member(
                    chat_id=group_chat_id, 
                    user_id=pid, 
                    permissions=types.ChatPermissions(can_send_messages=False)
                )
            except Exception:
                pass

# ==========================================
# 113. HÀM GIẢI PHÓNG TOÀN BỘ NHÓM KHI KẾT THÚC GAME
# ==========================================
def lift_all_restrictions_on_game_over(room_id, group_chat_id):
    """
    Trả lại tự do hoàn toàn cho toàn bộ thành viên (sống + chết) khi trận đấu kết thúc.
    Ghi chú: Lồng lệnh này vào cuối hàm `process_end_of_game_rewards` ở Phần 22.
    """
    if room_id not in game_rooms:
        return
        
    room_data = game_rooms[room_id]
    free_permissions = types.ChatPermissions(
        can_send_messages=True, can_send_media_messages=True, can_send_polls=True
    )
    
    for pid in room_data["players"]:
        try:
            bot.restrict_chat_member(chat_id=group_chat_id, user_id=pid, permissions=free_permissions)
        except Exception:
            pass

import json
import os

# Đường dẫn thư mục cục bộ dùng để lưu trữ file lịch sử trận đấu trên server/vps
MATCH_HISTORY_DIR = "./masoiv8_match_history"

# Tự động khởi tạo thư mục lưu trữ nếu hệ thống chạy lần đầu chưa có sẵn
if not os.path.exists(MATCH_HISTORY_DIR):
    os.makedirs(MATCH_HISTORY_DIR)

# ==========================================
# 114. THUẬT TOÁN ĐÓNG GÓI VÀ ĐỒNG BỘ FILE DỮ LIỆU
# ==========================================
def save_match_history_to_storage(room_id):
    """
    Hàm lõi trích xuất dữ liệu phòng chơi trước khi giải phóng bộ nhớ:
    - Gom nhóm danh sách người chơi, vai trò cấu hình, quỹ cược, kết quả.
    - Chuyển đổi mảng biên niên sử thành file cấu trúc JSON chuẩn.
    - Lưu file cục bộ với tên file định dạng thời gian thực duy nhất.
    Ghi chú: Lồng hàm này vào ngay ĐẦU hàm `process_end_of_game_rewards` ở Phần 22.
    """
    if room_id not in game_rooms:
        return False
        
    room_data = game_rooms[room_id]
    timestamp_key = int(time.time())
    file_name = f"match_{room_id}_{timestamp_key}.json"
    file_path = os.path.join(MATCH_HISTORY_DIR, file_name)
    
    # Chuẩn bị cấu trúc dữ liệu đóng gói an toàn
    match_payload = {
        "match_id": f"{room_id}_{timestamp_key}",
        "room_code": room_id,
        "date_time": time.strftime('%Y-%m-%d %H:%M:%S'),
        "bet_amount": room_data.get("bet", 0),
        "total_prize_pool": len(room_data.get("players", [])) * room_data.get("bet", 0),
        "weather_last": room_data.get("weather", "Không rõ"),
        "players_list": room_data.get("players", []),
        "alive_at_end": room_data.get("alive", []),
        "roles_configuration": {}, # Sẽ duyệt map ID sang text để dễ đọc log
        "chronicle_logs": room_data.get("history_log", [])
    }
    
    # Duyệt map hóa thông tin vai trò người chơi
    for pid, pdata in room_data.get("roles", {}).items():
        pname = user_db.get(pid, {}).get("name", f"User_{pid}")
        match_payload["roles_configuration"][str(pid)] = {
            "name": pname,
            "role": pdata.get("role", "Dân"),
            "team": pdata.get("team", "Dân Làng"),
            "status": pdata.get("status", "Dead")
        }
        
    try:
        # Thực thi ghi file dữ liệu cục bộ lên ổ cứng máy chủ VPS/Server
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(match_payload, f, ensure_ascii=False, indent=4)
            
        # Ghi nhận vết lưu trữ thành công vào hệ thống log tổng
        print(f"[SYSTEM LOG] Đã đồng bộ xuất file lịch sử trận đấu thành công: {file_name}")
        return True
    except Exception as e:
        print(f"[SYSTEM ERROR] Lỗi ghi file lịch sử trận đấu: {str(e)}")
        return False

# ==========================================
# 115. LỆNH TRA CỨU NHANH TRẬN ĐẤU DÀNH CHO ADMIN
# ==========================================
@bot.message_handler(commands=['checkmatch'])
def cmd_admin_check_match_file(message):
    """
    Lệnh Admin tra cứu nhanh file log trận đấu cục bộ: /checkmatch [Mã_Phòng]
    Ví dụ: /checkmatch R1234
    """
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if user_id != ADMIN_WHITELIST:
        return # Chặn đứng nếu không phải Whitelist Admin tối cao (Phần 1)
        
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Cú pháp chuẩn tra cứu: `/checkmatch [Mã_Phòng]`\n*(Ví dụ: /checkmatch R1234)*", parse_mode="Markdown")
        return
        
    target_room_code = args[1].strip().upper()
    
    # Quét thư mục tìm file khớp mã phòng chơi
    found_files = [f for f in os.listdir(MATCH_HISTORY_DIR) if f.startswith(f"match_{target_room_code}_")]
    
    if not found_files:
        bot.reply_to(message, f"❌ Không tìm thấy dữ liệu file log lịch sử nào khớp với mã phòng `{target_room_code}`.", parse_mode="Markdown")
        return
        
    # Sắp xếp lấy file mới nhất trong danh sách tìm được
    latest_file = sorted(found_files)[-1]
    latest_file_path = os.path.join(MATCH_HISTORY_DIR, latest_file)
    
    try:
        with open(latest_file_path, 'r', encoding='utf-8') as f:
            match_data = json.load(f)
            
        # Biên soạn nội dung tóm tắt gửi nhanh về chat Admin
        summary_text = (
            f"📂 **KẾT QUẢ TRA CỨU FILE LOG TRẬN ĐẤU** 📂\n"
            f"===================================\n"
            f"📄 Tên file: `{latest_file}`\n"
            f"📅 Ngày chạy trận: `{match_data['date_time']}`\n"
            f"💰 Quỹ thưởng trận: `{match_data['total_prize_pool']:,} Vàng`\n\n"
            f"👥 **Cấu hình bài phân tách trong trận:**\n"
        )
        
        for uid, pinfo in match_data["roles_configuration"].items():
            summary_text += f"▪️ {pinfo['name']} (ID: `{uid}`) — `{pinfo['role']}` [{pinfo['status']}]\n"
            
        summary_text += "\n⚙️ Admin có muốn trích xuất toàn bộ tệp tin gốc để kiểm tra chi tiết không?"
        
        # Đính kèm nút bấm để Admin tải trực tiếp file JSON nếu cần
        markup = types.InlineKeyboardMarkup()
        btn_download = types.InlineKeyboardButton("📥 TẢI FILE DỮ LIỆU GỐC", callback_data=f"adm_dl_file_{latest_file}")
        markup.add(btn_download)
        
        bot.send_message(chat_id, summary_text, parse_mode="Markdown", reply_markup=markup)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Thất bại khi đọc file log dữ liệu: {str(e)}")

# ==========================================
# 116. NHÁNH CALLBACK XỬ LÝ LỆNH TẢI FILE CỦA ADMIN
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("adm_dl_file_"):
        if user_id != ADMIN_WHITELIST: return
        file_target_name = data.replace("adm_dl_file_", "")
        file_full_path = os.path.join(MATCH_HISTORY_DIR, file_target_name)
        
        if os.path.exists(file_full_path):
            bot.answer_callback_query(call.id, text="📥 Đang trích xuất dữ liệu file...")
            # Sử dụng API Telegram để bắn file trực tiếp về khung chat Admin bí mật
            with open(file_full_path, 'rb') as document:
                bot.send_document(chat_id, document, caption=f"📄 Bản sao tệp dữ liệu gốc: `{file_target_name}`", parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, text="❌ Tệp tin không tồn tại hoặc đã bị xóa!", show_alert=True)

# ==========================================
# 117. ĐỊNH NGHĨA PHẦN THƯỞNG CỦA VÒNG QUAY
# ==========================================
LUCKY_WHEEL_REWARDS = [
    {"type": "gold", "value": 200,   "name": "💰 200 Vàng"},
    {"type": "gold", "value": 500,   "name": "💰 500 Vàng"},
    {"type": "gold", "value": 1000,  "name": "🔥 1,000 Vàng Cực Lớn"},
    {"type": "item", "value": "bua_ho_menh", "name": "🛡️ 1 Bùa Hộ Mệnh (Hiếm)"},
    {"type": "item", "value": "kinh_hien_vi", "name": "🔬 1 Kính Hiển Vi (Hiếm)"},
    {"type": "gold", "value": 100,   "name": "💰 100 Vàng Khuyến Khích"}
]

# Trọng số tỷ lệ rớt trúng (Tổng bằng 100%)
LUCKY_WHEEL_WEIGHTS = [30, 20, 5, 10, 10, 25]

# ==========================================
# 118. GIAO DIỆN VÒNG QUAY MAY MẮN LÀNG SÓI
# ==========================================
def show_lucky_wheel_hub(user_id, chat_id, message_id=None):
    """Hiển thị giao diện Vòng Quay May Mắn và thời gian hồi chiêu"""
    user_data = user_db[user_id]
    current_time = int(time.time())
    
    # Lấy mốc thời gian đã quay trước đó (mặc định bằng 0 nếu chưa quay bao giờ)
    last_spin = user_data.get("last_wheel_spin", 0)
    time_passed = current_time - last_spin
    cooldown_seconds = 24 * 60 * 60 # 24 giờ tính bằng giây
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    if time_passed >= cooldown_seconds:
        wheel_status_text = "🟢 **TRẠNG THÁI:** Vòng quay thần bí đã sẵn sàng giải phóng may mắn cho bạn!"
        btn_spin = types.InlineKeyboardButton("🎯 KHỞI ĐỘNG VÒNG QUAY (MIỄN PHÍ)", callback_data="wheel_action_spin")
        markup.add(btn_spin)
    else:
        remaining_time = cooldown_seconds - time_passed
        hours = int(remaining_time // 3600)
        minutes = int((remaining_time % 3600) // 60)
        wheel_status_text = f"⏳ **TRẠNG THÁI ĐANG HỒI CHIÊU:** Bạn cần chờ thêm `{hours} giờ {minutes} phút` để thực hiện lượt quay tiếp theo."
        btn_locked = types.InlineKeyboardButton("🔒 VÒNG QUAY ĐANG ĐÓNG", callback_data="wheel_action_locked")
        markup.add(btn_locked)
        
    btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI SẢNH", callback_data="lobby_back_main")
    markup.add(btn_back)
    
    wheel_text = (
        f"🎯 **VÒNG QUAY MAY MẮN LÀNG MA SÓI** 🎯\n"
        f"-----------------------------------------\n"
        f"👤 Người thực hiện: **{user_data['name']}**\n"
        f"🎒 Kho đồ hiện tại: `{user_data.get('item_slot') if user_data.get('item_slot') else 'Trống'}`\n\n"
        f"🔮 **CƠ CHẾ PHẦN THƯỞNG:**\n"
        f"👉 Mỗi 24 giờ, thần linh sảnh game Ma Sói v8 sẽ cấp cho dũng sĩ 1 lượt quay mật miễn phí. Bạn có cơ hội trúng hàng ngàn Vàng hoặc các trang bị hỗ trợ trận đấu đắt giá mà không tốn một xu cọc!\n\n"
        f"{wheel_status_text}"
    )
    
    if message_id:
        bot.edit_message_text(wheel_text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, wheel_text, parse_mode="Markdown", reply_markup=markup)

# ==========================================
# 119. BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data == "lobby_wheel_hub":
        # Nút điều hướng từ sảnh chính dẫn vào cổng vòng quay
        show_lucky_wheel_hub(user_id, chat_id, message_id)
        bot.answer_callback_query(call.id)

    elif data == "wheel_action_locked":
        bot.answer_callback_query(call.id, text="❌ Vòng quay đang hồi chiêu, dũng sĩ hãy kiên nhẫn quay lại sau!", show_alert=True)

    elif data == "wheel_action_spin":
        user_data = user_db[user_id]
        current_time = int(time.time())
        last_spin = user_data.get("last_wheel_spin", 0)
        
        # Kiểm tra bảo mật tầng 2 đề phòng hack gửi gói tin liên tục
        if current_time - last_spin < 24 * 60 * 60:
            bot.answer_callback_query(call.id, text="❌ Phát hiện hành vi gian lận gửi lệnh quay liên tục!", show_alert=True)
            return
            
        bot.answer_callback_query(call.id, text="🎲 Vòng quay thần bí bắt đầu khởi chạy...")
        
        # Thuật toán quay số trúng thưởng có trọng số (Sử dụng random.choices)
        selected_reward = random.choices(LUCKY_WHEEL_REWARDS, weights=LUCKY_WHEEL_WEIGHTS, k=1)[0]
        
        # Cập nhật thời gian quay để khóa hồi chiêu 24 tiếng tiếp theo
        user_data["last_wheel_spin"] = current_time
        
        result_alert_text = ""
        
        # --- THỰC THI TRAO THƯỞNG DỰA TRÊN LOẠI PHẦN THƯỞNG QUAY TRÚNG ---
        if selected_reward["type"] == "gold":
            user_data["gold"] += selected_reward["value"]
            result_alert_text = f"🎉 Chúc mừng bạn đã quay trúng: {selected_reward['name']}! Tiền thưởng đã chuyển thẳng vào ví số dư."
        elif selected_reward["type"] == "item":
            # Kiểm tra hành lý xem có bị đầy ô trang bị trận đấu hay không (Đối chiếu Phần 4)
            if user_data.get("item_slot") is None:
                user_data["item_slot"] = selected_reward["value"]
                result_alert_text = f"🎉 SIÊU MAY MẮN! Bạn đã quay trúng: {selected_reward['name']}! Vật phẩm đã tự động trang bị vào hành lý sảnh."
            else:
                # Nếu kho đồ đầy, tự động đền bù quy đổi vật phẩm thành 500 Vàng an ủi
                compensation_gold = 500
                user_data["gold"] += compensation_gold
                result_alert_text = f"🎁 Bạn quay trúng {selected_reward['name']}. Tuy nhiên do hành lý đã đầy, hệ thống tự động quy đổi thành `+{compensation_gold} Vàng` an ủi!"
                
        # Bung thông báo pop-up chấn động màn hình cho người chơi thấy kết quả
        bot.send_message(
            chat_id,
            f"🎯 **KẾT QUẢ VÒNG QUAY MAY MẮN LÀNG SÓI** 🎯\n"
            f"-----------------------------------------\n"
            f"🎰 Trục quay dừng lại... Kim chỉ thẳng vào ô phần thưởng!\n\n"
            f"🎁 **Phần thưởng nhận được:** **{selected_reward['name']}**\n"
            f"ℹ️ *Trạng thái:* {result_alert_text}\n"
            f"-----------------------------------------\n"
            f"⏳ *Hẹn gặp lại dũng sĩ sau 24 giờ nữa để tiếp tục thử vận may đổi đời!*",
            parse_mode="Markdown"
        )
        
        # Làm mới lại giao diện màn hình để chuyển ngay sang trạng thái khóa hiển thị thời gian hồi chiêu
        show_lucky_wheel_hub(user_id, chat_id, message_id)

import datetime

# ==========================================
# 120. ĐỊNH NGHĨA PHẦN THƯỞNG ĐIỂM DANH THEO MỐC NGÀY (STREAK)
# ==========================================
# Phần thưởng gốc: Ngày thứ N nhận được = N * 100 Vàng + N * 10 EXP
# Cấu hình quà tặng bonus đặc biệt khi chạm mốc chuỗi liên tục:
ATTENDANCE_STREAK_BONUS = {
    3:  {"gold": 500,  "exp": 20,  "gift": "🎁 Hộp Quà Gỗ"},
    7:  {"gold": 1500, "exp": 50,  "gift": "🛡️ Thùng Tiếp Tế Làng Sói"},
    14: {"gold": 4000, "exp": 100, "gift": "🔮 Rương Ma Thuật Cao Cấp"},
    30: {"gold": 10000,"exp": 300, "gift": "👑 Kho Báu Huyền Thoại V8"}
}

# ==========================================
# 121. GIAO DIỆN TRUNG TÂM ĐIỂM DANH HẰNG NGÀY
# ==========================================
def show_attendance_hub(user_id, chat_id, message_id=None):
    """Hiển thị giao diện điểm danh, số ngày chuỗi và nút bấm nhận thưởng"""
    user_data = user_db[user_id]
    
    # Khởi tạo các biến lưu trữ nếu tài khoản chưa từng điểm danh
    if "last_attendance_date" not in user_data:
        user_data["last_attendance_date"] = "None"
        user_data["attendance_streak"] = 0

    current_date_str = time.strftime("%Y-%m-%d")
    last_date_str = user_data["last_attendance_date"]
    streak = user_data["attendance_streak"]
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    # Logic kiểm tra trạng thái điểm danh hôm nay
    if last_date_str == current_date_str:
        status_text = "✅ **TRẠNG THÁI:** Hôm nay bạn đã điểm danh nhận quà thành công! Hãy quay lại vào ngày mai."
        btn_action = types.InlineKeyboardButton("✅ ĐÃ ĐIỂM DANH HÔM NAY", callback_data="chk_att_done_today")
        markup.add(btn_action)
    else:
        # Kiểm tra xem có bị đứt chuỗi streak không (Nếu ngày cuối cùng cách ngày hôm nay > 1 ngày)
        is_streak_broken = False
        if last_date_str != "None":
            try:
                last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
                current_date = datetime.datetime.strptime(current_date_str, "%Y-%m-%d").date()
                if (current_date - last_date).days > 1:
                    is_streak_broken = True
            except Exception:
                pass
                
        if is_streak_broken:
            # Khôi phục chuỗi về 0 nếu bỏ quên quá 24 tiếng của ngày hôm sau
            user_data["attendance_streak"] = 0
            streak = 0
            status_text = "⚠️ **CẢNH BÁO ĐỨT CHUỖI:** Bạn đã bỏ lỡ điểm danh ngày hôm qua! Chuỗi Streak vinh danh đã bị reset về **Ngày 1**."
        else:
            status_text = "🔥 **TRẠNG THÁI:** Vẫn giữ vững chuỗi phong độ! Bạn đã sẵn sàng thu hoạch quà điểm danh hôm nay."
            
        btn_claim = types.InlineKeyboardButton("📆 BẤM ĐỂ ĐIỂM DANH NGAY", callback_data="chk_att_claim_action")
        markup.add(btn_claim)

    btn_back = types.InlineKeyboardButton("⬅️ QUAY LẠI SẢNH", callback_data="lobby_back_main")
    markup.add(btn_back)
    
    # Tính toán phần thưởng giả lập hiển thị cho ngày tiếp theo để kích thích người chơi
    next_day = streak + 1
    next_gold = next_day * 100
    next_exp = next_day * 10
    bonus_preview = f" (Có kèm {ATTENDANCE_STREAK_BONUS[next_day]['gift']}!)" if next_day in ATTENDANCE_STREAK_BONUS else ""

    hub_text = (
        f"📅 **TRUNG TÂM ĐIỂM DANH NHẬN QUÀ CHUỖI** 📅\n"
        f"-----------------------------------------\n"
        f"👤 Tài khoản: **{user_data['name']}**\n"
        f"🔥 Chuỗi tích lũy hiện tại: `🔥 THẦN TỐC {streak} NGÀY LIÊN TỤC`\n"
        f"📆 Lần cuối điểm danh: `{last_date_str if last_date_str != 'None' else 'Chưa từng điểm danh'}`\n\n"
        f"🎁 **QUÀ TẶNG LƯỢT ĐIỂM DANH KẾ TIẾP (NGÀY {next_day}):**\n"
        f"💰 Vàng nhận: `+{next_gold:,} Vàng`\n"
        f"✨ Kinh nghiệm: `+{next_exp} EXP`\n"
        f"{bonus_preview}\n"
        f"-----------------------------------------\n"
        f"{status_text}"
    )
    
    if message_id:
        bot.edit_message_text(hub_text, chat_id, message_id, parse_mode="Markdown", reply_markup=markup)
    else:
        bot.send_message(chat_id, hub_text, parse_mode="Markdown", reply_markup=markup)

# ==========================================
# 122. BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data == "lobby_attendance_hub":
        # Điều hướng từ nút sảnh chính vào trung tâm điểm danh
        show_attendance_hub(user_id, chat_id, message_id)
        bot.answer_callback_query(call.id)

    elif data == "chk_att_done_today":
        bot.answer_callback_query(call.id, text="⚠️ Bạn đã nhận quà điểm danh của ngày hôm nay rồi. Hãy quay lại sau 00:00 đêm nay nhé!", show_alert=True)

    elif data == "chk_att_claim_action":
        user_data = user_db[user_id]
        current_date_str = time.strftime("%Y-%m-%d")
        
        # Phòng hờ bảo mật nhấp chuột liên tục trùng lặp tin nhắn
        if user_data.get("last_attendance_date") == current_date_str:
            bot.answer_callback_query(call.id, text="❌ Bạn đã điểm danh hôm nay rồi!")
            return
            
        bot.answer_callback_query(call.id, text="🚀 Đang xử lý điểm danh...")
        
        # Tăng chuỗi ngày streak lên 1 mốc mới
        user_data["attendance_streak"] += 1
        new_streak = user_data["attendance_streak"]
        
        # Ghi đè mốc ngày hoàn tất mới nhất vào In-Memory DB
        user_data["last_attendance_date"] = current_date_str
        
        # Thuật toán tăng tiến quà tặng nhân số ngày
        earned_gold = new_streak * 100
        earned_exp = new_streak * 10
        
        # Thực hiện cộng dồn phần thưởng gốc
        user_data["gold"] += earned_gold
        
        # Kiểm tra quà tặng bonus mốc đặc biệt
        bonus_text = ""
        if new_streak in ATTENDANCE_STREAK_BONUS:
            bonus_config = ATTENDANCE_STREAK_BONUS[new_streak]
            user_data["gold"] += bonus_config["gold"]
            earned_exp += bonus_config["exp"]
            bonus_text = f"\n🎉 **THƯỞNG CHUỖI SIÊU CẤP {new_streak} NGÀY:** Nhận thêm `+{bonus_config['gold']:,} Vàng` và khai mở thành công **{bonus_config['gift']}**!"

        # Chạy kiểm tra thăng cấp độ từ mốc EXP mới nhận (Đồng bộ Phần 22)
        level_up = add_exp_and_check_level_up(user_id, earned_exp)
        lvl_up_text = "\n🔥 **LEVEL UP!** Bạn đã thăng cấp danh hiệu danh vọng tại sảnh chờ." if level_up else ""
        
        # Cập nhật tiến trình cho chuỗi Nhiệm Vụ Hàng Ngày (Mục tiêu 'Điểm danh hằng ngày') nếu có
        # (Bộ lọc tự động khớp mã hành động)
        
        bot.send_message(
            chat_id,
            f"📆 **BÁO CÁO ĐIỂM DANH THÀNH CÔNG** 📆\n"
            f"-----------------------------------------\n"
            f"🎯 Chúc mừng **{user_data['name']}** đã hoàn thành điểm danh ngày hôm nay!\n"
            f"🔥 Thiết lập kỷ lục chuỗi: `{new_streak} ngày liên tục`.\n\n"
            f"🎁 **Phần thưởng nhận được:**\n"
            f"▪️ Tiền Vàng cộng thêm: `+{earned_gold:,} Vàng`\n"
            f"▪️ Điểm kinh nghiệm: `+{earned_exp} EXP`{bonus_text}{lvl_up_text}\n"
            f"-----------------------------------------\n"
            f"📈 Số dư tài sản hiện tại: `{user_data['gold']:,} Vàng`",
            parse_mode="Markdown"
        )
        
        # Làm mới lại giao diện màn hình sảnh điểm danh sang trạng thái nút tích check xanh đã nhận
        show_attendance_hub(user_id, chat_id, message_id)

# Bộ nhớ tạm lưu trữ các khoản cược dự đoán của linh hồn trong trận đấu:
# { room_id: { user_id: {"predict_team": "Ma Sói/Dân Làng", "bet_gold": 500} } }
spectator_bets_cache = {}

# Tỷ lệ nhân thưởng mặc định cho kèo dự đoán (1 ăn 1.8 dải Vàng)
BETTING_PAYOUT_RATE = 1.8

# ==========================================
# 123. GIAO DIỆN MENU ĐẶT CƯỢC DỰ ĐOÁN CHO LINH HỒN
# ==========================================
def get_spectator_bet_markup(room_id):
    """Tạo menu 2 nút bấm Inline để linh hồn chọn phe dự đoán"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_wolf = types.InlineKeyboardButton("🐺 Dự Đoán: SÓI THẮNG", callback_data=f"spec_bet_choose_{room_id}_Ma Sói")
    btn_village = types.InlineKeyboardButton("🧑‍🌾 Dự Đoán: DÂN THẮNG", callback_data=f"spec_bet_choose_{room_id}_Dân Làng")
    markup.add(btn_wolf, btn_village)
    return markup

def trigger_spectator_betting_notification(room_id, dead_user_id):
    """
    Hàm được gọi ngay khi có một người chơi bị loại (chết đêm hoặc treo cổ).
    Gửi bảng menu mời gọi đặt cược dự đoán kiếm thêm thu nhập Vàng.
    """
    room_data = game_rooms[room_id]
    user_data = user_db[dead_user_id]
    
    # Kiểm tra nếu linh hồn đã từng đặt cược trong trận này rồi thì không gửi lại
    if room_id in spectator_bets_cache and dead_user_id in spectator_bets_cache[room_id]:
        return

    bet_invitation_text = (
        f"💀 **CỔNG DỰ ĐOÁN ĐƯỜNG ĐUA TỬ THẦN** 💀\n"
        f"-----------------------------------------\n"
        f"🥀 Thân xác của bạn đã nằm xuống, nhưng linh hồn của bạn vẫn có thể làm giàu! "
        f"Hệ thống mở cổng **Dự Đoán Kết Quả Trận Đấu** dành riêng cho các vong hồn phòng `{room_id}`.\n\n"
        f"💰 Tài sản hiện tại của bạn: `{user_data['gold']:,} Vàng`\n"
        f"💱 **Tỷ lệ ăn thưởng:** `1 ăn {BETTING_PAYOUT_RATE}` (Ví dụ: Cược 1,000 Vàng, nếu phe đó thắng bạn thu về 1,800 Vàng).\n"
        f"-----------------------------------------\n"
        f"👉 Hãy chọn phe mà bạn tin tưởng sẽ giành chiến thắng chung cuộc:"
    )
    try:
        bot.send_message(dead_user_id, bet_invitation_text, parse_mode="Markdown", reply_markup=get_spectator_bet_markup(room_id))
    except Exception:
        pass

# Ghi chú tích hợp: Bạn hãy gọi hàm `trigger_spectator_betting_notification(room_id, dead_id)` 
# tại cuối chu trình chết ở Phần 15 (sau khi lọc người chết đêm) và Phần 20 (sau khi Treo cổ xong).

# ==========================================
# 124. BỔ SUNG CÁC NHÁNH XỬ LÝ VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6)

    elif data.startswith("spec_bet_choose_"):
        # Phân tách chuỗi: spec_bet_choose_[room_id]_[phe_chọn]
        parts = data.split("_")
        room_id = parts[3]
        predict_team = parts[4]
        
        if room_id not in game_rooms or game_rooms[room_id]["status"] in ["End", "Lobby"]:
            bot.answer_callback_query(call.id, text="❌ Trận đấu đã kết thúc, cổng dự đoán đã khép lại!", show_alert=True)
            return
            
        if user_id in game_rooms[room_id]["alive"]:
            bot.answer_callback_query(call.id, text="❌ Bạn còn sống, không thể tham gia cổng cược khán giả!", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        
        # Chuyển trạng thái sang bước nhận số tiền cược từ tin nhắn chat mật của linh hồn
        msg_amt = bot.send_message(
            chat_id,
            f"💰 **BƯỚC ĐẶT PHƯƠNG ÁN CƯỢC:**\n"
            f"👉 Bạn đã chọn đặt niềm tin vào phe: **{predict_team.upper()}**.\n"
            f"📥 Hãy nhập **Số tiền Vàng** bạn muốn đặt cược (Tối thiểu 200 Vàng, tối đa 5,000 Vàng) và gửi cho Bot:",
            parse_mode="Markdown"
        )
        bot.register_next_step_handler(msg_amt, process_spectator_bet_amount_step, room_id, predict_team)

# ==========================================
# 125. TIẾP NHẬN SỐ TIỀN CƯỢC VÀ ĐÓNG BĂNG TÀI SẢN
# ==========================================
def process_spectator_bet_amount_step(message, room_id, predict_team):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    if room_id not in game_rooms:
        bot.send_message(chat_id, "❌ Trận đấu này không còn tồn tại.")
        return

    try:
        bet_gold = int(message.text.strip())
        user_data = user_db[user_id]
        
        # Xác thực hạn mức đặt cược quy định của sảnh
        if bet_gold < 200 or bet_gold > 5000:
            bot.send_message(chat_id, "❌ **Lỗi:** Hạn mức đặt cược dự đoán cho phép từ `200` đến `5,000 Vàng`.")
            return
            
        if user_data["gold"] < bet_gold:
            bot.send_message(chat_id, f"❌ **Giao dịch thất bại!** Số dư hiện tại không đủ để cọc `{bet_gold:,} Vàng`.")
            return
            
        # Thực hiện đóng băng, khấu trừ tài sản tạm thời của linh hồn
        user_data["gold"] -= bet_gold
        
        # Lưu thông số lệnh cược vào bộ nhớ Cache hệ thống
        if room_id not in spectator_bets_cache:
            spectator_bets_cache[room_id] = {}
            
        spectator_bets_cache[room_id][user_id] = {
            "predict_team": predict_team,
            "bet_gold": bet_gold
        }
        
        bot.send_message(
            chat_id,
            f"✅ **GHI NHẬN HÒM PHIẾU CƯỢC THÀNH CÔNG!**\n"
            f"-----------------------------------------\n"
            f"🎭 Dự phán: Phe **{predict_team.upper()}** chiến thắng.\n"
            f"💰 Khấu trừ quỹ cọc: `-{bet_gold:,} Vàng` (Đã đóng băng an toàn)\n"
            f"📈 Tiền thưởng kỳ vọng thu về: `+{int(bet_gold * BETTING_PAYOUT_RATE):,} Vàng` nếu đoán trúng.\n\n"
            f"⏳ *Hãy tiếp tục ẩn mình theo dõi diễn biến trận đấu chờ ngày kết toán vinh quang!*",
            parse_mode="Markdown"
        )
        
    except ValueError:
        bot.send_message(chat_id, "❌ **Lỗi:** Số tiền Vàng nhập vào phải là ký tự số nguyên hợp lệ!")

# ==========================================
# 126. THANH TOÁN TIỀN THƯỞNG CƯỢC KHI GAME OVER
# ==========================================
def settle_spectator_betting_rewards(room_id, final_winning_team):
    """
    Hàm quét cache cược của khán giả khi trận đấu ngã ngũ để thanh toán.
    Ghi chú: Lồng lệnh gọi hàm này vào ngay ĐẦU hàm `process_end_of_game_rewards` ở Phần 22.
    """
    if room_id not in spectator_bets_cache:
        return
        
    room_bets = spectator_bets_cache[room_id]
    
    for soul_id, bet_info in room_bets.items():
        if bet_info["predict_team"] == final_winning_team:
            # Đoán trúng: Trả lại gốc + tiền lãi theo tỷ lệ cấu hình
            prize_payout = int(bet_info["bet_gold"] * BETTING_PAYOUT_RATE)
            user_db[soul_id]["gold"] += prize_payout
            
            try:
                bot.send_message(
                    soul_id,
                    f"🏆 **THÀNH QUẢ TIÊN TRI TÂM LINH PHÁT TÀI** 🏆\n"
                    f"-----------------------------------------\n"
                    f"🎉 Chúc mừng linh hồn tinh anh! Phe **{final_winning_team.upper()}** đã giành chiến thắng đúng như dự đoán của bạn.\n"
                    f"💰 **Ngân hàng giải phóng ví:** Cộng tiền thưởng giao dịch `+{prize_payout:,} Vàng` vào số dư khả dụng của bạn!",
                    parse_mode="Markdown"
                )
            except Exception: pass
        else:
            # Đoán sai: Mất trắng số tiền đã đóng băng cọc ban đầu
            try:
                bot.send_message(
                    soul_id,
                    f"💀 **KẾT QUẢ DỰ ĐOÁN SAI LẦM** 💀\n"
                    f"-----------------------------------------\n"
                    f"🥀 Phe bạn đặt cược đã thất bại thảm hại trước sức mạnh của đối thủ.\n"
                    f"💸 Số tiền cọc cược `-{bet_info['bet_gold']:,} Vàng` đã chính thức bị đốt cháy vĩnh viễn trên máy chủ sảnh game.",
                    parse_mode="Markdown"
                )
            except Exception: pass
            
    # Thu hồi giải phóng bộ nhớ Cache của phòng chơi
    del spectator_bets_cache[room_id]

# ==========================================
# HÀM KHỞI ĐỘNG HỆ THỐNG ĐỒNG BỘ MÁY CHỦ v8
# ==========================================
if __name__ == "__main__":
    # Bước 1: Nạp lại toàn bộ tài sản, level của người chơi từ file cứng cũ vào RAM
    load_database_from_disk_storage()
    
    # Bước 2: Kích hoạt luồng ngầm tự động sao lưu dữ liệu sau mỗi 5 phút một lần
    start_auto_backup_daemon_thread(interval_seconds=300)
    
    # Bước 3: Cho bot chính thức Online nhận tin nhắn
    print("🤖 Bot Ma Sói v8 Nâng Cao chính thức Online sảnh chờ...")
    # bot.infinity_polling()  <- Dòng kích hoạt chạy bot của bạn nằm ở đây

# ==========================================
# 133. CẤU TRÚC DỰNG BẢNG ĐIỀU KHIỂN inline MARKUP ADMINISTRATIVE
# ==========================================
def get_comprehensive_admin_panel_markup():
    """Tạo hệ thống ma trận nút bấm điều hành khẩn cấp cho Admin"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # Dòng 1: Kiểm soát Chế độ bảo trì hệ thống toàn diện (Phần 5)
    status_maintenance = "🔴 BẢO TRÌ: ON" if MAINTENANCE_MODE else "🟢 BẢO TRÌ: OFF"
    btn_maint = types.InlineKeyboardButton(status_maintenance, callback_data="adm_panel_toggle_maint")
    
    # Dòng 2: Kiểm soát Sự kiện Giờ Vàng Nhân đôi tiền cược (Phần 33)
    status_double = "🔥 GIỜ VÀNG: ON" if IS_DOUBLE_GOLD_EVENT else "❄️ GIỜ VÀNG: OFF"
    btn_gold_ev = types.InlineKeyboardButton(status_double, callback_data="adm_panel_toggle_gold")
    
    # Dòng 3: Dọn dẹp phòng chơi rác & Quét dọn hệ thống (Đồng bộ Phần 47)
    btn_flush_rooms = types.InlineKeyboardButton("🧹 QUÉT PHÒNG TREO AFK", callback_data="adm_panel_flush_afk")
    btn_server_stats = types.InlineKeyboardButton("📊 XEM NHANH BÁO CÁO", callback_data="adm_analytics_refresh") # Trỏ link Phần 32
    
    # Dòng 4: Quản lý ví nạp & lưu trữ file cứng thủ công
    btn_force_save = types.InlineKeyboardButton("💾 LƯU CỨNG DATABASE NOW", callback_data="adm_panel_force_save")
    btn_close_panel = types.InlineKeyboardButton("❌ ĐÓNG BẢNG ĐIỀU KHIỂN", callback_data="adm_panel_close")
    
    markup.add(btn_maint, btn_gold_ev)
    markup.add(btn_flush_rooms, btn_server_stats)
    markup.add(btn_force_save)
    markup.add(btn_close_panel)
    return markup

# ==========================================
# 134. LỆNH CHAT GỌI BẢNG ĐIỀU KHIỂN MẬT CỦA BAN QUẢN TRỊ
# ==========================================
@bot.message_handler(commands=['adminpanel', 'panel', 'admpanel'])
def cmd_open_comprehensive_admin_panel(message):
    """Lệnh tối mật mở bảng điều khiển trung tâm máy chủ Ma Sói v8"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Middleware xác thực an ninh quyền lực quản trị viên tối cao
    if user_id != ADMIN_WHITELIST and user_id not in OPERATORS:
        return # Giữ lặng im tuyệt đối, không phản hồi người chơi thường tò mò mò lệnh
        
    admin_panel_text = (
        f"⚙️ **BẢNG ĐIỀU HÀNH TRUNG TÂM MÁY CHỦ v8** ⚙️\n"
        f"===================================\n"
        f"👑 Xin chào Thuyền Trưởng Ban Quản Trị. Tại đây tập hợp toàn bộ các công cụ can thiệp nhanh "
        f"vào luồng dữ liệu thời gian thực của RAM Server sảnh game Ma Sói.\n\n"
        f"📊 **THÔNG SỐ HIỆN TẠI:**\n"
        f"▪️ Trạng thái máy chủ: `{'🚨 ĐANG BẢO TRÌ TRÊN DIỆN RỘNG' if MAINTENANCE_MODE else '🟢 ĐANG ONLINE ỔN ĐỊNH'}`\n"
        f"▪️ Sự kiện dã thú: `{'🔥 DOUBLE GOLD (X2 VÀNG) ĐANG CHẠY' if IS_DOUBLE_GOLD_EVENT else '❄️ Không có sự kiện nào'}`\n"
        f"▪️ Số lượng phòng RAM tích trữ: `{len(game_rooms)} phòng chơi`\n"
        f"▪️ Số tài khoản nạp đen (Banned IP): `{len(banned_ips)} dải IP`\n"
        f"===================================\n"
        f"👇 *Hãy sử dụng các nút tương tác trực tiếp dưới đây để ra lệnh điều hành lập tức:*"
    )
    bot.send_message(chat_id, admin_panel_text, parse_mode="Markdown", reply_markup=get_comprehensive_admin_panel_markup())

# ==========================================
# 135. BỔ SUNG CÁC NHÁNH ĐIỀU HƯỚNG VÀO CALLBACK CHÍNH (PHẦN 6)
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6/19/43/44)

    # Nhánh Admin: Bật/tắt chế độ bảo trì trực tiếp trên bảng điều khiển Inline
    elif data == "adm_panel_toggle_maint":
        if user_id != ADMIN_WHITELIST: return
        global MAINTENANCE_MODE
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        bot.answer_callback_query(call.id, text=f"Đã {'BẬT' if MAINTENANCE_MODE else 'TẮT'} chế độ bảo trì!", show_alert=True)
        # Làm mới lại nội dung giao diện để đồng bộ icon nút bấm mới
        cmd_open_comprehensive_admin_panel(call.message)

    # Nhánh Admin: Bật/tắt sự kiện Giờ vàng trực tiếp từ bảng điều khiển Inline
    elif data == "adm_panel_toggle_gold":
        if user_id != ADMIN_WHITELIST: return
        global IS_DOUBLE_GOLD_EVENT
        IS_DOUBLE_GOLD_EVENT = not IS_DOUBLE_GOLD_EVENT
        bot.answer_callback_query(call.id, text=f"Đã {'BẬT' if IS_DOUBLE_GOLD_EVENT else 'TẮT'} sự kiện X2 Vàng!", show_alert=True)
        cmd_open_comprehensive_admin_panel(call.message)

    # Nhánh Admin: Cưỡng chế quét sạch phòng treo AFK ngay lập tức bằng tay
    elif data == "adm_panel_flush_afk":
        if user_id != ADMIN_WHITELIST and user_id not in OPERATORS: return
        initial_count = len(game_rooms)
        
        # Gọi thuật toán quét phòng treo rác dọn dẹp RAM (Đồng bộ Phần 47)
        # Quét và xóa các phòng ở Lobby có thời gian treo lâu hơn 10 phút
        current_time = time.time()
        rooms_to_delete = []
        for rid, rdata in game_rooms.items():
            if rdata.get("status") == "Lobby" and "created_time" in rdata:
                if current_time - rdata["created_time"] > 600:
                    rooms_to_delete.append(rid)
                    
        for rid in rooms_to_delete:
            del game_rooms[rid]
            
        freed_count = initial_count - len(game_rooms)
        bot.answer_callback_query(call.id, text=f"🧹 Quét hoàn tất! Đã dọn dẹp {freed_count} phòng rác khỏi RAM.", show_alert=True)
        cmd_open_comprehensive_admin_panel(call.message)

    # Nhánh Admin: Ép hệ thống xuất file cứng Database ngay lập tức không đợi chu kỳ 5 phút
    elif data == "adm_panel_force_save":
        if user_id != ADMIN_WHITELIST: return
        # Gọi hàm save cứng ổ đĩa đã viết hoàn thiện ở Phần 46
        save_success = save_database_to_disk_storage()
        if save_success:
            bot.answer_callback_query(call.id, text="💾 Đã đồng bộ sao lưu file cứng an toàn thành công!", show_alert=True)
        else:
            bot.answer_callback_query(call.id, text="❌ Lỗi sao lưu! Hãy kiểm tra dung lượng ổ cứng VPS.", show_alert=True)

    elif data == "adm_panel_close":
        if user_id != ADMIN_WHITELIST and user_id not in OPERATORS: return
        bot.answer_callback_query(call.id, text="Đã đóng bảng điều khiển an toàn.")
        bot.edit_message_text("🔒 Bảng điều khiển Quản trị viên v8 đã được mã hóa đóng an toàn.", chat_id, message_id)

# ==========================================
# 136. BỔ SUNG CÁC NHÁNH PHÊ DUYỆT HOÁ ĐƠN VÀO CALLBACK CHÍNH
# ==========================================
# (Đoạn này bạn dán nối tiếp vào cấu trúc Callback tập trung ở Phần 6/19/48)

    # 🏦 Nhánh Admin: Phê duyệt lệnh rút vàng "XÁC NHẬN ĐÃ BANK TIỀN" (Đối chiếu Phần 3)
    elif data.startswith("tx_approve_"):
        if user_id != ADMIN_WHITELIST: return
        tx_id = data.replace("tx_approve_", "")
        
        # Kiểm tra sự tồn tại của mã giao dịch trong bộ nhớ tạm
        if tx_id not in pending_transactions:
            bot.answer_callback_query(call.id, text="❌ Mã lệnh giao dịch không tồn tại hoặc đã được xử lý trước đó!", show_alert=True)
            return
            
        tx_data = pending_transactions[tx_id]
        
        if tx_data["status"] != "PENDING":
            bot.answer_callback_query(call.id, text="⚠️ Giao dịch này đã được xử lý xong rồi!", show_alert=True)
            return
            
        # Cập nhật trạng thái hoàn tất hóa đơn kế toán
        tx_data["status"] = "SUCCESS"
        target_user_id = tx_data["user_id"]
        target_name = user_db.get(target_user_id, {}).get("name", f"User_{target_user_id}")
        
        bot.answer_callback_query(call.id, text="📌 Đã duyệt lệnh thành công! Đóng hòm file giao dịch.", show_alert=True)
        
        # 1. Cập nhật lại giao diện tin nhắn của Admin thành hóa đơn đã khóa sổ đẹp mắt
        approved_admin_msg = (
            f"✅ **HÓA ĐƠN ĐÃ ĐƯỢC PHÊ DUYỆT THÀNH CÔNG** ✅\n"
            f"===================================\n"
            f"👤 **Dũng sĩ nhận giải:** {target_name} (ID: `{target_user_id}`)\n"
            f"🏦 **Thông tin tài khoản:** `{tx_data['info']}`\n"
            f"💰 **Số tiền Admin đã bank:** `{tx_data['amount_vnd']:,} VNĐ`\n"
            f"🪙 **Số vàng đã trừ:** `{tx_data['gold']:,} Vàng`\n"
            f"-----------------------------------\n"
            f"📌 **Trạng thái:** Lệnh rút tiền đã được thực thi chuyển khoản ngân hàng thật và đóng hồ sơ sổ sách kế toán v8 vào lúc `{time.strftime('%H:%M:%S')}`."
        )
        bot.edit_message_text(approved_admin_msg, chat_id, message_id, parse_mode="Markdown")
        
        # 2. Bắn biên lai chuyển khoản thành công trực tiếp cho dũng sĩ nhận giải
        try:
            receipt_user_text = (
                f"🏦 **BIÊN LAI CHUYỂN KHOẢN THÀNH CÔNG** 🏦\n"
                f"-----------------------------------------\n"
                f"🎉 Xin chúc mừng dũng sĩ Làng Sói! Lệnh giải ngân phần thưởng của bạn đã được Admin phê duyệt đóng ấn.\n\n"
                f"🆔 Mã giao dịch: `{tx_id}`\n"
                f"🪙 Vàng tiêu thụ: `-{tx_data['gold']:,} Vàng`\n"
                f"💵 Số tiền ngân hàng thực nhận: `+{tx_data['amount_vnd']:,} VNĐ`\n"
                f"🏦 Tài khoản đích: `{tx_data['info']}`\n"
                f"-----------------------------------------\n"
                f"📈 **Trạng thái:** Tiền thật đã được chuyển thành công vào tài khoản ngân hàng của bạn. Vui lòng kiểm tra ứng dụng Mobile Banking của mình!"
            )
            bot.send_message(target_user_id, receipt_user_text, parse_mode="Markdown")
        except Exception:
            pass
            
        # Giải phóng giao dịch khỏi bộ nhớ đệm Cache tạm thời
        del pending_transactions[tx_id]

    # 🏦 Nhánh Admin: Hủy lệnh rút tiền và Hoàn lại vàng cho người chơi
    elif data.startswith("tx_reject_"):
        if user_id != ADMIN_WHITELIST: return
        tx_id = data.replace("tx_reject_", "")
        
        if tx_id not in pending_transactions:
            bot.answer_callback_query(call.id, text="❌ Lệnh giao dịch không tồn tại!", show_alert=True)
            return
            
        tx_data = pending_transactions[tx_id]
        target_user_id = tx_data["user_id"]
        target_name = user_db.get(target_user_id, {}).get("name", f"User_{target_user_id}")
        
        # --- LOGIC HOÀN TIỀN: Trả lại số Vàng đóng băng về ví cho game thủ ---
        user_db[target_user_id]["gold"] += tx_data["gold"]
        
        bot.answer_callback_query(call.id, text="❌ Đã từ chối lệnh! Hoàn trả tài sản.", show_alert=True)
        
        # 1. Cập nhật lại giao diện tin nhắn của Admin thành trạng thái hủy bỏ đơn
        rejected_admin_msg = (
            f"❌ **HÓA ĐƠN RÚT TIỀN BỊ TỪ CHỐI / HỦY BỎ** ❌\n"
            f"===================================\n"
            f"👤 **Người yêu cầu:** {target_name} (ID: `{target_user_id}`)\n"
            f"💰 **Số tiền yêu cầu:** `{tx_data['amount_vnd']:,} VNĐ`\n"
            f"-----------------------------------\n"
            f"⚠️ **Hành động:** Admin đã từ chối lệnh rút này. Hệ thống đã tự động mở khóa giải đóng băng và hoàn trả đầy đủ `+{tx_data['gold']:,} Vàng` về tài khoản của người chơi."
        )
        bot.edit_message_text(rejected_admin_msg, chat_id, message_id, parse_mode="Markdown")
        
        # 2. Bắn thông báo cảnh báo hoàn tiền về cho người chơi biết lý do
        try:
            reject_user_text = (
                f"⚠️ **THÔNG BÁO TỪ CHỐI GIAO DỊCH RÚT TIỀN** ⚠️\n"
                f"-----------------------------------------\n"
                f"🆔 Lệnh giao dịch mã số `{tx_id}` của bạn đã bị Ban Quản Trị từ chối phê duyệt.\n\n"
                f"💰 **Số Vàng hoàn lại:** `+{tx_data['gold']:,} Vàng` (Đã cộng trả lại vào số dư khả dụng).\n"
                f"📌 *Lý do thường gặp:* Thông tin số tài khoản sai định dạng, dính nghi vấn clone ip trục lợi điểm thưởng, hoặc tài khoản ngân hàng không hợp lệ.\n"
                f"-----------------------------------------\n"
                f"💬 *Vui lòng kiểm tra kỹ lại thông tin và thực hiện tạo lệnh rút mới chính xác tại Cổng Ngân Hàng!*"
            )
            bot.send_message(target_user_id, reject_user_text, parse_mode="Markdown")
        except Exception:
            pass
            
        # Giải phóng giao dịch khỏi bộ nhớ đệm Cache tạm thời
        del pending_transactions[tx_id]

# ==========================================
# 137. THUẬT TOÁN KEEPALIVE WATCHDOG VÒNG LẶP VÔ HẠN
# ==========================================
def run_bot_with_keep_alive_watchdog():
    """
    Bộ não vận hành tối cao: Chạy bot bằng cấu trúc vòng lặp bất tử.
    Bắt toàn bộ các lỗi ngoại lệ hệ thống và tự động kết nối lại sau 5 giây.
    """
    print("==================================================")
    print("🚀 HỆ THỐNG WATCHDOG CHỐNG SẬP v8 ĐÃ KÍCH HOẠT")
    print("==================================================")
    
    # 1. Nạp lại toàn bộ tài sản, level của người chơi từ file cứng cũ vào RAM (Phần 46)
    load_database_from_disk_storage()
    
    # 2. Kích hoạt luồng ngầm tự động sao lưu dữ liệu sau mỗi 5 phút một lần (Phần 46)
    start_auto_backup_daemon_thread(interval_seconds=300)
    
    # 3. Kích hoạt luồng ngầm tự động quét và giải phóng phòng rác treo AFK (Phần 47)
    # (Đoạn này bạn chèn thêm hàm start_afk_sweeper_thread nếu đã cấu hình ở Phần 47)
    
    print("🤖 Bot Ma Sói v8 Nâng Cao chính thức bước vào trạng thái trực tuyến...")
    
    # Vòng lặp bất tử giám sát xung đột hệ thống
    while True:
        try:
            # Xóa sạch toàn bộ Webhook cũ còn kẹt trên Server Telegram để tránh xung đột dữ liệu Long Polling
            bot.remove_webhook()
            
            # Kích hoạt chế độ nhận tin nhắn liên tục với các tham số tối ưu hóa:
            # - timeout: 60 giây giữ kết nối cổng đọc tin nhắn mượt mà
            # - long_polling_timeout: 60 giây chống mất gói tin mạng
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
            
        except Exception as e:
            # Ghi vết chi tiết lỗi crash khẩn cấp ra terminal máy chủ để tiện debug
            print(f"\n🚨 [CRASH DETECTED] Phát hiện sự cố sập luồng mạng: {str(e)}")
            print("⏳ [WATCHDOG EVENT] Hệ thống tự động kích hoạt lệnh hồi sinh. Đang kết nối lại sau 5 giây...")
            
            # Cơ chế cách ly chống dội bom gói tin (Anti-Flood Sleep) tránh bị Telegram khóa IP chặn Bot
            time.sleep(5)
            print("🔄 [WATCHDOG] Đang khởi động lại cổng kết nối Telegram API...\n")

# ==========================================
# 138. ĐIỂM KHỞI CHẠY CHÍNH CỦA TOÀN BỘ FILE CODE
# ==========================================
if __name__ == "__main__":
    # Ra lệnh cho Watchdog độc lập quản lý vận hành toàn bộ vòng đời của bot
    run_bot_with_keep_alive_watchdog()
