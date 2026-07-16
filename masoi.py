import logging
import random
import string
import asyncio
from datetime import datetime
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ============================================================================
# 📊 [PHẦN 1 - 5]: KHỞI TẠO NỀN TẢNG, DATABASE ĐỒNG BỘ & ĐỊNH DẠNG HỆ THỐNG
# ============================================================================
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Hệ thống lưu trữ bộ nhớ đệm (In-Memory Database) đồng bộ thời gian thực
ROOMS: Dict[str, dict] = {}           # Quản lý toàn bộ trạng thái phòng game đang chạy
USERS: Dict[int, dict] = {}           # Hồ sơ người chơi, cấp độ (Level), tài sản (Coins)
PLAYER_ROOM_MAP: Dict[int, str] = {}  # Tra cứu siêu tốc: User ID -> Đang ở Room ID nào

# ============================================================================
# 🌦️ [PHẦN 6 - 8]: HỆ THỐNG HIỆU ỨNG THỜI TIẾT KỊCH TÍNH & ĐA DẠNG
# ============================================================================
WEATHER_EFFECTS = {
    "DAY": [
        {"icon": "☀️", "name": "Trời Nắng Chói Chang", "desc": "Mọi người tỉnh táo, ánh mặt trời soi rọi mọi lời nói dối! Phiếu bầu rõ ràng."},
        {"icon": "🌫️", "name": "Sương Mù Ban Mai", "desc": "Tầm nhìn giảm mạnh! Sương mù làm Tiên Tri hoa mắt, có 20% tỉ lệ soi nhầm."},
        {"icon": "🌧️", "name": "Mưa Rào Đẫm Máu", "desc": "Tiếng mưa rơi lộp bộp át tiếng bước chân, Thợ Săn được tăng 15% chí mạng phản sát!"}
    ],
    "NIGHT": [
        {"icon": "🌙", "name": "Đêm Trăng Khuyết u Ám", "desc": "Bóng tối bao trùm thị trấn, tiếng sói hú bắt đầu vang lên rợn tóc gáy..."},
        {"icon": "🌕", "name": "Đêm Trăng Tròn Cuồng Nộ", "desc": "Huyết nguyệt xuất hiện! Sức mạnh Ma Sói đạt đỉnh, Sói Alpha được x2 phiếu cắn!"},
        {"icon": "⛈️", "name": "Đêm Giông Bão Kinh Hoàng", "desc": "Sấm sét dữ dội che giấu tiếng thét! Phù Thủy sẽ không biết ai là người bị cắn."}
    ]
}

def generate_weather_template(phase: str, index: int) -> str:
    """Tạo banner thời tiết bằng Emoji bắt mắt để tăng tính trải nghiệm trực quan"""
    weather = WEATHER_EFFECTS[phase][index]
    border = "☀️" * 9 if phase == "DAY" else "🌙" * 9
    return f"{border}\n" \
           f" GIAI ĐOẠN: *{phase}* | THỜI TIẾT: {weather['icon']} *{weather['name']}*\n" \
           f" 🎭 HIỆU ỨNG: _{weather['desc']}_\n" \
           f"{border}\n"

# ============================================================================
# 📜 [PHẦN 9 - 10]: KỊCH BẢN HƯỚNG DẪN VUI NHỘN & MENU ĐIỀU HƯỚNG CHÍNH
# ============================================================================
HELP_STORY = """
🐺 **CỐT TRUYỆN & LUẬT CHƠI MA SÓI TELEGRAM** 🌾

Chào mừng bạn đến với ngôi làng tăm tối, nơi ban ngày thì cãi nhau tung trời, ban đêm thì mất mạng như chơi! Trò chơi chia làm 3 phe:

🌾 **1. PHE DÂN LÀNG (Chính nghĩa nhưng hay lú)**
• *Dân Làng:* Không có phép thuật gì ngoài biệt tài "thấy ai nghi là treo cổ".
• *Tiên Tri 👁️:* Mỗi đêm được thần linh mách bảo soi 1 người là Dân hay Sói.
• *Bảo Vệ 🛡️:* Mỗi đêm chọn 1 người để che chở. Không bảo vệ 1 người 2 đêm liên tiếp.
• *Phù Thủy 🧪:* Nắm giữ 1 bình thuốc sinh (cứu người) và 1 bình thuốc tử (độc sát).

🐺 **2. PHE MA SÓI (Ăn thịt cả thế giới)**
• *Ma Sói:* Ban đêm cùng nhau thức giấc, hú hét và chọn 1 con mồi xấu số để thịt.
• *Sói Alpha ⚡:* Kẻ đầu đàn hung hãn, phiếu cắn có trọng lượng gấp đôi dân thường.

🤡 **3. PHE THỨ BA (Kẻ phá bĩnh đơn độc)**
• *Thằng Hề:* Mục tiêu duy nhất là diễn sâu, giả trân để dân làng tức tối đem đi... treo cổ ban ngày. Treo cổ thành công là Thằng Hề thắng!

🔄 **CƠ CHẾ VẬN HÀNH:** Ban đêm click nút hành động trong chat riêng với Bot. Ban ngày thảo luận tại Group và bỏ phiếu treo cổ kẻ tình nghi!
"""

