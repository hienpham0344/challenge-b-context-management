# Challenge B: Context Management

Dự án trình diễn hai kỹ thuật giúp agent xử lý phiên dài và nhiều log với lượng context gọn hơn:

- **B1 — Compact:** tạo checkpoint từ các lượt điều tra cũ khi lịch sử vượt ngưỡng; giữ system message và các lượt gần nhất.
- **B2 — Code Mode:** agent yêu cầu thống kê log qua tool giới hạn sẵn; Python đọc log tại máy và chỉ gửi kết quả tổng hợp cho model.

Dự án dùng lại ứng dụng Issue Triage và persistent memory từ Challenge A làm nền. B1 và B2 chạy riêng qua `challenge_b.py`.

## Cài đặt

Cần Python 3.10 trở lên. Tạo môi trường ảo và cài dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Trên Windows PowerShell, kích hoạt môi trường bằng:

```powershell
.venv\Scripts\Activate.ps1
```

Tạo `.env` từ file mẫu, rồi điền endpoint tương thích OpenAI, model và API key:

```bash
cp .env.example .env
```

Không commit hoặc chia sẻ `.env` có API key. Các demo B1/B2 gọi model thật nên có thể tiêu tốn quota.

## B1: Compact lịch sử điều tra

```bash
python challenge_b.py b1
```

Demo tạo một phiên điều tra lỗi thanh toán dài. Khi lịch sử đạt ngưỡng 4.000 ký tự, model tóm tắt các lượt cũ thành checkpoint gồm sự cố, bằng chứng, việc đã thử, ràng buộc và bước tiếp theo. Ứng dụng giữ lại system message và lượt gần nhất rồi tiếp tục hỏi model.

Kết quả hiển thị checkpoint, câu trả lời, kích thước lịch sử trước và sau compact, cùng `usage.prompt_tokens` nếu provider trả về. Ngưỡng ký tự chỉ là ước lượng, không phải số token. Token của lượt tạo checkpoint cũng được tính vào chi phí phiên. Nếu tóm tắt rỗng hoặc không làm lịch sử ngắn hơn, ứng dụng giữ nguyên lịch sử cũ.

Kiểm tra câu trả lời có giữ được lỗi HTTP 500, các bước kiểm tra đã thực hiện, ràng buộc không restart production và bước tiếp theo là kiểm tra database hay không. Tóm tắt do model tạo có thể bỏ sót hoặc làm sai chi tiết.

## B2: Code Mode phân tích log

Chạy trên log mẫu:

```bash
python challenge_b.py b2
```

Đặt câu hỏi hoặc chọn thư mục log khác:

```bash
python challenge_b.py b2 --logs sample_logs --question "How many payment errors and HTTP 500 responses are there?"
```

Model gọi tool `analyze_logs` với một từ khóa. Tool Python đọc tuần tự các file `.log` trong thư mục và chỉ trả về số dòng khớp, số lượng theo log level, mã HTTP và số file đã đọc. Log thô không được gửi tới model; câu hỏi và từ khóa vẫn được gửi. Model không được sinh hay thực thi lệnh tùy ý.

Với log mẫu, toàn bộ ba file có 4 dòng `ERROR` và 3 mã HTTP `500`. Kết quả hiển thị thống kê cùng `usage.prompt_tokens` của từng lượt API nếu provider cung cấp. Tool chỉ trả lời tốt các câu hỏi về số lượng dòng, log level và mã HTTP; nó không tìm kiếm nội dung log tùy ý ngoài lọc một từ khóa.

## Kiểm thử

Chạy kiểm thử không cần gọi API:

```bash
python -m unittest test_challenge_b -v
```

Hoặc chạy toàn bộ kiểm thử bằng pytest:

```bash
python -m pytest -q
```

Các kiểm thử dùng client giả lập và log tạm để xác minh ngưỡng compact, bảo toàn lịch sử khi compact thất bại, thống kê nhiều file và không đưa dòng log thô vào yêu cầu model. Chúng không đánh giá chất lượng câu trả lời của model thật.

## Challenge A: Issue Triage và persistent memory

`app.py` và `triage_workflow.py` cung cấp giao diện Issue Triage. `persistent_memory.py` lưu các quy ước dự án vào `project_memory.json`, ghi lịch sử cập nhật và chèn quy ước hiện hành vào system message ở mỗi lượt triage.

Xem bộ nhớ hoặc cập nhật một quy ước qua CLI:

```bash
python triage_workflow.py --show-memory
python triage_workflow.py --remember "severity_policy=Use P1 for widespread payment outages."
```

Khởi chạy giao diện Streamlit:

```bash
python -m streamlit run app.py
```
