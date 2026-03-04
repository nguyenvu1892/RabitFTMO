# 📋 WALKTHROUGH - Dự án Rabit_FTMO AI (XAGUSD)

---

## [Phase 1] Task 1.1 — Khởi tạo Môi trường Ảo & Thư viện

**Ngày thực hiện:** 2026-03-05  
**Người thực hiện AI:** Antigravity  
**Branch:** `feature/task1.1-env-setup` (sẽ tạo sau khi TechLead PROCEED)  
**Trạng thái:** ⏳ CHỜ LỆNH PROCEED

---

## 1. Phân tích Bối cảnh (Context Analysis)

### 1.1 Mục tiêu dự án (từ CORE_RULES.md)

Dự án **Rabit_FTMO** là một Algorithmic Trading Bot hoàn toàn tự động giao dịch cặp **XAGUSD** (Bạc/USD) trên nền tảng **MetaTrader 5**, mục tiêu vượt qua kỳ thi tài khoản **FTMO Normal**. Kiến trúc hoạt động theo 2 tầng:

1. **Rule-based Layer (Tầng 1):** 5 vũ khí cốt lõi (Market Structure H1, FVG M15, Pinbar M5, VSA Volume, ATR).
2. **Self-Evolving ML Layer (Tầng 2):** Module RL học từ lịch sử trade thực tế để tự tinh chỉnh trọng số.

Giao tiếp với MT5 thông qua thư viện `MetaTrader5` của Python — đây là cầu nối **sống còn** của toàn bộ hệ thống.

---

## 2. Phân tích Thư viện Cần thiết

### 2.1 Bảng Thư viện Lõi

| STT | Thư viện | Phiên bản gợi ý | Vai trò | Lý do BẮT BUỘC |
|-----|----------|-----------------|---------|----------------|
| 1 | `MetaTrader5` | `>=5.0.45` | Kết nối MT5, kéo OHLCV, gửi lệnh | Cầu nối duy nhất giữa Python và sàn giao dịch |
| 2 | `pandas` | `>=2.0.0` | Xử lý DataFrame nến (OHLCV + Tick Volume) | Toàn bộ logic tính toán 5 vũ khí dựa trên DataFrame |
| 3 | `numpy` | `>=1.26.0` | Tính toán toán học nhanh (ATR, SL/TP, rolling window) | Nhanh hơn pandas thuần khi tính vector/ma trận |
| 4 | `python-dotenv` | `>=1.0.0` | Load biến môi trường từ file `.env` | **BẢO MẬT** — ẩn MT5 login/password/server FTMO khỏi codebase |

### 2.2 Thư viện Mở rộng (Đề xuất thêm — Phase sau)

| STT | Thư viện | Vai trò | Phase sử dụng |
|-----|----------|---------|--------------|
| 5 | `requests` | Gọi API Lịch kinh tế (News Filter) | Phase 2 - Task 2.3 |
| 6 | `schedule` | Scheduler tự động chạy bot theo giờ phiên | Phase 4 |
| 7 | `stable-baselines3` | Framework Reinforcement Learning (PPO/A2C) | Phase 5 |
| 8 | `gymnasium` | Môi trường RL chuẩn OpenAI Gym | Phase 5 |
| 9 | `loguru` | Logging nâng cao thay `logging` chuẩn | Phase 4 |

> **Lưu ý từ AI:** `requests` nên được thêm ngay vào `requirements.txt` từ bây giờ vì Phase 2.3 (News Filter) sẽ đến sớm, tránh phải cài thêm sau.

---

## 3. Đề xuất Cấu trúc Thư mục Chuẩn

Dựa trên **CORE_RULES.md** quy định các module: `data_pipeline.py`, `strategy_engine.py`, `risk_manager.py`, `execution.py`, `ml_model.py`.

```
RabitFTMO/                          ← Root (đã có Git)
│
├── .env                            ← [KHÔNG đẩy Git] Chứa MT5_LOGIN, MT5_PASSWORD, MT5_SERVER
├── .gitignore                      ← Chặn .env, __pycache__, venv/, *.log
├── requirements.txt                ← Danh sách thư viện pip
├── CORE_RULES.md                   ← Bộ luật hệ thống (đã có)
├── Plan.md                         ← Master Plan (đã có)
├── History.txt                     ← Log lịch sử thay đổi theo Phase
│
├── core/                           ← [MỚI] Tầng lõi xử lý nghiệp vụ
│   ├── __init__.py
│   ├── data_pipeline.py            ← Kết nối MT5, kéo dữ liệu OHLCV XAGUSD
│   ├── strategy_engine.py          ← Engine tính 5 Vũ khí (H1/M15/M5)
│   ├── risk_manager.py             ← Quản lý rủi ro FTMO (4.5% DD, Lot sizing)
│   ├── execution.py                ← Gửi lệnh Buy/Sell/Close xuống MT5
│   └── ml_model.py                 ← Module AI/RL tự tiến hóa (Phase 5)
│
├── config/                         ← [MỚI] Cấu hình toàn cục
│   ├── __init__.py
│   └── settings.py                 ← Hằng số: SYMBOL="XAGUSD", TIMEFRAMES, ATR_PERIOD=14
│
├── utils/                          ← [MỚI] Tiện ích dùng chung
│   ├── __init__.py
│   └── logger.py                   ← Setup logger ghi ra system.log
│
├── logs/                           ← [MỚI] File log runtime (không đẩy Git)
│   └── system.log
│
├── docs/                           ← Tài liệu (đã có)
│   └── walkthrough.md              ← File này
│
└── main.py                         ← [MỚI] Entry point — khởi chạy bot
```