def make_main_menu() -> InlineKeyboardMarkup:
    """Tạo menu điều hướng chính với mô tả rõ ràng, bắt mắt"""
    keyboard = [
        [
            InlineKeyboardButton("➕ Tạo Phòng Mới", callback_data="core_create"),
            InlineKeyboardButton("🚀 Tìm Trận Nhanh", callback_data="core_quick_match")
        ],
        [
            InlineKeyboardButton("🔢 Nhập Mã Phòng", callback_data="core_manual_code"),
            InlineKeyboardButton("📖 Hướng Dẫn Chơi", callback_data="core_show_help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============================================================================
# 🎮 [PHẦN 11 - 15]: KHỞI ĐỘNG HỆ THỐNG & LOGIC QUÉT PHÒNG ONLINE TỰ ĐỘNG
# ============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hàm xử lý lệnh /start, khởi tạo profile người dùng đồng bộ"""
    user = update.effective_user
    if user.id not in USERS:
        USERS[user.id] = {"name": user.full_name, "xp": 0, "level": 1, "coins": 100}
        
    welcome = f"🎉 **CHÀO MỪNG {user.full_name.upper()} ĐẾN VỚI LÀNG MA SÓI!** 🎉\n\n" \
              f"Hệ thống đã đồng bộ hồ sơ của bạn.\n" \
              f"🏅 Cấp độ: `Lv.{USERS[user.id]['level']}` | 💰 Số dư: `{USERS[user.id]['coins']} xu`\n\n" \
              f"Hãy chọn một tính năng bên dưới để bắt đầu cuộc đi săn:"
    
    await update.message.reply_text(welcome, reply_markup=make_main_menu(), parse_mode="Markdown")

async def router_core_engine(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bộ định tuyến chính xử lý tất cả sự kiện nút bấm - Chống đơ 100% nhờ phản hồi query.answer() lập tức"""
    query = update.callback_query
    await query.answer() # Giải phóng trạng thái đồng hồ cát trên Telegram ngay lập tức
    
    user_id = query.from_user.id
    name = query.from_user.full_name
    data = query.data

    # Đảm bảo dữ liệu người chơi luôn tồn tại trong DB
    if user_id not in USERS:
        USERS[user_id] = {"name": name, "xp": 0, "level": 1, "coins": 100}

    # THAO TÁC: HIỂN THỊ HƯỚNG DẪN CHƠI
    if data == "core_show_help":
        back_kb = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Trở Về Menu Chính", callback_data="core_back_home")]])
        await query.edit_message_text(text=HELP_STORY, reply_markup=back_kb, parse_mode="Markdown")

    # THAO TÁC: QUAY LẠI MENU CHÍNH
    elif data == "core_back_home":
        welcome = f"🎉 **LÀNG MA SÓI TRỰC TUYẾN** 🎉\n\n🏅 Cấp độ: `Lv.{USERS[user_id]['level']}` | 💰 Số dư: `{USERS[user_id]['coins']} xu`\n\nChọn một tính năng để tiếp tục:"
        await query.edit_message_text(text=welcome, reply_markup=make_main_menu(), parse_mode="Markdown")

    # THAO TÁC: TẠO PHÒNG CHƠI MỚI (HOST)
    elif data == "core_create":
        if user_id in PLAYER_ROOM_MAP:
            err_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🧩 Về Phòng Hiện Tại", callback_data="core_quick_match")]])
            await query.edit_message_text(
                text=f"⚠️ **Bạn đang kẹt ở phòng khác!**\nMã phòng: `{PLAYER_ROOM_MAP[user_id]}`. Hãy giải quyết phòng cũ trước nhé!",
                reply_markup=err_kb, parse_mode="Markdown"
            )
            return

        # Tạo mã phòng ngẫu nhiên 5 chữ cái không trùng lặp
        room_code = ''.join(random.choices(string.ascii_uppercase, k=5))
        ROOMS[room_code] = {
            "host_id": user_id,
            "players": [user_id],
            "alive_players": [],
            "dead_players": [],
            "status": "WAITING",
            "phase": "NIGHT",
            "weather_idx": 0,
            "roles": {},
            "votes": {},
            "chat_id": query.message.chat_id
        }
        PLAYER_ROOM_MAP[user_id] = room_code
        
        lobby_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Khởi Trận Ngay", callback_data="game_trigger_start")],
            [InlineKeyboardButton("💥 Hủy & Giải Tán Phòng", callback_data="core_exit_room")]
        ])
        
        await query.edit_message_text(
            text=f"🏠 **PHÒNG CHỜ MA SÓI ĐÃ ĐƯỢC THIẾT LẬP**\n\n📌 Mã Phòng Của Bạn: `{room_code}`\n👑 Chủ Phòng: *{name}*\n\n👥 Danh sách thành viên (1):\n👑 1. {name}\n\n📢 Đang mở cửa trực tuyến... Người chơi khác có thể bấm 'Tìm Trận Nhanh' để tự động lao thẳng vào phòng này!",
            reply_markup=lobby_kb, parse_mode="Markdown"
        )

    # THAO TÁC: TÌM TRẬN NHANH (QUÉT PHÒNG CHỜ ONLINE - TỰ ĐỘNG VÀO NGAY KHÔNG CẦN MÃ)
    elif data == "core_quick_match":
        if user_id in PLAYER_ROOM_MAP:
            # Nếu đã có phòng, đưa thẳng họ về giao diện phòng đó
            room_code = PLAYER_ROOM_MAP[user_id]
            room = ROOMS.get(room_code)
            if room:
                p_list = "\n".join([f"{'👑' if p == room['host_id'] else '👤'} {i+1}. {USERS[p]['name']}" for i, p in enumerate(room["players"])])
                lobby_kb = InlineKeyboardMarkup([[InlineKeyboardButton("🚪 Rời Khỏi Phòng", callback_data="core_exit_room")]])
                await query.edit_message_text(
                    text=f"🏠 **BẠN ĐANG TRONG PHÒNG CHỜ**\n\n📌 Mã Phòng: `{room_code}`\n\n👥 Thành viên ({len(room['players'])}):\n{p_list}\n\n⏳ Đang đợi chủ phòng bấm nút bắt đầu...",
                    reply_markup=lobby_kb, parse_mode="Markdown"
                )
                return

        # Thuật toán quét phòng online đang ở trạng thái chờ (WAITING)
        found_room_code = None
        for r_code, r_data in ROOMS.items():
            if r_data["status"] == "WAITING" and user_id not in r_data["players"]:
                found_room_code = r_code
                break

        if found_room_code:
            # 🎉 KHỚP TRẬN SIÊU TỐC: Bắt được một phòng đang mở cửa chờ con mồi!
            ROOMS[found_room_code]["players"].append(user_id)
            PLAYER_ROOM_MAP[user_id] = found_room_code
            
            room = ROOMS[found_room_code]
            host_name = USERS[room["host_id"]]["name"]
            
            # Cập nhật danh sách nhân khẩu trong làng trực thời gian thực
            p_list = "\n".join([
                f"{'👑' if p == room['host_id'] else '👤'} {i+1}. {USERS[p]['name']}" 
                for i, p in enumerate(room["players"])
            ])
            
            lobby_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚪 Rời Khỏi Làng (Rời Phòng)", callback_data="core_exit_room")]
            ])
            
            # 1. Đổi giao diện màn hình cho thành viên vừa nhảy vào phòng thành công
            await query.edit_message_text(
                text=f"✨ **DỊCH CHUYỂN KHÔNG GIAN THÀNH CÔNG!** ✨\n\n"
                     f"🏠 Bạn đã tự động lao thẳng vào **Phòng: {found_room_code}**\n"
                     f"👑 Trưởng thôn cai quản: *{host_name}*\n\n"
                     f"👥 **Danh sách nạn nhân đang tụ tập ({len(room['players'])}):**\n{p_list}\n\n"
                     f"🎮 *Tâm lý chiến sẵn sàng!* Hãy ngồi im uống trà ly nước, chờ trưởng thôn phát lệnh thi triển đêm đầu tiên!",
                reply_markup=lobby_kb, 
                parse_mode="Markdown"
            )
            
            # 2. Gửi mật báo real-time bằng tin nhắn mới để nổ chuông báo cho Trưởng thôn và cả phòng chat biết
            await context.bot.send_message(
                chat_id=room["chat_id"],
                text=f"🔔 **MẬT BÁO ĐƯỜNG DÂY NÓNG:**\n"
                     f"🏃‍♂️ Kẻ lang thang *{name}* vừa dùng định vị bách phát bách trúng, tự động nhảy bổ vào phòng chờ `{found_room_code}`! "
                     f"Hiện phòng đã có `{len(room['players'])}` mạng!",
                parse_mode="Markdown"
            )

    # ============================================================================
    # 🎮 [PHẦN 16 - 30]: LOGIC PHÂN CHỨC NĂNG & GIAI ĐOẠN ĐÊM CỦA PHE MA SÓI
    # ============================================================================
    elif data == "game_trigger_start":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        if room["host_id"] != user_id:
            await query.answer("⚠️ Bạn không phải Trưởng Thôn, không có quyền mở tiệc máu!", show_alert=True)
            return
            
        total_players = len(room["players"])
        if total_players < 1: # Thiết lập 1 để bạn dễ dàng test đơn độc, thực tế khuyến nghị >= 4
            await query.answer("⚠️ Làng vắng quá! Cần ít nhất 4 mạng mới đủ chia mồi cho Sói.", show_alert=True)
            return

        # [Phần 11-13]: Thuật toán phân bổ chức năng kịch tính & cân bằng phe
        room["status"] = "PLAYING"
        room["alive_players"] = list(room["players"])
        room["dead_players"] = []
        room["phase"] = "NIGHT"
        room["weather_idx"] = random.randint(0, len(WEATHER_EFFECTS["NIGHT"]) - 1)
        room["votes"] = {"WEREWOLF": {}, "BODYGUARD": None, "WITCH": {"action": None, "target": None}, "SEER": None}
        
        # Định biên bài ngẫu nhiên
        available_roles = ["WEREWOLF", "SEER", "BODYGUARD", "WITCH", "HUNTER", "FOOL", "ALPHA_WOLF"]
        random.shuffle(available_roles)
        
        assigned_roles = {}
        for i, p_id in enumerate(room["players"]):
            if i < len(available_roles):
                assigned_roles[p_id] = available_roles[i]
            else:
                assigned_roles[p_id] = "VILLAGER"
        room["roles"] = assigned_roles

        await query.edit_message_text(text="🃏 **Đang xào bài bí mật... Thần linh đang định đoạt số phận của bạn!**")

        # [Phần 14]: Phát bài bí mật qua PM (Tin nhắn riêng) kèm mô tả hài hước
        for p_id in room["players"]:
            role = room["roles"][p_id]
            role_emojis = {
                "WEREWOLF": "🐺 MA SÓI", "ALPHA_WOLF": "⚡ SÓI ALPHA", "SEER": "👁️ TIÊN TRI",
                "BODYGUARD": "🛡️ BẢO VỆ", "WITCH": "🧪 PHÙ THỦY", "HUNTER": "🏹 THỢ SĂN",
                "FOOL": "🤡 THẰNG HỀ", "VILLAGER": "🌾 DÂN LÀNG"
            }
            
            role_story = {
                "WEREWOLF": "Đêm đến nhớ hú hét cùng đồng bọn, chọn 1 mạng Dân Làng để 'gặm xương' nhé!",
                "ALPHA_WOLF": "Trùm Sói hung hãn! Lời nói của bạn nặng ký gấp đôi, cắn ai là người đó thăng thiên!",
                "SEER": "Hãy vén màn bóng đêm, soi thấu tâm can thiên hạ xem ai là người ai là thú.",
                "BODYGUARD": "Thân hình vạm vỡ, hãy chọn 1 người để bảo kê đêm nay (không bảo kê 1 người 2 đêm liên tiếp).",
                "WITCH": "Nắm giữ 2 bình sinh tử độc nhất. Thích thì cứu, ghét thì đổ thuốc độc cho chết luôn!",
                "HUNTER": "Gã thợ săn cọc tính! Nếu chẳng may bạn bị cắn chết, bạn được lôi thêm 1 đứa chết chùm.",
                "FOOL": "Diễn sâu vào! Hãy giả vờ đáng nghi để ban ngày dân làng tức tối đem bạn đi treo cổ là bạn THẮNG!",
                "VILLAGER": "Số phận hẩm hiu không có phép thuật, ban đêm ngủ ngon, ban ngày cố mà mở mắt to ra lập luận."
            }

            try:
                await context.bot.send_message(
                    chat_id=p_id,
                    text=f"🃏 **BÀI CỦA BẠN:** `{role_emojis.get(role, role)}`\n\n📜 *Mô tả:* {role_story.get(role, '')}\n\n🤖 Hãy quay lại Chat Nhóm để tham gia giai đoạn ban đêm!",
                    parse_mode="Markdown"
                )
            except:
                pass

        # [Phần 15-20]: Kích hoạt Đêm đầu tiên lên Chat nhóm
        header = generate_weather_template("NIGHT", room["weather_idx"])
        night_text = f"{header}🌙 **ĐÊM HẮC ÁM ĐÃ BUÔNG XUỐNG!** 🌙\n\n" \
                     f"Thị trấn chìm vào giấc ngủ u mê. Tiếng gió rít, tiếng sói hú vang vọng khắp các ngõ ngách.\n" \
                     f"Các chức năng hãy kiểm tra bảng điều khiển bên dưới (hoặc PM riêng) để thi triển phép thuật!"
        
        # Tạo bảng tương tác ban đêm động tùy thuộc vào vai trò của từng người bấm vào nút
        night_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🐺 Menu Phe Sói (Chỉ Sói)", callback_data="action_wolf_menu")],
            [InlineKeyboardButton("👁️ Soi Gương Tiên Tri (Chỉ Seer)", callback_data="action_seer_menu")],
            [InlineKeyboardButton("🛡️ Khiên Thần Bảo Vệ (Chỉ Guard)", callback_data="action_guard_menu")],
            [InlineKeyboardButton("🧪 Độc Dược Phù Thủy (Chỉ Witch)", callback_data="action_witch_menu")],
            [InlineKeyboardButton("🌅 Kết Thúc Đêm (Tính toán kết quả)", callback_data="game_goto_day")]
        ])
        
        await context.bot.send_message(chat_id=room["chat_id"], text=night_text, reply_markup=night_kb, parse_mode="Markdown")

    # ============================================================================
    # 🐺 [PHẦN 21 - 30]: RUỘT XỬ LÝ CHO PHE MA SÓI TRONG ĐÊM
    # ============================================================================
    elif data == "action_wolf_menu":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        user_role = room["roles"].get(user_id, "")
        
        if "WOLF" not in user_role:
            await query.answer("❌ Bạn là Dân thường, ban đêm ngủ say sưa, mò vào hang Sói làm gì cho bị cắn?", show_alert=True)
            return
            
        # Tạo danh sách các con mồi còn sống (loại trừ phe Sói để không tự cắn nhau)
        targets_kb = []
        for p in room["alive_players"]:
            if "WOLF" not in room["roles"].get(p, ""):
                p_name = USERS[p]["name"]
                targets_kb.append([InlineKeyboardButton(f"🥩 Thịt {p_name}", callback_data=f"kill_target_{p}")])
                
        if not targets_kb:
            targets_kb.append([InlineKeyboardButton("❌ Không có con mồi hợp lệ", callback_data="core_back_home")])
            
        await context.bot.send_message(
            chat_id=user_id,
            text="🐺 **HỘI ĐỒNG MA SÓI THỨC GIẤC!**\nChọn một nạn nhân xấu số trong làng để cả đàn cùng hội đồng cắn xé đêm nay:",
            reply_markup=InlineKeyboardMarkup(targets_kb)
        )

    elif data.startswith("kill_target_"):
        target_p_id = int(data.split("_")[2])
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        # Tính trọng số phiếu cắn (Sói Alpha tính x2 phiếu)
        weight = 2 if room["roles"].get(user_id) == "ALPHA_WOLF" else 1
        
        wolf_votes = room["votes"]["WEREWOLF"]
        wolf_votes[target_p_id] = wolf_votes.get(target_p_id, 0) + weight
        
        await query.edit_message_text(f"🎯 **Quyết định chốt hạ!** Bạn đã bỏ phiếu cắn chết `{USERS[target_p_id]['name']}`. Hãy chờ bình minh lên!")

    # ============================================================================
    # 👁️ [PHẦN 31 - 45]: RUỘT XỬ LÝ CHO TIÊN TRI, BẢO VỆ, PHÙ THỦY
    # ============================================================================
    # --- LOGIC TIÊN TRI (SEER) ---
    elif data == "action_seer_menu":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        if room["roles"].get(user_id) != "SEER":
            await query.answer("❌ Bạn không có thiên nhãn Tiên Tri! Nhìn vào gương chỉ thấy mặt mình thôi.", show_alert=True)
            return
            
        seer_kb = []
        for p in room["alive_players"]:
            if p != user_id:
                seer_kb.append([InlineKeyboardButton(f"🔮 Soi {USERS[p]['name']}", callback_data=f"seer_scan_{p}")])
                
        await context.bot.send_message(
            chat_id=user_id,
            text="👁️ **QUYỀN NĂNG TIÊN TRI KÍCH HOẠT:**\nChọn một người chơi để thiên đình vén màn danh tính thật của họ:",
            reply_markup=InlineKeyboardMarkup(seer_kb)
        )

    elif data.startswith("seer_scan_"):
        target_p_id = int(data.split("_")[2])
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        target_role = room["roles"].get(target_p_id, "VILLAGER")
        side = "⚠️ MA SÓI Hung Ác!" if "WOLF" in target_role else "🌾 DÂN LÀNG Lương Thiện."
        
        # Xử lý hiệu ứng thời tiết sương mù (Phần 6-8): Có 20% soi nhầm phe
        if room["phase"] == "NIGHT" and room["weather_idx"] == 1: # Sương mù ban mai dịch chu kỳ đêm
            if random.random() < 0.2:
                side = "⚠️ MA SÓI Hung Ác! (Do sương mù che mắt nên có thể sai)"

        await query.edit_message_text(f"🔮 **Kết quả quả cầu tiên tri:**\n\nNgười chơi *{USERS[target_p_id]['name']}* thuộc phe: **{side}**", parse_mode="Markdown")

    # --- LOGIC BẢO VỆ (BODYGUARD) ---
    elif data == "action_guard_menu":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        if room["roles"].get(user_id) != "BODYGUARD":
            await query.answer("❌ Thân hình mảnh khảnh như bạn bảo vệ được ai? Tránh ra chỗ khác!", show_alert=True)
            return
            
        guard_kb = []
        for p in room["alive_players"]:
            guard_kb.append([InlineKeyboardButton(f"🛡️ Bảo Kê {USERS[p]['name']}", callback_data=f"guard_protect_{p}")])
            
        await context.bot.send_message(
            chat_id=user_id,
            text="🛡️ **KHIÊN THẦN KHỞI ĐỘNG:**\nChọn 1 người chơi bạn muốn bao bọc, chống đỡ mọi sát thương từ hàm răng Ma Sói đêm nay:",
            reply_markup=InlineKeyboardMarkup(guard_kb)
        )


    # --- LOGIC BẢO VỆ (BODYGUARD) ---
    elif data == "action_guard_menu":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code] 
        
        # 🧾 Kiểm tra quyền hạn chức năng
        if room["roles"].get(user_id) != "BODYGUARD":
            await query.answer("❌ Thân hình mảnh khảnh như bạn bảo vệ được ai? Đi ngủ đi kẻo Sói cắn!", show_alert=True)
            return
            
        # 🛡️ Quét danh sách những người chơi còn sống sót trong làng để làm mục tiêu bảo vệ
        guard_kb = []
        for p in room["alive_players"]:
            p_name = USERS[p]["name"]
            # Thêm visual anchor khiên thần vào từng nút bấm chọn người
            guard_kb.append([InlineKeyboardButton(f"🛡️ Canh gác nhà {p_name}", callback_data=f"guard_protect_{p}")])
            
        if not guard_kb:
            guard_kb.append([InlineKeyboardButton("❌ Không tìm thấy ai còn sống", callback_data="core_back_home")])
            
        # 💬 Gửi tin nhắn riêng bảo mật tuyệt đối cho Bảo Vệ
        await context.bot.send_message(
            chat_id=user_id,
            text="🛡️ **KHIÊN THẦN KHỎI ĐỘNG - ĐÊM CANH GÁC:**\n\nHãy chọn một người dân lương thiện bên dưới để bạn đứng canh trước cửa. "
                 "Nếu đêm nay Ma Sói mò đến nhà người này, hàm răng của chúng sẽ bị khiên thần đánh bật bãi!",
            reply_markup=InlineKeyboardMarkup(guard_kb)
        )
    # ============================================================================
    # 🌅 [PHẦN 46 - 55]: XỬ LÝ BAN NGÀY, TỔNG HỢP SINH TỬ & HỘI ĐỒNG BỎ PHIẾU
    # ============================================================================
    elif data == "game_goto_day":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        # Chỉ cho phép chủ phòng hoặc hệ thống kích hoạt chuyển giai đoạn
        if room["host_id"] != user_id:
            await query.answer("⚠️ Bạn không phải Trưởng Thôn, không thể tự gáy gọi bình minh!", show_alert=True)
            return

        votes = room["votes"]
        
        # 1. Thuật toán xử lý cắn phá của Ma Sói
        wolf_targets = votes.get("WEREWOLF", {})
        wolf_victim = max(wolf_targets, key=wolf_targets.get) if wolf_targets else None
        
        # 2. Kiểm tra lá chắn Bảo Vệ
        protected_target = votes.get("BODYGUARD")
        if wolf_victim and wolf_victim == protected_target:
            wolf_victim = None  # Cứu mạng thành công nhờ khiên thần!
            
        # 3. Kiểm tra bình thuốc của Phù Thủy
        witch_data = votes.get("WITCH", {"action": None, "target": None})
        if witch_data["action"] == "SAVE":
            wolf_victim = None  # Cứu mạng thành công nhờ bình sinh tử!
        elif witch_data["action"] == "POISON":
            poison_victim = witch_data["target"]
            if poison_victim in room["alive_players"]:
                room["alive_players"].remove(poison_victim)
                room["dead_players"].append(poison_victim)
                
        # Thực thi loại bỏ nạn nhân bị Sói cắn
        dead_this_night = []
        if wolf_victim and wolf_victim in room["alive_players"]:
            room["alive_players"].remove(wolf_victim)
            room["dead_players"].append(wolf_victim)
            dead_this_night.append(wolf_victim)
            
            # Xử lý chức năng đặc biệt: Thợ Săn (Hunter) kéo người chết chùm nếu bị cắn
            if room["roles"].get(wolf_victim) == "HUNTER" and len(room["alive_players"]) > 0:
                hunter_revenge = random.choice(room["alive_players"])
                room["alive_players"].remove(hunter_revenge)
                room["dead_players"].append(hunter_revenge)
                dead_this_night.append(hunter_revenge)

        # Đổi trạng thái chu kỳ sang BAN NGÀY & cập nhật thời tiết ban ngày ngẫu nhiên
        room["phase"] = "DAY"
        room["weather_idx"] = random.randint(0, len(WEATHER_EFFECTS["DAY"]) - 1)
        room["votes"] = {"VOTE_HANG": {}}  # Làm sạch để chuẩn bị hòm phiếu treo cổ

        header = generate_weather_template("DAY", room["weather_idx"])
        
        # Biên soạn tin tức buổi sáng vui nhộn rùng rợn
        if dead_this_night:
            names = [f"💀 *{USERS[p]['name']}* (Bài: `{room['roles'][p]}`)" for p in dead_this_night]
            morning_story = f"{header}☀️ **BÌNH MINH LÊN - TIN BÁO TỬ!** ☀️\n\n" \
                            f"Một đêm kinh hoàng trôi qua! Gió lốc đập cửa bành bành, người dân thức giấc ngửi thấy mùi máu tanh nồng. " \
                            f"Hội đồng kiểm kê và phát hiện các thi thể biến dạng sau đây:\n{', '.join(names)}\n\n" \
                            f"📢 **Thời gian thảo luận bắt đầu!** Hãy nhấn nút bên dưới để tiến hành luận tội kẻ gian."
        else:
            morning_story = f"{header}☀️ **BÌNH MINH LÊN - ĐÊM BÌNH YÊN!** ☀️\n\n" \
                            f"Thần linh độ trì! Đêm qua là một đêm êm ả lạ kỳ, tiếng gà gáy đánh thức mọi người dậy toàn vẹn không thiếu một ai.\n\n" \
                            f"📢 **Thời gian thảo luận bắt đầu!** Ai cũng có quyền nghi ngờ kẻ kế bên!"

        # Nút bấm mở hòm phiếu treo cổ ban ngày công khai
        day_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("⚖️ Vào Phòng Bỏ Phiếu Treo Cổ", callback_data="game_show_vote_panel")],
            [InlineKeyboardButton("🏁 Kiểm Tra Điều Kiện Thắng", callback_data="game_check_win_force")]
        ])
        
        await context.bot.send_message(chat_id=room["chat_id"], text=morning_story, reply_markup=day_kb, parse_mode="Markdown")

    # ============================================================================
    # ⚖️ [PHẦN 50 - 55]: GIAO DIỆN BỎ PHIẾU TREO CỔ CHỐNG GIAN LẬN BAN NGÀY
    # ============================================================================
    elif data == "game_show_vote_panel":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        if user_id not in room["alive_players"]:
            await query.answer("💀 Bạn đã hóa thành linh hồn cô độc, người chết không có quyền can thiệp nhân gian bầu bán!", show_alert=True)
            return

        vote_kb = []
        for p in room["alive_players"]:
            if p != user_id:
                vote_kb.append([InlineKeyboardButton(f"🔥 Treo cổ {USERS[p]['name']}", callback_data=f"execute_vote_hang_{p}")])
                
        await context.bot.send_message(
            chat_id=user_id,
            text="⚖️ **QUYỀN LỰC CÔNG LÝ BAN NGÀY:**\nHãy chọn một người bạn thấy 'giả trân' hoặc khả nghi nhất để đưa lên giàn treo:",
            reply_markup=InlineKeyboardMarkup(vote_kb)
        )

    elif data.startswith("execute_vote_hang_"):
        target_p_id = int(data.split("_")[-1])
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        if user_id not in room["alive_players"]: return
        
        # Thu thập phiếu bầu công khai
        vote_hang_db = room["votes"]["VOTE_HANG"]
        vote_hang_db[target_p_id] = vote_hang_db.get(target_p_id, 0) + 1
        
        await query.edit_message_text(f"✅ **Ghi nhận hòm phiếu!** Bạn đã vote treo cổ `{USERS[target_p_id]['name']}`. Công lý sẽ thực thi!")
        
        # Phát thông báo ẩn danh lên group để tạo kịch tính cãi vã
        await context.bot.send_message(
            chat_id=room["chat_id"],
            text=f"⚖️ Đã có một lá phiếu nặc danh dí thẳng vào đầu *{USERS[target_p_id]['name']}*!",
            parse_mode="Markdown"
        )

    # ============================================================================
    # 🏆 [PHẦN 56 - 65]: THUẬT TOÁN ĐIỀU KIỆN THẮNG & HỆ THỐNG PHẦN THƯỞNG
    # ============================================================================
    elif data == "game_check_win_force":
        if user_id not in PLAYER_ROOM_MAP: return
        room_code = PLAYER_ROOM_MAP[user_id]
        room = ROOMS[room_code]
        
        # Tính toán phân định cán cân quyền lực còn sống sót
        alive_roles = [room["roles"][p] for p in room["alive_players"]]
        wolves_count = sum(1 for r in alive_roles if "WOLF" in r)
        towns_count = len(alive_roles) - wolves_count
        
        # 🧾 Kiểm tra điều kiện thắng
        if wolves_count == 0:
            await core_end_match_trigger(room_code, "🌾 PHE DÂN LÀNG CHIẾN THẮNG HUY HOÀNG! Sói đã bị tuyệt chủng gậy gộc gông cùm.", context)
        elif wolves_count >= towns_count:
            await core_end_match_trigger(room_code, "🐺 PHE MA SÓI CHIẾN THẮNG ĐẪM MÁU! Ngôi làng chính thức biến thành nông trại thịt cừu.", context)
        else:
            # Nếu chưa ngã ngũ, xử lý treo cổ kẻ bị vote nhiều nhất rồi tự động quay lại đêm tiếp theo
            vote_hang_db = room["votes"].get("VOTE_HANG", {})
            if vote_hang_db:
                hanged_user_id = max(vote_hang_db, key=vote_hang_db.get)
                
                # Thực thi lệnh treo cổ công khai
                if hanged_user_id in room["alive_players"]:
                    room["alive_players"].remove(hanged_user_id)
                    room["dead_players"].append(hanged_user_id)
                    
                    # Kiểm tra chức năng đặc biệt: Thằng Hề (Fool) thắng cuộc khi bị treo cổ ban ngày
                    if room["roles"].get(hanged_user_id) == "FOOL":
                        await core_end_match_trigger(room_code, f"🤡 THẰNG HỀ CHIẾN THẮNG ĐƠN ĐỘC! Diễn xuất đỉnh cao khiến cả làng lú lẫn đem treo cổ gã.", context)
                        return
                        
                    await context.bot.send_message(
                        chat_id=room["chat_id"],
                        text=f"🪓 **KẾT QUẢ PHÁN QUYẾT:** Kẻ tội đồ *{USERS[hanged_user_id]['name']}* nhận nhiều phiếu bầu nhất và bị áp giải lên giàn thiêu! "
                             f"Chức năng thật khi chết: `{room['roles'][hanged_user_id]}`.",
                        parse_mode="Markdown"
                    )
            
            # Nếu chưa ai thắng, vòng tuần hoàn tiếp tục: Reset về Đêm tiếp theo
            room["phase"] = "NIGHT"
            room["weather_idx"] = random.randint(0, len(WEATHER_EFFECTS["NIGHT"]) - 1)
            room["votes"] = {"WEREWOLF": {}, "BODYGUARD": None, "WITCH": {"action": None, "target": None}, "SEER": None}
            
            header = generate_weather_template("NIGHT", room["weather_idx"])
            next_night_text = f"{header}🌙 **CHU KỲ TUẦN HOÀN: ĐÊM TIẾP THEO LẠI BUÔNG XUỐNG!** 🌙\n\n" \
                              f"Oán khí ngút trời, bóng tối tái sinh. Hãy lẩn trốn thật kỹ hoặc thực thi hành động ẩn để sinh tồn!"
            
            night_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🐺 Menu Phe Sói", callback_data="action_wolf_menu")],
                [InlineKeyboardButton("👁️ Soi Gương Tiên Tri", callback_data="action_seer_menu")],
                [InlineKeyboardButton("🛡️ Khiên Thần Bảo Vệ", callback_data="action_guard_menu")],
                [InlineKeyboardButton("🧪 Độc Dược Phù Thủy", callback_data="action_witch_menu")],
                [InlineKeyboardButton("🌅 Kết Thúc Đêm (Tính toán kết quả)", callback_data="game_goto_day")]
            ])

            # 🔥 VÒNG TUẦN HOÀN TÁI SINH: Nếu chưa ai thắng, bóng đêm lại bao trùm!
            room["phase"] = "NIGHT"
            room["weather_idx"] = random.randint(0, len(WEATHER_EFFECTS["NIGHT"]) - 1)
            
            # Reset hoàn toàn hòm phiếu ẩn để chuẩn bị cho một cuộc đi săn mới
            room["votes"] = {
                "WEREWOLF": {}, 
                "BODYGUARD": None, 
                "WITCH": {"action": None, "target": None}, 
                "SEER": None
            }
            
            # Nạp giao diện thời tiết đêm kinh hoàng mới
            header = generate_weather_template("NIGHT", room["weather_idx"])
            next_night_text = f"{header}🌙 **ĐÊM TIẾP THEO LẠI BUÔNG XUỐNG!** 🌙\n\n" \
                              f"Oán khí ngút trời, bóng tối tái sinh che lấp những âm mưu đen tối. " \
                              f"Hàm răng của Sói lại thèm khát máu tươi, các chức năng hãy nhanh chóng hành động để tự cứu lấy mình!"
            
            # Tái tạo bảng nút bấm tương tác đêm để người chơi click thi triển phép thuật
            night_kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🐺 Menu Phe Sói (Chỉ Sói)", callback_data="action_wolf_menu")],
                [InlineKeyboardButton("👁️ Soi Gương Tiên Tri (Chỉ Seer)", callback_data="action_seer_menu")],
                [InlineKeyboardButton("🛡️ Khiên Thần Bảo Vệ (Chỉ Guard)", callback_data="action_guard_menu")],
                [InlineKeyboardButton("🧪 Độc Dược Phù Thủy (Chỉ Witch)", callback_data="action_witch_menu")],
                [InlineKeyboardButton("🌅 Kết Thúc Đêm (Tính toán kết quả)", callback_data="game_goto_day")]
            ])
            
            # Gửi thông báo trực tiếp vào phòng chat chung của làng để ép đổi giai đoạn lập tức
            await context.bot.send_message(
                chat_id=room["chat_id"], 
                text=next_night_text, 
                reply_markup=night_kb, 
                parse_mode="Markdown"
            )


async def core_end_match_trigger(room_code: str, victory_banner: str, context: ContextTypes.DEFAULT_TYPE):
    """[Phần 59 - 65]: Màn hình tổng kết vinh danh, phát thưởng cấp độ kịch tính & dọn dẹp bộ nhớ"""
    room = ROOMS[room_code]
    
    end_text = f"🏁 **TRẬN ĐẤU KẾT THÚC ĐỒNG BỘ** 🏁\n\n" \
               f"🎉 **KẾT QUẢ CHUNG CUỘC:**\n*{victory_banner}*\n\n" \
               f"📋 **NHẬT KÝ DANH TÍNH NGÔI LÀNG:**\n"
    
    for p_id in room["players"]:
        name = USERS[p_id]["name"]
        role = room["roles"].get(p_id, "🌾 VILLAGER")
        status = "🟢 Sống sót thần kỳ" if p_id in room["alive_players"] else "💀 Thăng thiên"
        end_text += f"• {name}: Vai bài `{role}` -> Trạng thái: {status}\n"
        
        # 🪙 Hệ thống phân phối phần thưởng đồng bộ vào Profile người chơi
        if p_id in USERS:
            USERS[p_id]["xp"] += 100
            USERS[p_id]["coins"] += 20
            
            # Thuật toán tự động thăng cấp Level khi tích đủ 200 điểm kinh nghiệm
            if USERS[p_id]["xp"] >= 200:
                USERS[p_id]["level"] += 1
                USERS[p_id]["xp"] = 0
                try:
                    await context.bot.send_message(
                        chat_id=p_id, 
                        text=f"🆙 **CHÚC MỪNG!** Bạn đã thăng lên cấp độ `Lv.{USERS[p_id]['level']}` nhờ màn trình diễn xuất sắc!"
                    )
                except:
                    pass

    await context.bot.send_message(chat_id=room["chat_id"], text=end_text, parse_mode="Markdown")
    
    # 🧹 [Phần 64]: Cơ chế reset phòng chơi cũ, giải phóng bộ nhớ đệm chống tràn dữ liệu VPS
    for p_id in room["players"]:
        PLAYER_ROOM_MAP.pop(p_id, None)
    ROOMS.pop(room_code, None)


# ============================================================================
# ⚙️ [PHẦF 66 - 70]: KHỞI CHẠY CHÍNH VÀ MÔI TRƯỜNG THỰC TẾ (MAIN ENGINE)
# ============================================================================
def main():
    """Hàm khởi chạy chính của framework, đăng ký định tuyến sự kiện toàn diện"""
    # 🔑 NHẬP ĐOẠN API TOKEN ĐƯỢC CẤP TỪ @BotFather VÀO ĐÂY ĐỂ VẬN HÀNH
    TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
    
    # Dựng khung ứng dụng bot kèm cấu hình tắt xem trước liên kết (Link Preview) để gọn giao diện chat
    app = Application.builder().token(TOKEN).link_preview_options(LinkPreviewOptions(is_disabled=True)).build()
    
    # Đăng ký bộ xử lý văn bản và nút bấm tương tác tập trung
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("join", join_room_by_code)) 
    app.add_handler(CallbackQueryHandler(router_core_engine))  # Đồng bộ tất cả xử lý nút bấm tại đây
    
    print("🚀 [SUCCESS] Framework Bot Game Ma Sói Hoàn Chỉnh Đang Vận Hành Thành Công!")
    app.run_polling()

if __name__ == '__main__':
    main()
