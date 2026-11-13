# Connect Four | Explainable AI

Bản Python/Pygame độc lập cho đồ án Nhập môn Trí tuệ Nhân tạo.
Người chơi đấu với AI Alpha-Beta ở độ sâu 2, 4 hoặc 6.

## Cài và chạy trên Windows

Giải nén ZIP, mở thư mục `connect_four` trong VS Code rồi mở Terminal (PowerShell).
Dùng Python 3.12 và chạy:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Trên macOS hoặc Linux, tạo môi trường bằng `python3 -m venv .venv` rồi
dùng `.venv/bin/python` thay cho `.\.venv\Scripts\python.exe`.

## Kịch bản demo

| Thao tác | Nội dung trình bày |
|---|---|
| Click một cột | Người chơi thả quân vàng. AI thả quân đỏ và hiển thị phân tích. |
| F1 | AI thắng ngay ở cột 4. |
| F2 | AI chặn ở cột 4. Nếu AI chọn cột 3, người chơi thắng ngay ở cột 4. |
| F3 | Ở độ sâu mặc định 4, cột 4 có điểm Minimax 5, cột 7 có điểm 2. |
| 2 / 4 / 6 | Đổi độ sâu cho lần tìm kiếm kế tiếp. Chọn 4 trước khi trình diễn F3. |
| R / Esc | Ván mới / thoát. |

Điểm Minimax được tính từ góc nhìn AI, với giả định đối thủ chọn phản hồi
tốt nhất trong phạm vi độ sâu đã tìm. Từng nước ở gốc được tìm với cửa sổ
Alpha-Beta đầy đủ để lấy điểm chính xác **ở độ sâu đó**. Khi đồng điểm,
AI ưu tiên theo thứ tự cột 4, 3, 5, 2, 6, 1, 7. Điểm heuristic tĩnh sau
nước đi mô tả riêng bàn cờ ngay sau nước đó. Trong tìm kiếm, heuristic
được dùng để chấm các nút lá chưa kết thúc. Chiến thắng/thua được xử lý
trước heuristic, ưu tiên thắng sớm và trì hoãn thua.

## Thực nghiệm

```powershell
.\.venv\Scripts\python.exe experiment.py
```

Chạy lại lệnh sẽ cập nhật CSV trong `results/`.

| File | Nội dung |
|---|---|
| search.csv | 45 cấu hình gồm 5 bàn cờ, 3 độ sâu và 3 cấu hình tìm kiếm. Thời gian là trung vị của 3 lượt, tính bằng ms. |
| games.csv | 120 ván với Random và Greedy (Minimax sâu 1), dùng 10 seed và đổi bên trên cùng khai cuộc hai nước. |
| games_summary.csv | Tổng thắng, hòa, thua theo độ sâu và đối thủ. |
| explanations.csv | 8 tình huống kiểm tra nước đi, lý do, so sánh và tính nhất quán. |

Số node tính cả gốc và các lá đã duyệt. So sánh Minimax với Alpha-Beta
giữ nguyên heuristic, độ sâu và thứ tự duyệt. Dòng Alpha-Beta left first
đổi thứ tự duyệt để đo ảnh hưởng của move ordering. Benchmark thuật toán
đo quá trình chọn nước; phân tích GUI tìm thêm điểm cho từng phương án nên
có chi phí riêng. Thời gian đo phụ thuộc máy. Kết quả sức chơi chỉ áp dụng
cho bộ khai cuộc và đối thủ đã thử.

Mã nguồn dùng bitboard bằng số nguyên Python để biểu diễn bàn 6×7.
Pygame là thư viện cài thêm duy nhất. Transposition Table nằm ngoài phạm
vi của bản này.
