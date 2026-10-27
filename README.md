# Issue Triage + Challenge A: Bộ nhớ dài hạn (Persistent Memory)

Dự án mở rộng agent **Issue Triage** hiện có bằng cách bổ sung cơ chế **lưu trữ bộ nhớ dài hạn trên file** (*file-backed persistent memory*). Các thành phần ban đầu như schema phân loại sự cố, quy trình gọi hàm (*function calling*) và cơ chế xác thực nhóm phụ trách vẫn được giữ nguyên.

## 1. Các thay đổi chính

- **`persistent_memory.py`**: Đọc và ghi các quy ước của dự án vào `project_memory.json`. Dữ liệu được ghi theo cơ chế nguyên tử (*atomic write*) và lưu lại lịch sử khi một quy ước được thay đổi.
- **`triage_workflow.py`**: Nạp bộ nhớ đã lưu thông qua harness và chèn nội dung bộ nhớ vào system message trong mỗi yêu cầu gửi đến model. Schema `IssueTriage` và cơ chế xác thực tool vẫn được giữ nguyên.
- **`app.py`**: Hiển thị các quy ước đã lưu ở thanh bên của giao diện Streamlit, đồng thời cho phép người dùng thêm hoặc cập nhật quy ước.
- **`test_persistent_memory.py`**: Kiểm thử khả năng duy trì dữ liệu sau khi tải lại, cập nhật quy ước, loại bỏ các bản ghi trùng lặp và chèn bộ nhớ vào lời nhắc của model bằng client giả lập (*fake client*), không cần gọi API.

## 2. Cài đặt và cấu hình

Tạo môi trường ảo và cài đặt các thư viện cần thiết:

```bash
python -m venv .venv
```

Trên Windows PowerShell, kích hoạt môi trường ảo:

```powershell
.venv\Scripts\Activate.ps1
```

Cài đặt các thư viện từ `requirements.txt`:

```bash
python -m pip install -r requirements.txt
```

Tạo file `.env` từ file mẫu:

```powershell
Copy-Item .env.example .env
```

Mở file `.env` và cấu hình endpoint tương thích với OpenAI API, tên model và API key hợp lệ.

**Lưu ý:** Không đưa file `.env` chứa API key lên Git hoặc đưa vào gói nộp bài. Chỉ chia sẻ `.env.example` với các biến môi trường mẫu, không chứa thông tin bí mật.

## 3. Hướng dẫn trình diễn Challenge A

Để thực hiện triage thực tế, dự án cần được cấu hình model hợp lệ. Tuy nhiên, các thao tác lưu, đọc và cập nhật bộ nhớ không cần gọi model, nên có thể kiểm tra mà không tiêu tốn quota API.

### Bước 1: Xem bộ nhớ hiện tại

```bash
python triage_workflow.py --show-memory
```

Lệnh này hiển thị các quy ước đã lưu trong bộ nhớ dự án.

### Bước 2: Lưu một quy ước và kiểm tra khả năng duy trì dữ liệu

```bash
python triage_workflow.py --remember "severity_policy=When a payment outage affects all users, classify it as P1 unless evidence suggests otherwise."
python triage_workflow.py --show-memory
```

Thoát khỏi tiến trình hiện tại rồi chạy lại lệnh `--show-memory`.

Nếu quy ước vẫn còn sau khi khởi động lại, điều đó chứng minh dữ liệu đã được lưu trên đĩa trong `project_memory.json`, thay vì chỉ tồn tại trong bộ nhớ tạm của tiến trình.

### Bước 3: Cập nhật quy ước hiện có

```bash
python triage_workflow.py --remember "severity_policy=Classify a payment outage as P1 only when the issue evidence confirms broad impact; otherwise ask for more information."
python triage_workflow.py --show-memory
```

Giá trị mới sẽ thay thế giá trị hiện tại của cùng một khóa. Lịch sử `history` ghi lại giá trị cũ và giá trị mới.

Trong lần triage tiếp theo, ứng dụng đọc lại bộ nhớ từ file và chèn quy ước mới nhất vào yêu cầu gửi đến model. Người dùng cũng có thể cập nhật quy ước trực tiếp từ thanh bên của giao diện Streamlit.

### Bước 4: Khởi chạy giao diện người dùng

```bash
python -m streamlit run app.py
```

Giao diện cho phép nhập mô tả sự cố, thực hiện triage và xem kết quả phân loại, nhóm phụ trách cũng như trace của quá trình gọi hàm. Các quy ước đã lưu cũng được hiển thị ở thanh bên.

## 4. Kiểm thử không cần API quota

Cài đặt `pytest` nếu chưa có:

```bash
python -m pip install pytest
```

Chạy toàn bộ kiểm thử:

```bash
python -m pytest -q
```

Các kiểm thử sử dụng fake client để xác minh vòng đời của bộ nhớ và việc đưa nội dung bộ nhớ đã lưu vào system message. Những kiểm thử này không cần gọi model thật và không tiêu tốn quota API.

**Giới hạn của kiểm thử:** Fake-client tests xác minh luồng xử lý trong ứng dụng, nhưng không chứng minh model thật luôn tuân thủ các quy ước được cung cấp. Khi trình diễn với model thật, có thể cho xem bộ nhớ đã được chèn vào yêu cầu và so sánh kết quả triage trước và sau khi cập nhật quy ước.

