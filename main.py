"""
main.py — Entry Point chính của Rabit_FTMO AI Bot (XAGUSD)

Đây là file khởi chạy duy nhất của toàn bộ hệ thống.
Luồng hoạt động dự kiến:
    1. Load cấu hình & credentials từ .env
    2. Chạy Health Check tiền khởi động
    3. Khởi tạo DataPipeline (kết nối MT5)
    4. Vòng lặp chính: OnTick loop
       - Kéo dữ liệu OHLCV XAGUSD (M5 / M15 / H1)
       - Chạy Strategy Engine (5 Vũ khí)
       - Kiểm tra Risk Manager (FTMO rules)
       - Nếu đủ điều kiện → Execution (gửi lệnh)
    5. Force Close trước giờ đóng phiên

Phase: 1 — Task 1.1 (Skeleton). Toàn bộ logic sẽ implement từ Task 1.2 trở đi.

Tác giả: Antigravity (AI Coder)
Ngày tạo: 2026-03-05

Cách chạy:
    # Kích hoạt venv trước
    .\\venv\\Scripts\\Activate.ps1

    # Chạy bot
    python main.py
"""

from dotenv import load_dotenv
from utils.logger import system_logger

# TODO (Task 1.2): Uncomment từng module khi đã implement xong
# from utils.health_check import run_all_checks
# from core.data_pipeline import DataPipeline
# from core.strategy_engine import StrategyEngine
# from core.risk_manager import RiskManager
# from core.execution import ExecutionEngine


def main():
    """Entry point chính khởi chạy Rabit_FTMO AI Bot."""

    # --- Bước 1: Load biến môi trường từ .env ---
    load_dotenv()
    system_logger.info("=" * 60)
    system_logger.info("🐇 Rabit_FTMO AI Bot — Khởi động")
    system_logger.info("=" * 60)

    # --- Bước 2: Health Check ---
    # TODO (Task 1.2): Bỏ comment khi health_check đã implement
    # system_logger.info("Đang chạy kiểm tra tiền khởi động (Health Checks)...")
    # if not run_all_checks():
    #     system_logger.critical("Health Check THẤT BẠI. Bot dừng lại.")
    #     return

    # --- Bước 3–5: Vòng lặp chính (OnTick) ---
    # TODO (Task 1.2 – Phase 4): Implement vòng lặp chính
    system_logger.info("⚙️  main.py skeleton sẵn sàng. Chờ implement từ Task 1.2.")


if __name__ == "__main__":
    main()
