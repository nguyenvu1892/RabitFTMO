# 📋 WALKTHROUGH — Dự án Rabit_FTMO AI (XAGUSD)

---

## [Phase 1] Task 1.1 — Khởi tạo Môi trường Ảo & Thư viện

**Ngày thực hiện:** 2026-03-05  
**Branch:** `feature/task1.1-env-setup`  
**Commit:** `79b6885`  
**Trạng thái:** ✅ HOÀN THÀNH

---

## 1. Files Đã Tạo (13 files, 653 insertions)

| File | Mục đích |
|------|---------|
| `.gitignore` | Chặn `.env`, `venv/`, `logs/`, `__pycache__/` khỏi Git |
| `.env.example` | Template credentials MT5/FTMO (an toàn để commit) |
| `requirements.txt` | 6 thư viện phân tầng (Core → Security → Utils → ML) |
| `History.txt` | Log lịch sử Phase/Task |
| `core/__init__.py` | Khai báo package core |
| `core/data_pipeline.py` | Skeleton + docstring + TODOs cho Task 1.2 |
| `config/__init__.py` | Khai báo package config |
| `config/settings.py` | **Tất cả hằng số** từ CORE_RULES.md (SYMBOL, ATR, RISK, Timing) |
| `utils/__init__.py` | Khai báo package utils |
| `utils/logger.py` | Dual-log: `system.log` (INFO) + `trade_decisions.log` (DEBUG) |
| `utils/health_check.py` | 5 Pre-flight checks skeleton (NotImplementedError safeguard) |
| `main.py` | Entry point — load dotenv + system_logger, TODOs Phase sau |
| `logs/.gitkeep` | Giữ thư mục `logs/` trong Git (logs thật bị .gitignore chặn) |

---

## 2. Cấu trúc Thư mục Thực tế

```
RabitFTMO/
├── .env.example          ← Template (commit được)
├── .gitignore            ← Bảo vệ bí mật
├── requirements.txt      ← 6 thư viện lõi
├── History.txt           ← Log Phase/Task
├── main.py               ← Entry point
│
├── core/
│   ├── __init__.py
│   └── data_pipeline.py  ← Skeleton (Task 1.2 implement)
│
├── config/
│   ├── __init__.py
│   └── settings.py       ← Tập trung hóa TOÀN BỘ hằng số
│
├── utils/
│   ├── __init__.py
│   ├── logger.py         ← Dual-log system ✅
│   └── health_check.py   ← Pre-flight checks ✅
│
├── logs/
│   └── .gitkeep          ← Placeholder
│
└── docs/
    └── walkthrough.md    ← File này
```

---

## 3. Hướng dẫn Setup Virtual Environment (User tự chạy)

```powershell
# Bước 1: Tạo venv trong thư mục dự án
python -m venv venv

# Bước 2: Kích hoạt (PowerShell)
.\venv\Scripts\Activate.ps1
# Nếu lỗi execution policy:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Bước 3: Cài thư viện
pip install -r requirements.txt

# Bước 4: Copy file .env và điền thông tin thật
copy .env.example .env
# Mở .env và điền MT5_LOGIN, MT5_PASSWORD, MT5_SERVER

# Bước 5: Test chạy thử (kiểm tra logger hoạt động)
python main.py
```

---

## 4. History Log

```
[Phase 1] Task 1.1 Khởi tạo môi trường ảo và thư viện
- Lý do  : Đặt nền móng dự án Python và thư viện MT5
- Ngày   : 2026-03-05
- Branch : feature/task1.1-env-setup
- Commit : 79b6885
- Status : ✅ HOÀN THÀNH — Chờ TechLead merge PR hoặc tiếp tục Task 1.2
```

---

## 5. Bước Tiếp theo (Task 1.2)

- Implement `core/data_pipeline.py` — Kết nối MT5, kéo OHLCV XAGUSD (M5/M15/H1)
- Implement `utils/health_check.py` — 5 pre-flight checks
- Merge PR `feature/task1.1-env-setup` → `main`