# Connect Four | Explainable AI

Đồ án Nhập môn Trí tuệ Nhân tạo. Người chơi đấu với AI Alpha-Beta ở độ sâu 2, 4 hoặc 6.
Điểm khác biệt của đồ án: AI giải thích từng nước đi, trả lời "vì sao không đi cột kia",
nhận xét nước đi của người chơi, và mọi lời giải thích đều được kiểm chứng tự động.

| Câu hỏi nghiên cứu | Cách trả lời | Kết quả nằm ở |
|---|---|---|
| RQ1. Lời giải thích có đúng không? | Đi lại từng khẳng định trên 1.200 thế cờ ngẫu nhiên | `results/faithfulness_summary.csv` |
| RQ2. Lời giải thích có giúp người chơi đoán được AI không? | Khảo sát đoán nước, hai nhóm có và không có giải thích | `results/study.csv` |
| RQ3. Giải thích tốn thêm bao nhiêu tính toán? | So thời gian chọn nước với chọn và giải thích | `results/overhead.csv` |

## Cài và chạy trên Windows

Mở thư mục repo (`AI`) trong VS Code rồi mở Terminal (PowerShell). Dùng Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Trên macOS hoặc Linux, tạo môi trường bằng `python3 -m venv .venv` rồi
dùng `.venv/bin/python` thay cho `.\.venv\Scripts\python.exe`.

## Điều khiển

| Thao tác | Kết quả |
|---|---|
| Click trái một cột | Thả quân vàng. AI thả quân đỏ và hiện phân tích. |
| Click phải một cột | Hỏi "Why not column X?": AI nêu hậu quả và chuỗi nước dự kiến. |
| E | Bật/tắt toàn bộ phần giải thích. |
| C | Bật/tắt huấn luyện viên (nhận xét nước đi của người chơi). |
| 2 / 4 / 6 | Đổi độ sâu cho lần tìm kiếm kế tiếp. |
| F1 / F2 / F3 | Thế cờ demo: AI thắng ngay, AI phải chặn, so sánh điểm tìm kiếm. |
| R / Esc | Ván mới / thoát. |

## AI giải thích những gì

**Hàng nhãn phía trên bàn cờ** cho biết AI đánh giá từng cột ra sao trước khi đi:
`Win 2` là thắng chắc sau 2 nước của AI, `Loss 1` là đối thủ thắng ngay ở nước kế,
số có dấu (`+8`) là điểm Minimax khi chưa thấy kết cục trong phạm vi độ sâu.
Cột AI chọn có viền trắng.

**Lý do chọn nước** thuộc một trong bảy loại, xét theo thứ tự:

| Loại | Ý nghĩa |
|---|---|
| `win` | Nước này tạo bốn quân liên tiếp. |
| `block` | Chặn bốn quân liên tiếp của đối thủ. |
| `lost` | Mọi nước đều thua; AI chọn nước thua muộn nhất, hoặc nêu hai cột đối thủ cùng dọa thắng. |
| `forced_win` | Thắng chắc sau N nước dù đối thủ đáp thế nào. |
| `avoid` | Nước an toàn; nêu các cột sẽ thua nếu đi vào. |
| `threat` | Điểm cao nhất và tạo đe dọa bốn quân. |
| `search` | Điểm Minimax cao nhất ở độ sâu đang dùng. |

**Huấn luyện viên** chấm nước của người chơi theo cùng cách tìm kiếm, từ góc nhìn người chơi:
`BEST`, `GOOD` (kém nước tốt nhất tối đa 3 điểm, hoặc thắng chậm hơn), `INACCURACY`,
`MISSED WIN`, `BLUNDER` (nước này để AI thắng chắc trong khi có nước an toàn).

Mọi điểm số chỉ đúng **trong phạm vi độ sâu đã tìm**. Từng nước ở gốc được tìm với cửa sổ
Alpha-Beta đầy đủ để lấy điểm chính xác. Khi đồng điểm, AI ưu tiên cột 4, 3, 5, 2, 6, 1, 7.

## Khảo sát đoán nước (RQ2)

Mỗi người tham gia chơi 2 đến 3 ván ở độ sâu 4. Chia hai nhóm xen kẽ:

```powershell
.\.venv\Scripts\python.exe main.py --study P01 --condition explain
.\.venv\Scripts\python.exe main.py --study P02 --condition control
```

Sau mỗi nước của mình, người chơi click vào cột mà họ đoán AI sẽ đi, rồi AI mới đi thật.
Nhóm `explain` thấy lời giải thích sau mỗi nước, nhóm `control` chỉ thấy nước đi.
Cuối ván, người chơi bấm 1 đến 5 để tự đánh giá mức độ hiểu AI.
Dữ liệu ghi nối vào `results/study.csv` và `results/study_ratings.csv`.

## Thực nghiệm, biểu đồ và test

```powershell
.\.venv\Scripts\python.exe experiment.py   # khoảng 2 phút, ghi CSV vào results/
.\.venv\Scripts\python.exe plots.py        # vẽ biểu đồ vào results/figures/
.\.venv\Scripts\python.exe -m pytest       # 12 test cho luật chơi, tìm kiếm và giải thích
```

| File | Nội dung |
|---|---|
| faithfulness.csv, faithfulness_summary.csv | RQ1: 1.000 thế cờ ở độ sâu 4 và 200 thế ở độ sâu 6. Mỗi khẳng định được kiểm bằng cách đi lại nước cờ và bằng một bộ kiểm tra vét cạn độc lập với hàm tìm kiếm. |
| faithfulness_failures.csv | Các khẳng định sai, nếu có. |
| overhead.csv | RQ3: số nút và thời gian của Alpha-Beta thường so với chế độ giải thích, 20 thế cờ, độ sâu 2 đến 8. |
| search.csv | 45 cấu hình gồm 5 bàn cờ, 3 độ sâu và 3 cấu hình tìm kiếm. Thời gian là trung vị của 3 lượt, tính bằng ms. |
| games.csv, games_summary.csv | 120 ván với Random và Greedy (Minimax sâu 1), dùng 10 seed và đổi bên trên cùng khai cuộc hai nước. |
| explanations.csv | 8 tình huống chọn tay kiểm tra nước đi, lý do và câu so sánh. |

Số node tính cả gốc và các lá đã duyệt. So sánh Minimax với Alpha-Beta giữ nguyên heuristic,
độ sâu và thứ tự duyệt. Chế độ giải thích còn tìm thêm chuỗi nước dự kiến cho cột so sánh;
phần đó có trong thời gian đo nhưng không có trong số node. Thời gian đo phụ thuộc máy.
Kết quả sức chơi chỉ áp dụng cho bộ khai cuộc và đối thủ đã thử.

Mã nguồn dùng bitboard bằng số nguyên Python để biểu diễn bàn 6×7.
Transposition Table nằm ngoài phạm vi của bản này.
