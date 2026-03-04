"""
utils/logger.py — Thiết lập Dual-Log System cho Rabit_FTMO AI

Chiến lược logging 2 cấp độ (đã phê duyệt bởi TechLead - Task 1.1):
    1. system.log         — INFO level: Mọi hoạt động của bot (startup, kết nối, lỗi, phiên)
    2. trade_decisions.log — DEBUG level: Chỉ ghi lý do vào/ra lệnh
                            (Dataset quý giá cho Phase 5 ML Training)

Sử dụng:
    from utils.logger import system_logger, trade_logger

    system_logger.info("Bot khởi động - Kết nối MT5 thành công")
    trade_logger.debug("ENTRY | XAGUSD | BUY | Lý do: Pinbar + VSA Climax tại FVG H1")
"""

import logging
import os
from config.settings import SYSTEM_LOG_FILE, TRADE_LOG_FILE, LOG_DIR

# Tạo thư mục logs/ nếu chưa tồn tại
os.makedirs(LOG_DIR, exist_ok=True)


def _build_logger(name: str, log_file: str, level: int) -> logging.Logger:
    """
    Factory tạo một logger với handler ghi ra file và console.

    Args:
        name     : Tên logger (phân biệt trong logging registry)
        log_file : Đường dẫn file log
        level    : Mức logging (logging.INFO / logging.DEBUG)

    Returns:
        logging.Logger: Logger đã cấu hình sẵn
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Tránh thêm handler trùng lặp khi module được import nhiều lần
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # --- Handler 1: Ghi ra File ---
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # --- Handler 2: In ra Console (stdout) ---
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)   # Console chỉ hiện INFO trở lên
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


# ============================================================
# LOGGER 1: HỆ THỐNG — Mọi hoạt động bot
# ============================================================
system_logger = _build_logger(
    name="rabit.system",
    log_file=SYSTEM_LOG_FILE,
    level=logging.INFO
)

# ============================================================
# LOGGER 2: QUYẾT ĐỊNH GIAO DỊCH — Dataset cho Phase 5 ML
# ============================================================
trade_logger = _build_logger(
    name="rabit.trade",
    log_file=TRADE_LOG_FILE,
    level=logging.DEBUG
)