### 3.1 Tại sao chọn cấu trúc này?

- **`core/`** tách biệt hoàn toàn từng domain logic theo đúng quy định CORE_RULES.md — dễ test, dễ maintain.
- **`config/settings.py`** tập trung hóa hằng số (`SYMBOL`, `ATR_PERIOD`, `RISK_PER_TRADE`), tránh hardcode rải rác.
- **`utils/logger.py`** chuẩn hóa logging từ đầu — bắt buộc theo CORE_RULES.md (ghi log mọi quyết định).
- **`.env + python-dotenv`** là pattern tiêu chuẩn công nghiệp để bảo mật credentials FTMO — tuyệt đối không commit password lên Git.

---

## 4. Kế hoạch Triển khai Chi tiết (Implementation Plan)

### Bước 1 — Git Hygiene (Thực hiện trên Terminal của User)

```bash
# Xác nhận đang ở main và sạch
git status
git branch

# Tạo và chuyển sang branch mới
git checkout -b feature/task1.1-env-setup
```

> **Trạng thái hiện tại:** Branch `main` đã sạch, không có untracked changes. ✅

### Bước 2 — Tạo Virtual Environment (User tự chạy trên Terminal)

```bash
# Trong thư mục RabitFTMO/
python -m venv venv

# Kích hoạt (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Kích hoạt (Windows CMD)
venv\Scripts\activate.bat
```

> ⚠️ **Lưu ý Windows:** Nếu gặp lỗi "execution policy", chạy trước:  
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### Bước 3 — Antigravity sẽ tạo các file sau (sau khi có lệnh PROCEED)

| File | Thao tác | Nội dung |
|------|----------|---------|
| `requirements.txt` | TẠO MỚI | 4 thư viện lõi + comments |
| `.gitignore` | TẠO MỚI | Chặn `.env`, `venv/`, `logs/`, `__pycache__/` |
| `.env.example` | TẠO MỚI | Template mẫu (không chứa pass thật) |
| `History.txt` | TẠO MỚI | Ghi log Phase 1 Task 1.1 |
| `core/__init__.py` | TẠO MỚI | File trống |
| `core/data_pipeline.py` | TẠO MỚI | File trống với docstring mô tả module |
| `config/__init__.py` | TẠO MỚI | File trống |
| `config/settings.py` | TẠO MỚI | Hằng số SYMBOL, TIMEFRAMES, RISK |
| `utils/__init__.py` | TẠO MỚI | File trống |
| `utils/logger.py` | TẠO MỚI | Setup logger → `logs/system.log` |
| `main.py` | TẠO MỚI | Entry point skeleton |

### Bước 4 — Cài đặt thư viện (User tự chạy sau khi Antigravity tạo requirements.txt)

```bash
pip install -r requirements.txt
```

### Bước 5 — Commit và push branch

```bash
git add .
git commit -m "[Phase 1][Task 1.1] Setup môi trường Python, cấu trúc dự án và thư viện MT5"
git push origin feature/task1.1-env-setup
```

---

## 5. Phân tích Rủi ro & Đề xuất Cải tiến AI

### 5.1 ⚠️ Rủi ro Bảo mật (CRITICAL)

**Vấn đề:** Credentials FTMO (Account ID, Password, Server) nếu lộ lên GitHub → tài khoản bị truy cập trái phép.

**Giải pháp đề xuất:**
1. Dùng `python-dotenv` để load `.env` — **không bao giờ** commit `.env` lên Git.
2. Tạo `.env.example` làm template hướng dẫn (không có giá trị thật).
3. Thêm `.env` vào `.gitignore` ngay từ commit đầu tiên.
4. *(Nâng cao — Phase sau)* Xem xét dùng Windows Credential Store hoặc Azure Key Vault cho môi trường production.

### 5.2 💡 Đề xuất Cải tiến Cấu trúc

1. **Thêm `config/trading_params.json`:** Tách biệt các tham số trading (ATR_MULTIPLIER, RISK_PERCENT, PINBAR_RATIO) ra JSON/YAML để điều chỉnh mà không cần sửa code — rất hữu ích khi cần hot-reload params giữa các phiên.

2. **Module `health_check.py`:** Thêm ngay từ đầu một file kiểm tra trạng thái kết nối MT5 trước khi bot chạy — tránh bot chạy lệnh "mù" khi MT5 mất kết nối.

3. **Logging hai cấp độ:**
   - `system.log` — Mọi hoạt động của bot (INFO level).
   - `trade_decisions.log` — Riêng biệt chỉ ghi lý do vào/ra lệnh (DEBUG level) — dữ liệu quý giá cho Phase 5 ML.

---

## 6. History Log

```
[Phase 1] Task 1.1 Khởi tạo môi trường ảo và thư viện
- Lý do: Đặt nền móng dự án Python và thư viện MT5
- Ngày: 2026-03-05
- Branch: feature/task1.1-env-setup
- Trạng thái: PENDING PROCEED
```

---

*⏸️ DỪNG TẠI ĐÂY — Chờ lệnh PROCEED từ TechLead/Sếp trước khi bất kỳ dòng code nào được tạo.*