"""
utils/health_check.py — Kiểm tra sức khỏe hệ thống trước khi bot khởi chạy

Mục đích:
    Đảm bảo tất cả điều kiện tiên quyết đều thỏa mãn trước khi bot
    bắt đầu vòng lặp giao dịch. Nếu bất kỳ check nào thất bại,
    bot KHÔNG được phép khởi động — tránh giao dịch "mù".

Danh sách kiểm tra:
    [1] Kết nối MetaTrader 5 Terminal thành công.
    [2] Đăng nhập tài khoản MT5 thành công (credentials từ .env).
    [3] Symbol XAGUSD khả dụng và có thể giao dịch.
    [4] Giờ hiện tại KHÔNG nằm trong khung cấm (News Filter / Force Close).
    [5] Daily Drawdown chưa chạm ngưỡng 4.5% FTMO.

Phase: 1 — Task 1.1 (Skeleton). Logic đầy đủ sẽ implement ở Task 1.2 và Phase 2.

Tác giả: Antigravity (AI Coder)
Ngày tạo: 2026-03-05
"""

# TODO (Task 1.2): Uncomment khi DataPipeline đã implement
# import MetaTrader5 as mt5
# from utils.logger import system_logger
# from config.settings import SYMBOL

# TODO (Phase 2): Thêm kiểm tra Risk/Drawdown và News Filter


def check_mt5_connection() -> bool:
    """
    [CHECK 1] Kiểm tra MetaTrader 5 Terminal đang chạy và có thể kết nối.

    Returns:
        bool: True nếu kết nối thành công, False nếu thất bại.
    """
    # TODO (Task 1.2): Implement kết nối MT5
    # if not mt5.initialize():
    #     system_logger.error(f"[HealthCheck] FAIL - MT5 không thể khởi động: {mt5.last_error()}")
    #     return False
    # system_logger.info("[HealthCheck] PASS - Kết nối MT5 Terminal thành công.")
    # return True
    raise NotImplementedError("check_mt5_connection() sẽ implement ở Task 1.2")


def check_symbol_available(symbol: str) -> bool:
    """
    [CHECK 3] Xác nhận symbol (XAGUSD) đang khả dụng và có thể giao dịch.

    Args:
        symbol: Tên symbol cần kiểm tra (XAGUSD).

    Returns:
        bool: True nếu symbol available, False nếu không.
    """
    # TODO (Task 1.2): Implement kiểm tra symbol
    raise NotImplementedError("check_symbol_available() sẽ implement ở Task 1.2")


def run_all_checks() -> bool:
    """
    Entry point chạy toàn bộ chuỗi kiểm tra sức khỏe hệ thống.
    Gọi hàm này trước khi khởi động vòng lặp bot chính.

    Returns:
        bool: True nếu TẤT CẢ checks đều PASS, False nếu bất kỳ check nào FAIL.
    """
    # TODO (Task 1.2): Lắp ghép toàn bộ checks vào đây
    raise NotImplementedError("run_all_checks() sẽ implement ở Task 1.2")
