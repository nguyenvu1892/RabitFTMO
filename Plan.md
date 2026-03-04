🗺️ MASTER PLAN: DỰ ÁN RABIT_FTMO AI (XAGUSD)
Công nghệ: Python 3.10+ & MetaTrader 5 API
Mục tiêu: Vượt qua quỹ FTMO Normal và tự động hóa 100% bằng 5 vũ khí SMC/VSA.

📍 Phase 0: Khởi tạo Kỷ luật & Nền móng (Đã hoàn thành 90%)
Mục tiêu: Định hình luật chơi cho AI Coder (Antigravity).

Task 0.1: Khởi tạo Git repository RabitFTMO trên local và GitHub. (Anh đã làm xong).

Task 0.2: Đưa bộ luật CORE_RULES.md (Quy tắc hệ thống) và AI_SOP_TEMPLATE.md (Quy trình ép buộc Antigravity) vào thư mục gốc. (Đang tiến hành).

📍 Phase 1: Mạch máu Dữ liệu (Data Pipeline & MT5 Connection)
Mục tiêu: Xây dựng cầu nối để Python "nhìn thấy" thị trường thông qua MT5.

Task 1.1 (Setup): Tạo môi trường ảo (virtualenv), cài đặt thư viện MetaTrader5, pandas, numpy.

Task 1.2 (Connect & Fetch): Code module data_pipeline.py.

Kết nối an toàn vào tài khoản FTMO.

Hàm kéo dữ liệu nến (Open, High, Low, Close) và Tick Volume của XAGUSD trên 3 khung M5, M15, H1.

Cơ chế xử lý lỗi (Try/Catch) tự động kết nối lại khi rớt mạng.

📍 Phase 2: Khiên bảo vệ & Quản trị FTMO (Risk Management)
Mục tiêu: Đảm bảo Bot sống sót, tuyệt đối không vi phạm luật FTMO Normal.

Task 2.1 (Position Sizing): Code module tính toán Lot Size động dựa trên % rủi ro cho phép (ví dụ 0.5%/lệnh) và khoảng cách SL (tính theo ATR).

Task 2.2 (Hard-Stop FTMO): Code logic theo dõi Equity realtime. Khóa bot ngay lập tức nếu lỗ trong ngày chạm ngưỡng 4.5% (Daily Drawdown).

Task 2.3 (Intraday & News Filter): * Logic tự động đóng mọi lệnh XAGUSD trước giờ đóng phiên hàng ngày.

Tích hợp API Lịch kinh tế: Khóa giao dịch trước/sau 30 phút khi có tin Đỏ (USD).

📍 Phase 3: Khối óc Chiến lược (The 5 Weapons Engine)
Mục tiêu: Số hóa 5 vũ khí giao dịch thành các hàm logic bằng Python (không dùng Indicator có sẵn của MT5).

Task 3.1 (H1 Compass): Nhận diện Market Structure (Swing High/Low, BOS, CHoCH) để chốt hướng đánh (Directional Bias).

Task 3.2 (M15 POI): Quét Imbalance 3 nến để vẽ Box FVG làm vùng chờ. Xóa Box khi giá đã lấp đầy.

Task 3.3 (M5 Trigger): Bắt nến Pinbar/Hammer tại vùng FVG.

Task 3.4 (M5 VSA): Đọc Tick Volume của nến Pinbar. Lọc nhiễu bằng logic VSA (Chỉ vào lệnh nếu Volume cực cao - Climax, hoặc cực thấp - No Supply/Demand).

Task 3.5 (ATR Management): Tính toán SL động (tránh quét râu/giãn spread) và dời SL về hòa vốn (Breakeven).

📍 Phase 4: Lắp ráp & Mô phỏng (Master Assembly & Backtest)
Mục tiêu: Ghép các module lại và cho chạy test trên dữ liệu quá khứ.

Task 4.1 (Execution Logic): Tạo hàm OnTick của Python. Nếu (Phase 2 an toàn) + (Phase 3 đủ 5 điều kiện) -> Bắn lệnh Buy/Sell xuống MT5.

Task 4.2 (Logging System): Lưu xuất toàn bộ lịch sử ra quyết định, file log system_log.csv (Rất quan trọng cho Phase 5). Bot vào lệnh vì lý do gì, Volume lúc đó là bao nhiêu, bị quét SL hay dính TP.

📍 Phase 5: Tiến hóa (AI / Machine Learning Integration)
Mục tiêu: Biến Bot từ Rule-based thành AI tự học (Mục tiêu tối thượng của Rabit 2.0).

Task 5.1 (Data Preparation): Sử dụng data từ Phase 4 để làm tập huấn luyện (Training dataset).

Task 5.2 (Reinforcement Learning): Xây dựng môi trường RL (ví dụ dùng thư viện Stable Baselines3). Cho AI tự động test hàng triệu kịch bản để tự tinh chỉnh các trọng số: Tỷ lệ Râu nến Pinbar bao nhiêu là đẹp nhất? Hệ số nhân ATR nên là 1.5 hay 2.0 tùy theo độ biến động của phiên Âu/Mỹ?