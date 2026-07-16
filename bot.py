# bot.py
import threading
import time
from telebot import TeleBot
from config import BOT_TOKEN, TIME_LOBBY_COUNTDOWN, TIME_NIGHT, TIME_DISCUSSION
from modules.database import init_db, register_player, get_profile, get_leaderboard
from modules.game_engine import get_game
from modules.menus import main_menu_keyboard, lobby_menu_keyboard, back_to_main_keyboard, get_action_keyboard, witch_night_keyboard
from modules.night_logic import start_night_phase, handle_seer_logic
from modules.day_logic import start_day_phase, process_voting_results, execute_hanging

# Khởi tạo instance Bot
bot = TeleBot(BOT_TOKEN)

# =====================================================================
# LỆNH ĐIỀU KHIỂN CHÁT RIÊNG & NHÓM CHUNG (COMMAND HANDLERS)
# =====================================================================
@bot.message_handler(commands=['start', 'help'])
def cmd_start(message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    display_name = message.from_user.first_name

    # Luôn đăng ký/cập nhật thông tin tài khoản người dùng vào SQLite
    register_player(user_id, username, display_name)

    if message.chat.type == "private":
        welcome_private = (
            f"🐺 **CHÀO MỪNG BẠN ĐẾN VỚI BOT MA SÓI TERMUX!** 🐺\n\n"
            f"Chào mừng *{display_name}* đã tham gia hệ thống.\n"
            f"Đây là không gian tương tác riêng tư để bạn nhận vai trò bí mật, "
            f"thực hiện chức năng ban đêm và kiểm tra số liệu cá nhân của mình."
        )
        bot.send_message(chat_id, welcome_private, reply_markup=main_menu_keyboard(), parse_mode="Markdown")
    else:
        # Nếu gõ /start ở nhóm chung -> Kích hoạt menu phòng chờ
        welcome_group = (
            f"🏰 **PHÒNG CHỜ TRÒ CHƠI MA SÓI** 🏰\n\n"
            f"Nhóm: *{message.chat.title}*\n"
            f"Bấm nút dưới đây để tham gia vào trận đấu kịch tính sắp diễn ra!"
        )
        bot.send_message(chat_id, welcome_group, reply_markup=lobby_menu_keyboard(), parse_mode="Markdown")

# =====================================================================
# BỘ LỌC KIỂM SOÁT QUYỀN CHAT TRONG NHÓM (ANTI-GUEST & PHASE CONTROL)
# =====================================================================
@bot.message_handler(func=lambda message: message.chat.type != "private", content_types=['text'])
def filter_group_messages(message):
    """
    Tự động kiểm tra và xóa tin nhắn của:
    1. Người chưa tham gia game (Người lạ/Khách xem).
    2. Người chơi tham gia nhưng chat sai phase (ví dụ: chat vào ban đêm).
    """
    chat_id = message.chat.id
    user_id = message.from_user.id
    display_name = message.from_user.first_name
    
    # Lấy thông tin phòng game hiện tại
    game = get_game(chat_id)
    
    # Nếu game chưa bắt đầu (đang ở phòng chờ), ai cũng có thể chat tự do
    if not game.is_active:
        return

    # LỆNH ĐẶC BIỆT: Bỏ qua không chặn lệnh hệ thống (ví dụ lệnh /vote ban ngày)
    if message.text.startswith('/'):
        return

    # LỖI 1: Người nhắn tin không có tên trong danh sách tham gia game
    if user_id not in game.players:
        try:
            bot.delete_message(chat_id, message.message_id)
            # Gửi cảnh báo nhanh và tự xóa sau vài giây (tránh làm rác group)
            warn_msg = bot.send_message(chat_id, f"⚠️ *{display_name}*, bạn không tham gia trận đấu này! Vui lòng không nhắn tin cắt ngang cuộc chơi.", parse_mode="Markdown")
            threading.Thread(target=lambda: (time.sleep(3), bot.delete_message(chat_id, warn_msg.message_id))).start()
        except:
            pass
        return

    # LỖI 2: Người chơi đã tham gia nhưng đã bị CHẾT (Linh hồn không được phím chat)
    if not game.players[user_id]["alive"]:
        try:
            bot.delete_message(chat_id, message.message_id)
            warn_msg = bot.send_message(chat_id, f"💀 *{display_name}*, bạn đã chết! Linh hồn không thể nói chuyện với người sống.", parse_mode="Markdown")
            threading.Thread(target=lambda: (time.sleep(3), bot.delete_message(chat_id, warn_msg.message_id))).start()
        except:
            pass
        return

    # LỖI 3: Có tham gia, còn sống, nhưng CHAT SAI THỜI GIAN (Chỉ cho phép chat ở phase thảo luận)
    # Phase thảo luận ban ngày của chúng ta là: "day_discuss"
    if game.phase != "day_discuss":
        try:
            bot.delete_message(chat_id, message.message_id)
            # Chỉ cảnh báo nếu đang ở phase ban đêm u ám
            if game.phase == "night":
                warn_msg = bot.send_message(chat_id, f"🤫 *{display_name}*, trời đang tối! Mọi người đang ngủ, không được làm ồn.", parse_mode="Markdown")
                threading.Thread(target=lambda: (time.sleep(3), bot.delete_message(chat_id, warn_msg.message_id))).start()
        except:
            pass
        return

    # Nếu vượt qua hết tất cả các điều kiện trên -> Tin nhắn hợp lệ, cho phép hiển thị bình thường trong nhóm!

@bot.message_handler(commands=['vote'])
def cmd_vote(message):
    """Lệnh gọi danh sách bỏ phiếu treo cổ nhanh vào ban ngày ở nhóm chung"""
    if message.chat.type == "private":
        bot.reply_to(message, "⚠️ Lệnh này chỉ sử dụng trong nhóm chat đang diễn ra trò chơi.")
        return
        
    game = get_game(message.chat.id)
    if not game.is_active or game.phase != "day_discuss":
        bot.reply_to(message, "❌ Hiện tại không phải là thời gian bỏ phiếu treo cổ của game.")
        return
        
    if message.from_user.id not in game.players or not game.players[message.from_user.id]["alive"]:
        bot.reply_to(message, "⚠️ Bạn không tham gia hoặc đã chết, không có quyền bỏ phiếu!")
        return
        
    bot.send_message(
        message.chat.id,
        "🗳️ **Chọn người bạn nghi ngờ là Ma Sói để đưa lên đoạn đầu đài:**",
        reply_markup=get_action_keyboard(game, "voteday")
    )

# =====================================================================
# XỬ LÝ SỰ KIỆN TƯƠNG TÁC NÚT BẤM (CALLBACK QUERY HANDLERS)
# =====================================================================
# Cập nhật đoạn này trong file bot.py của bạn:
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    # Trả lời Telegram ngay lập tức để tắt trạng thái xoay vòng chờ của nút bấm (Chống spam)
    try: bot.answer_callback_query(call.id)
    except: pass

    data_parts = call.data.split(":")
    prefix = data_parts[0]
    action = data_parts[1]
    
    user_id = call.from_user.id
    display_name = call.from_user.first_name
    chat_id = call.message.chat.id

    # Lấy Target ID an toàn nếu có
    target_id = int(data_parts[2]) if len(data_parts) > 2 and data_parts[2].isdigit() else None

    # Tìm phòng chứa người chơi (Dành cho các hành động gửi từ chat riêng)
    target_game = None
    for g in games_manager.values():
        if user_id in g.players:
            target_game = g
            break

    # -----------------------------------------------------------------
    # MENU CHÍNH CHAT RIÊNG
    # -----------------------------------------------------------------
    if prefix == "main":
        if action == "profile":
            p = get_profile(user_id)
            win_rate = (p['wins'] / p['matches'] * 100) if p['matches'] > 0 else 0
            text = f"📊 **HỒ SƠ THÀNH VIÊN: {p['name']}**\n\n⚔️ Số trận: {p['matches']}\n🏆 Thắng: {p['wins']}\n📈 ELO: *{p['elo']}*\n🎯 Tỉ lệ: {win_rate:.1f}%"
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
        elif action == "leaderboard":
            rows = get_leaderboard()
            text = "🏆 **BẢNG XẾP HẠNG CAO THỦ MA SÓI** 🏆\n\n"
            for idx, r in enumerate(rows, 1): text += f"{idx}. {r[0]} — *{r[1]} ELO*\n"
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
        elif action == "back":
            bot.edit_message_text("Wolf Bot sẵn sàng tương tác!", user_id, call.message.message_id, reply_markup=main_menu_keyboard())

    # -----------------------------------------------------------------
    # MENU PHÒNG CHỜ NHÓM CHUNG
    # -----------------------------------------------------------------
    elif prefix == "lobby":
        game = get_game(chat_id)
        if action == "join":
            register_player(user_id, call.from_user.username or "NoUsername", display_name)
            success, msg = game.add_player(user_id, display_name)
            bot.send_message(chat_id, msg, parse_mode="Markdown")
        elif action == "leave":
            success, msg = game.remove_player(user_id)
            bot.send_message(chat_id, msg, parse_mode="Markdown")
        elif action == "status":
            if not game.players: return
            status_text = "📋 **Danh sách người chơi đã sẵn sàng:**\n"
            for p_info in game.players.values(): status_text += f"- {p_info['name']} 🟢\n"
            bot.send_message(chat_id, status_text, parse_mode="Markdown")
        elif action == "start":
            if game.is_active or len(game.players) < 4: return
            game.is_active = True
            game.assign_roles()
            
            # Xóa menu phòng chờ cũ trong nhóm để tránh người chơi bấm bậy khi game đã chạy
            try: bot.delete_message(chat_id, call.message.message_id)
            except: pass
            
            for p_id, p_info in game.players.items():
                try: bot.send_message(p_id, f"🔮 Vai trò bí mật của bạn là: **{p_info['role']}**", parse_mode="Markdown")
                except: bot.send_message(chat_id, f"❌ Lỗi: {p_info['name']} cần bấm /start với Bot riêng trước!")
            bot.send_message(chat_id, "🏁 **TẤT CẢ ĐÃ NHẬN VAI TRÒ BÍ MẬT. GAME BẮT ĐẦU!**")
            threading.Thread(target=run_game_loop, args=(chat_id,)).start()

    # -----------------------------------------------------------------
    # LOGIC CHƠI GAME THỜI GIAN THỰC (Bổ sung hàm khóa nút sau khi bấm)
    # -----------------------------------------------------------------
    elif prefix == "game" and target_game:
        if action == "wolf" and target_id:
            target_game.votes_night["werewolf"][user_id] = target_id
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🐺 Bạn đã chọn cắn: **{t_name}**", user_id, call.message.message_id, parse_mode="Markdown")
            for wolf_id in target_game.players:
                if target_game.players[wolf_id]["role"] in ["Ma Sói", "Sói Nhỏ", "Sói Trắng"] and wolf_id != user_id:
                    try: bot.send_message(wolf_id, f"👀 Sói đồng đội *{display_name}* chọn cắn: {t_name}", parse_mode="Markdown")
                    except: pass
        elif action == "seer" and target_id:
            result_role = handle_seer_logic(target_game, target_id)
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🔮 Kết quả soi: **{t_name}** là *{result_role}*", user_id, call.message.message_id, parse_mode="Markdown")
        elif action == "guard" and target_id:
            target_game.protected_target = target_id
            bot.edit_message_text(f"🛡️ Bạn đã phủ lá chắn bảo vệ lên: **{target_game.players[target_id]['name']}**", user_id, call.message.message_id, parse_mode="Markdown")
        elif action == "corrupt" and target_id:
            target_game.votes_night["corrupt"] = target_id
            bot.edit_message_text(f"🦅 Bạn đã nguyền rủa: **{target_game.players[target_id]['name']}**", user_id, call.message.message_id, parse_mode="Markdown")
        elif action == "witch_save":
            target_game.witch_action_save = (data_parts[2] == "yes")
            bot.edit_message_text("🧪 Quyết định của bạn về bình cứu đã được ghi nhận.", user_id, call.message.message_id)
        elif action == "witch_choose_kill":
            bot.edit_message_text("🧪 Chọn 1 mục tiêu để đổ độc:", user_id, call.message.message_id, reply_markup=get_action_keyboard(target_game, "witch_final_kill"))
        elif action == "witch_final_kill" and target_id:
            target_game.witch_action_kill = target_id
            bot.edit_message_text(f"💀 Đã đổ độc chết: **{target_game.players[target_id]['name']}**", user_id, call.message.message_id, parse_mode="Markdown")
        elif action == "hunter_shot" and target_id:
            target_game.players[target_id]["alive"] = False
            bot.edit_message_text(f"🎯 Bạn đã bắn chết: {target_game.players[target_id]['name']}", user_id, call.message.message_id)
            bot.send_message(target_game.room_id, f"💥 **THỢ SĂN PHẢN SÁT:** Trước khi chết đã bắn hạ thêm **{target_game.players[target_id]['name']}**!")
        elif action == "voteday" and target_id:
            group_game = get_game(chat_id)
            group_game.votes_day[user_id] = target_id
            # Xóa danh sách nút bấm vote cũ của người này để tránh họ đổi ý bấm liên tục phá game
            try: bot.delete_message(chat_id, call.message.message_id)
            except: pass
            bot.send_message(chat_id, f"🗳️ *{display_name}* đã bỏ phiếu treo cổ thành công!", parse_mode="Markdown")
        elif action == "judge":
            group_game = get_game(chat_id)
            if user_id in group_game.judgment_votes["voters"]: return
            group_game.judgment_votes["voters"].append(user_id)
            if data_parts[2] == "guilty": group_game.judgment_votes["guilty"] += 1
            else: group_game.judgment_votes["innocent"] += 1

# =====================================================================
# LUỒNG ĐỒNG HỒ ĐẾM NGƯỢC AN TOÀN CHỐNG ĐƠ MÁY (THREADING ENGINE)
# =====================================================================
def run_game_loop(room_id):
    """Vòng lặp thời gian điều khiển tiến trình trò chơi tự động"""
    game = get_game(room_id)
    
    while game.is_active:
        # Phase 1: Ban đêm
        start_night_phase(bot, game)
        
        # Tạo logic đặc biệt kích hoạt trễ riêng cho Phù Thủy sau 20 giây khi Sói đã chọn mục tiêu
        time.sleep(20)
        for p_id, p_info in game.players.items():
            if p_info["alive"] and p_info["role"] == "Phù Thủy" and game.witch_has_save:
                # Tìm nạn nhân tạm thời của sói để báo cho Phù Thủy biết
                wolf_votes = list(game.votes_night.get("werewolf", {}).values())
                v_name = game.players[wolf_votes[0]]["name"] if wolf_votes else "Không ai"
                try: bot.send_message(p_id, f"🧪 Đêm nay, Sói dự định cắn *{v_name}*. Bạn muốn làm gì?", reply_markup=witch_night_keyboard(v_name), parse_mode="Markdown")
                except: pass
                
        # Chờ nốt thời gian còn lại của ban đêm
        time.sleep(TIME_NIGHT - 20)
        
        # Phase 2: Chuyển sang Ban ngày công bố kết quả
        start_day_phase(bot, game)
        if not game.is_active: break # Dừng luồng nếu có phe thắng cuộc ngay buổi sáng
        
        # Đợi hết thời gian thảo luận tự do ban ngày
        time.sleep(TIME_DISCUSSION)
        
        # Phase 3: Tổng kết phiếu bầu thảo luận ban ngày để đưa vào phòng biện hộ
        process_voting_results(bot, game)
        if game.phase != "day_defense":
            # Nếu không ai bị bầu -> Quay lại chu kỳ đêm tiếp theo tự động
            continue
            
        # Nếu có người lọt vào phòng biện hộ, chờ thời gian biểu quyết Treo / Tha
        time.sleep(20)
        execute_hanging(bot, game)
        if not game.is_active: break # Dừng luồng nếu game kết thúc sau khi treo cổ

# =====================================================================
# KHỞI CHẠY HỆ THỐNG
# =====================================================================
if __name__ == "__main__":
    print("🗄️ Khởi tạo cấu trúc cơ sở dữ liệu SQLite...")
    init_db()
    print("🐺 Bot Game Ma Sói Đa Vai Trò đã kích hoạt thành công trên Termux!")
    print("📢 Đang lắng nghe sự kiện từ Telegram... (Nhấn Ctrl + C để dừng)")
    bot.infinity_polling()
