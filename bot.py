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
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    data_parts = call.data.split(":")
    prefix = data_parts[0]
    action = data_parts[1]
    
    user_id = call.from_user.id
    display_name = call.from_user.first_name
    chat_id = call.message.chat.id

    # -----------------------------------------------------------------
    # MENU CHÍNH CHAT RIÊNG (Prefix: main)
    # -----------------------------------------------------------------
    if prefix == "main":
        if action == "profile":
            p = get_profile(user_id)
            win_rate = (p['wins'] / p['matches'] * 100) if p['matches'] > 0 else 0
            text = (
                f"📊 **HỒ SƠ THÀNH VIÊN: {p['name']}**\n\n"
                f"⚔️ Số trận đã đấu: {p['matches']}\n"
                f"🏆 Số trận thắng: {p['wins']}\n"
                f"💀 Số trận thua: {p['losses']}\n"
                f"📈 Điểm số ELO: *{p['elo']}*\n"
                f"🔥 Chuỗi thắng hiện tại: {p['streak']}\n"
                f"🎯 Tỉ lệ thắng: {win_rate:.1f}%"
            )
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
        
        elif action == "leaderboard":
            rows = get_leaderboard()
            text = "🏆 **BẢNG XẾP HẠNG CAO THỦ MA SÓI** 🏆\n\n"
            for idx, r in enumerate(rows, 1):
                medal = "🥇 " if idx == 1 else "🥈 " if idx == 2 else "🥉 " if idx == 3 else f"{idx}. "
                text += f"{medal}{r[0]} — *{r[1]} ELO*\n"
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
            
        elif action == "help":
            text = "📖 **HƯỚNG DẪN LUẬT CHƠI CƠ BẢN**\n\nGame chia làm 2 phe đối lập ban ngày ban đêm..."
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
            
        elif action == "roles":
            text = "🔮 **DANH SÁCH CÁC VAI TRÒ HỖ TRỢ:**\n\nSói, Tiên tri, Bảo vệ, Phù thủy, Thợ Săn, Thằng Hề, Kẻ thâm độc..."
            bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=back_to_main_keyboard(), parse_mode="Markdown")
            
        elif action == "back":
            bot.edit_message_text("Wolf Bot sẵn sàng tương tác!", user_id, call.message.message_id, reply_markup=main_menu_keyboard())

    # -----------------------------------------------------------------
    # MENU PHÒNG CHỜ NHÓM CHUNG (Prefix: lobby)
    # -----------------------------------------------------------------
    elif prefix == "lobby":
        game = get_game(chat_id)
        
        if action == "join":
            register_player(user_id, call.from_user.username or "NoUsername", display_name)
            success, msg = game.add_player(user_id, display_name)
            bot.answer_callback_query(call.id, text=msg.replace("*", ""))
            if success:
                bot.send_message(chat_id, msg, parse_mode="Markdown")
                
        elif action == "leave":
            success, msg = game.remove_player(user_id)
            bot.answer_callback_query(call.id, text=msg.replace("*", ""))
            if success:
                bot.send_message(chat_id, msg, parse_mode="Markdown")
                
        elif action == "status":
            if not game.players:
                bot.answer_callback_query(call.id, "Phòng trống!")
                return
            status_text = "📋 **Danh sách người chơi đã sẵn sàng:**\n"
            for p_info in game.players.values():
                status_text += f"- {p_info['name']} 🟢 Sẵn sàng\n"
            bot.send_message(chat_id, status_text, parse_mode="Markdown")
            bot.answer_callback_query(call.id)
            
        elif action == "start":
            if game.is_active:
                bot.answer_callback_query(call.id, "Trận đấu đã đang diễn ra rồi!")
                return
            if len(game.players) < 4:
                bot.answer_callback_query(call.id, "⚠️ Cần tối thiểu 4 người chơi để mở trận!")
                return
                
            bot.answer_callback_query(call.id, "Khởi chạy trò chơi...")
            game.is_active = True
            game.assign_roles()
            
            # Gửi vai trò bí mật cho từng người qua chat riêng
            for p_id, p_info in game.players.items():
                try:
                    bot.send_message(p_id, f"🔮 Vai trò bí mật của bạn trong trận đấu là: **{p_info['role']}**", parse_mode="Markdown")
                except Exception:
                    bot.send_message(chat_id, f"❌ Lỗi gửi tin cho {p_info['name']}. Hãy bấm /start với bot riêng trước!")
                    
            bot.send_message(chat_id, "🏁 **TẤT CẢ ĐÃ NHẬN VAI TRÒ BÍ MẬT. TRÒ CHƠI CHÍNH THỨC BẮT ĐẦU!**")
            
            # Khởi động luồng thời gian Ban đêm (Không chặn luồng chính giúp chống đơ bot)
            threading.Thread(target=run_game_loop, args=(chat_id,)).start()

    # -----------------------------------------------------------------
    # LOGIC CHƠI GAME THỜI GIAN THỰC (Prefix: game)
    # -----------------------------------------------------------------
    elif prefix == "game":
        target_id = int(data_parts[2]) if len(data_parts) > 2 and data_parts[2].isdigit() else None
        
        # Tìm phòng chứa người chơi này (Duyệt tìm phòng tương ứng vì thao tác diễn ra ở inbox riêng)
        target_game = None
        for g in get_game.__globals__['games_manager'].values():
            if user_id in g.players:
                target_game = g
                break
                
        if not target_game:
            bot.answer_callback_query(call.id, "Không tìm thấy dữ liệu trận đấu của bạn.")
            return

        # Sói cắn người
        if action == "wolf":
            target_game.votes_night["werewolf"][user_id] = target_id
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🐺 Bạn đã chọn cắn: {t_name}", user_id, call.message.message_id)
            
            # Đồng bộ báo hiệu cho các con Sói khác cùng biết
            for wolf_id in target_game.players:
                if target_game.players[wolf_id]["role"] in ["Ma Sói", "Sói Nhỏ"] and wolf_id != user_id:
                    try: bot.send_message(wolf_id, f"👀 Sói đồng đội *{display_name}* đang chọn cắn: {t_name}", parse_mode="Markdown")
                    except: pass

        # Tiên Tri soi bài
        elif action == "seer":
            result_role = handle_seer_logic(target_game, target_id)
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🔮 Kết quả thần giao cách cảm: **{t_name}** có vai trò là *{result_role}*", user_id, call.message.message_id, parse_mode="Markdown")

        # Bảo Vệ cứu người
        elif action == "guard":
            target_game.protected_target = target_id
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🛡️ Bạn đã phủ lá chắn bảo vệ lên: {t_name}", user_id, call.message.message_id)

        # Kẻ Thâm Độc nguyền rủa
        elif action == "corrupt":
            target_game.votes_night["corrupt"] = target_id
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🦅 Bạn đã nguyền rủa thành công mục tiêu: {t_name}", user_id, call.message.message_id)

        # Phù thủy tương tác
        elif action == "witch_save":
            sub_act = data_parts[2]
            if sub_act == "yes":
                target_game.witch_action_save = True
                bot.edit_message_text("🧪 Bạn chọn dùng bình cứu sống nạn nhân.", user_id, call.message.message_id)
            else:
                bot.edit_message_text("❌ Bạn chọn giữ lại bình cứu.", user_id, call.message.message_id)
                
        elif action == "witch_choose_kill":
            bot.edit_message_text("🧪 Chọn 1 mục tiêu bạn muốn đổ độc chết đêm nay:", user_id, call.message.message_id, reply_markup=get_action_keyboard(target_game, "witch_final_kill"))
            
        elif action == "witch_final_kill":
            target_game.witch_action_kill = target_id
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"💀 Đầu độc chết: {t_name}", user_id, call.message.message_id)

        # Thợ Săn nổ súng phản sát
        elif action == "hunter_shot":
            target_game.players[target_id]["alive"] = False
            t_name = target_game.players[target_id]["name"]
            bot.edit_message_text(f"🎯 Bạn đã bóp cò kết liễu: {t_name}", user_id, call.message.message_id)
            bot.send_message(target_game.room_id, f"💥 **TIẾNG SÚNG THỢ SĂN VANG LÊN!** Trước khi gục ngã, Thợ săn đã bắn chết thêm **{t_name}**!", parse_mode="Markdown")

        # Biểu quyết treo cổ ban ngày (ở Nhóm chung)
        elif action == "voteday":
            # Thao tác vote diễn ra ở nhóm chung, target_game chính là game lấy từ chat_id nhóm
            group_game = get_game(chat_id)
            group_game.votes_day[user_id] = target_id
            t_name = group_game.players[target_id]["name"]
            bot.answer_callback_query(call.id, text=f"Bạn đã vote treo cổ {t_name}")
            bot.send_message(chat_id, f"🗳️ *{display_name}* đã bỏ phiếu đưa một nghi phạm lên đoạn đầu đài!", parse_mode="Markdown")

        # Biểu quyết trong phòng biện hộ (Treo / Tha)
        elif action == "judge":
            group_game = get_game(chat_id)
            if user_id in group_game.judgment_votes["voters"]:
                bot.answer_callback_query(call.id, "⚠️ Bạn đã biểu quyết rồi, không thể nhấn lại!")
                return
            sub_act = data_parts[2]
            group_game.judgment_votes["voters"].append(user_id)
            if sub_act == "guilty":
                group_game.judgment_votes["guilty"] += 1
                bot.answer_callback_query(call.id, "Bạn chọn Treo cổ!")
            else:
                group_game.judgment_votes["innocent"] += 1
                bot.answer_callback_query(call.id, "Bạn chọn Tha bổng!")

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
