# config.py
import os

# Thay Token Bot của bạn vào đây
BOT_TOKEN = "TOKEN_CỦA_BẠN"

# Cấu hình thời gian các Phase (giây) - Thiết lập ngắn để test, có thể tăng lên khi chơi thật
TIME_LOBBY_COUNTDOWN = 30
TIME_NIGHT = 45
TIME_DISCUSSION = 60
TIME_VOTE = 30
TIME_DEFENSE = 20

# Danh sách tất cả các vai trò được hỗ trợ trong hệ thống
ALL_ROLES = [
    "Ma Sói", "Sói Nhỏ", "Sói Trắng", 
    "Tiên Tri", "Bảo Vệ", "Phù Thủy", "Già Làng", "Thợ Săn", "Thằng Hề", "Kẻ Thâm Độc",
    "Dân Làng"
]

# Hệ thống thời tiết và hiệu ứng ảnh hưởng đến game
WEATHER_EFFECTS = {
    "Trời Quang": "☀️ Thời tiết bình thường, không có hiệu ứng phụ.",
    "Sương Mù": "🌫️ Sương mù dày đặc! Tiên Tri có 30% tỷ lệ soi sai vai trò đêm nay.",
    "Trăng Tròn": "🌕 Trăng tròn rực rỡ! Sức mạnh Ma Sói tăng cao, Bảo Vệ không thể bảo vệ chính mình.",
    "Mưa Bão": "⛈️ Mưa bão sấm chớp! Mọi người hoảng loạn, thời gian thảo luận ban ngày giảm 20 giây."
}
