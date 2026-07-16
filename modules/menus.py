# modules/menus.py
from telebot import types

def main_menu_keyboard():
    """Giao diện Menu chính hiển thị khi người chơi bấm /start chat riêng với Bot"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_profile = types.InlineKeyboardButton("📊 Hồ Sơ Cá Nhân", callback_data="main:profile")
    btn_leaderboard = types.InlineKeyboardButton("🏆 Bảng Xếp Hạng", callback_data="main:leaderboard")
    btn_help = types.InlineKeyboardButton("📖 Hướng Dẫn Luật", callback_data="main:help")
    btn_roles = types.InlineKeyboardButton("🔮 Danh Sách Vai Trò", callback_data="main:roles")
    
    markup.add(btn_profile, btn_leaderboard)
    markup.add(btn_help, btn_roles)
    return markup

def lobby_menu_keyboard():
    """Menu tương tác tại phòng chờ trong nhóm chat chung"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_join = types.InlineKeyboardButton("✅ Tham Gia", callback_data="lobby:join")
    btn_leave = types.InlineKeyboardButton("🚪 Rời Phòng", callback_data="lobby:leave")
    btn_status = types.InlineKeyboardButton("📋 Danh Sách", callback_data="lobby:status")
    btn_start = types.InlineKeyboardButton("🏁 Bắt Đầu Game", callback_data="lobby:start")
    
    markup.add(btn_join, btn_leave)
    markup.add(btn_status, btn_start)
    return markup

def back_to_main_keyboard():
    """Nút bấm quay lại Menu chính khi xem thông tin riêng tư"""
    markup = types.InlineKeyboardMarkup()
    btn_back = types.InlineKeyboardButton("⬅️ Quay Lại", callback_data="main:back")
    markup.add(btn_back)
    return markup

def get_action_keyboard(game, action_type, exclude_id=None):
    """
    Tạo danh sách nút bấm hiển thị tự động tên những người chơi còn sống.
    Dùng cho các hành động bỏ phiếu ban ngày hoặc dùng chức năng ban đêm.
    """
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    for p_id, p_info in game.players.items():
        # Bỏ qua những người đã chết
        if not p_info["alive"]:
            continue
        # Bỏ qua mục tiêu bị loại trừ (ví dụ: thợ săn tự bắn mình, hoặc bảo vệ tự bảo vệ mình)
        if exclude_id and p_id == exclude_id:
            continue
            
        btn_text = p_info["name"]
        # Nếu là Cảnh sát trưởng thì thêm biểu tượng vương miện
        if p_info.get("is_mayor", False):
            btn_text = f"👑 {btn_text}"
            
        btn = types.InlineKeyboardButton(btn_text, callback_data=f"game:{action_type}:{p_id}")
        buttons.append(btn)
        
    # Sắp xếp các nút bấm hiển thị thành lưới gọn gàng
    markup.add(*buttons)
    return markup

def witch_night_keyboard(target_name):
    """Menu đặc biệt dành riêng cho Phù Thủy khi đêm xuống"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_save = types.InlineKeyboardButton(f"🧪 Cứu {target_name}", callback_data="game:witch_save:yes")
    btn_skip_save = types.InlineKeyboardButton("❌ Không Cứu", callback_data="game:witch_save:no")
    btn_kill = types.InlineKeyboardButton("💀 Dùng Bình Độc", callback_data="game:witch_choose_kill:init")
    btn_skip_all = types.InlineKeyboardButton("💤 Bỏ Qua Lượt", callback_data="game:witch_skip:all")
    
    markup.add(btn_save, btn_skip_save)
    markup.add(btn_kill, btn_skip_all)
    return markup

def defense_judgment_keyboard():
    """Menu biểu quyết Treo cổ hay Tha bổng trong giai đoạn biện hộ ban ngày"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_guilty = types.InlineKeyboardButton("💀 Treo Cổ (Guilty)", callback_data="game:judge:guilty")
    btn_innocent = types.InlineKeyboardButton("🕊️ Tha Bổng (Innocent)", callback_data="game:judge:innocent")
    
    markup.add(btn_guilty, btn_innocent)
    return markup
