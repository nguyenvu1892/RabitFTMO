"""
core/__init__.py — Package core của Rabit_FTMO AI

Modules trong package này:
    data_pipeline   : Kết nối MT5, kéo OHLCV + Tick Volume XAGUSD
    strategy_engine : Engine tính toán 5 Vũ khí (H1/M15/M5)
    risk_manager    : Quản lý rủi ro FTMO (4.5% DD Hard-Stop, Lot sizing)
    execution       : Gửi lệnh Buy/Sell/Close xuống MT5
    ml_model        : Module AI/RL tự tiến hóa (Phase 5)
"""