## 5. Các quyết định thiết kế

- **Lưu trữ (Storage):** Sử dụng file JSON để lưu bộ nhớ dự án ở quy mô nhỏ. Định dạng này dễ đọc, dễ kiểm tra và thuận tiện cho việc gỡ lỗi.
- **Cập nhật (Writer):** Người dùng chủ động thêm hoặc sửa quy ước thông qua CLI hoặc giao diện. Cách này tránh tự động biến những phát biểu hội thoại bất kỳ thành quy tắc dài hạn.
- **Truy xuất (Retrieval):** Đọc bộ nhớ từ file trong mỗi lượt triage, thay vì phụ thuộc hoàn toàn vào trạng thái bộ nhớ tạm của tiến trình.
- **Cập nhật và xử lý thay đổi (Conflict/Update Handling):** Mỗi khóa có một giá trị hiện hành. Khi cập nhật, giá trị cũ được thay thế và lịch sử thay đổi được ghi lại.
- **Thứ tự ưu tiên (Priority):** Bộ nhớ cung cấp ngữ cảnh cho các quyết định đặc thù của dự án, nhưng không được phép ghi đè schema đầu ra Pydantic, cơ chế xác thực tool hoặc các ràng buộc cốt lõi trong system prompt.

## 6. Kết luận

Triển khai này bổ sung cơ chế lưu trữ và truy xuất bộ nhớ dài hạn cho Challenge A, cho phép các quy ước của dự án được duy trì qua nhiều lần chạy ứng dụng và được đưa vào ngữ cảnh của các lượt triage tiếp theo.

Đồng thời, triển khai vẫn giữ nguyên quy trình Issue Triage ban đầu, bao gồm phân loại sự cố theo schema, gọi hàm có kiểm soát bởi ứng dụng và xác thực kết quả tool.

## 7. Challenge B: Context Management

Hai trình diễn trong `challenge_b.py` dùng cùng cấu hình API tương thích OpenAI ở mục 2. Cần cài các gói trong `requirements.txt`, cấu hình `.env` và dùng model/provider hỗ trợ Chat Completions và function calling. Các lệnh gọi model có thể tiêu tốn quota API.

### B1: Selective compaction

```bash
python3 challenge_b.py b1
```

Chương trình tạo một phiên điều tra có lịch sử dài. Khi kích thước lịch sử đạt ngưỡng 4.000 ký tự, ứng dụng yêu cầu model tóm tắt các lượt cũ thành checkpoint gồm sự cố, bằng chứng, các bước đã thử, ràng buộc và bước tiếp theo. System message và lượt gần nhất được giữ lại; sau đó model trả lời câu hỏi dựa trên checkpoint.

Kết quả hiển thị checkpoint, câu trả lời, số ký tự trước/sau, `summary_prompt_tokens` và `followup_prompt_tokens` từ `usage.prompt_tokens` nếu provider cung cấp. Ngưỡng ký tự là phép ước lượng đơn giản, không phải số token hoặc giới hạn context của model. Lượt tạo checkpoint cũng tiêu tốn token; số token của lượt sau không phải tổng chi phí phiên. Kiểm tra thủ công câu trả lời có giữ đúng lỗi HTTP 500, các kiểm tra đã làm, ràng buộc không restart production và bước kiểm tra database hay không. Tóm tắt do model tạo có thể bỏ sót hoặc sai thông tin; nếu tóm tắt rỗng hay không ngắn hơn, lịch sử gốc không bị thay thế.

Đây là compaction do ứng dụng tự thực hiện, không phải API compaction tích hợp của OpenAI. Với phiên thực tế, nên chọn ngưỡng có dự phòng cho câu trả lời và giới hạn của model/provider.

### B2: Xử lý log tại máy

```bash
python3 challenge_b.py b2
python3 challenge_b.py b2 --logs sample_logs --question "How many payment errors and HTTP 500 responses are there?"
```

Model gọi `analyze_logs` với từ khóa; Python đọc tuần tự các file `.log` trực tiếp trong thư mục được chỉ định và chỉ gửi số lượng dòng khớp, mức log và mã HTTP tổng hợp cho model. Với dữ liệu mẫu, toàn bộ ba file có 4 dòng ERROR và 3 dòng HTTP 500. Lệnh in câu trả lời, thống kê và `prompt_tokens` của từng lượt API; giá trị `null` nghĩa là provider không trả về usage. Dữ liệu log thô không được gửi trong các yêu cầu model, nhưng câu hỏi và từ khóa được gửi. Chương trình không thực thi code do model sinh ra.

Tool chỉ hỗ trợ lọc theo một chuỗi không phân biệt chữ hoa/thường và đếm mức `DEBUG`, `INFO`, `WARN`, `WARNING`, `ERROR`, `FATAL` cùng mã sau `HTTP`; các câu hỏi ngoài thống kê này có thể không trả lời được. Dùng thư mục chứa log mẫu hoặc dữ liệu được phép phân tích.

### Kiểm thử Challenge B không cần API

```bash
python3 -m unittest test_challenge_b -v
```

Các kiểm thử dùng client giả lập để kiểm tra ngưỡng, giữ lịch sử khi tóm tắt thất bại, xử lý nhiều file và không gửi dòng log thô tới model. Chúng không chứng minh chất lượng tóm tắt hay câu trả lời của model thật.
