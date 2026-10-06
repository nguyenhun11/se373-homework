# Hướng dẫn thực hiện Homework 2 trên Windows

Tài liệu này hướng dẫn các bước chạy và chụp kết quả cho bài Issue Triage. Không cần sửa mã nguồn mẫu.

## 1. Trạng thái hiện tại

Môi trường `.venv` trong thư mục demo đã có các thư viện cần thiết: `openai`, `pydantic`, `python-dotenv`, `tiktoken` và `streamlit`.

- Có thể chạy ngay Demo 01 vì demo này không gọi API.
- Để chạy Demo 00, 02, 03 và 04, cần tự tạo file `.env` và điền thông tin API của provider. File `.env` hiện chưa tồn tại.

## 2. Mở terminal đúng thư mục

Mở PowerShell trong VS Code hoặc Windows Terminal, sau đó chạy:

```powershell
cd "D:\2.Study\SE373.AI\Homework2\Demo Issue Triage-20260919"
```

Lệnh `cd` nghĩa là chuyển terminal đến thư mục chứa các file Python của demo.

## 3. Cú pháp chạy Python trên Windows

Có hai cách tương đương.

### Cách A — kích hoạt virtual environment

Đây là cách dễ dùng nhất khi mới học Python:

```powershell
.\.venv\Scripts\Activate.ps1
python --version
python 01_measure_tokens.py
```

Sau khi kích hoạt, đầu dòng terminal thường xuất hiện `(.venv)`. Từ đó, `python` là Python trong môi trường bài tập.

Nếu PowerShell báo không cho chạy `Activate.ps1`, dùng lệnh sau **chỉ trong cửa sổ terminal đang mở**, rồi kích hoạt lại:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Cách B — không kích hoạt môi trường

Gọi trực tiếp Python nằm trong `.venv`. Cách này hữu ích nếu không muốn thay đổi execution policy:

```powershell
.\.venv\Scripts\python.exe 01_measure_tokens.py
```

Mẫu tổng quát là:

```powershell
python ten_file.py
python ten_file.py --ten-tham-so "gia tri"
```

Ví dụ truyền issue tùy chỉnh:

```powershell
python 00_minimal_triage.py --issue "API đăng nhập trả HTTP 503 cho toàn bộ người dùng từ 09:15."
```

## 4. Tạo cấu hình API trước các demo cần model

Không chạy lệnh này nếu bạn chưa có API key/model từ provider. Khi đã có, ở đúng thư mục demo chạy:

```powershell
Copy-Item .env.example .env
notepad .env
```

Điền ba giá trị thật vào file `.env`:

```dotenv
OPENAI_API_KEY=API_key_cua_ban
OPENAI_BASE_URL=https://dia-chi-api-openai-compatible/v1
OPENAI_MODEL=model-id-cua-provider
```

Lưu file rồi đóng Notepad. Không đăng `.env` lên Google Drive công khai và không chụp API key trong screenshot.

Provider phải hỗ trợ OpenAI-compatible API. Demo 02 cần structured output; Demo 03 và 04 cần tool/function calling. Vì vậy một model có thể chạy Demo 00 nhưng không nhất thiết chạy được tất cả các demo sau.

## 5. Chạy từng demo và cần chụp gì

### Demo 00 — LLM call tối thiểu

```powershell
python 00_minimal_triage.py
```

Chụp câu trả lời văn bản của model cho issue. Đây là bằng chứng API, endpoint và model ID hoạt động.

### Demo 01 — Đếm token, không cần API

```powershell
python 01_measure_tokens.py
```

Chụp hai dòng kết quả có `cl100k_base` và `o200k_base`, cùng số token EN, VI và ratio.

### Demo 02 — Structured output

```powershell
python 02_structured_output.py
```

Chụp cả hai phần:

1. `Prompt-only response` — JSON mà model tự tạo từ prompt.
2. `Constrained structured response` — object `IssueTriage` đã qua schema/validation.

### Demo 03 — Function calling

```powershell
python 03_function_calling.py
```

Chụp đủ chuỗi trace:

```text
1. Model đề xuất tool call
2. Application thực thi
3. Tool result quay lại model
Final response
```

Đây là phần quan trọng để cho thấy model chỉ đề xuất lời gọi hàm, còn application kiểm tra dữ liệu rồi mới tra team phụ trách.

### Demo 04 — Giao diện Streamlit

```powershell
streamlit run 04_streamlit_triage.py --server.headless true
```

Terminal sẽ in một `Local URL`, thường dạng `http://localhost:8501`. Mở địa chỉ đó trong trình duyệt, bấm **Phân loại issue**, rồi chụp:

- phần issue đã nhập;
- component đã xác thực;
- team phụ trách;
- expander `Trace function calling` đang mở;
- kết quả triage cuối cùng.

Giữ terminal này mở trong lúc dùng giao diện. Nhấn `Ctrl + C` tại terminal để dừng Streamlit.

## 6. Thứ tự nên thực hiện

1. Mở PowerShell và `cd` vào thư mục demo.
2. Kích hoạt `.venv`.
3. Chạy Demo 01 trước để xác nhận Python/thư viện hoạt động.
4. Tạo và cấu hình `.env` khi đã có thông tin provider.
5. Chạy Demo 00 để kiểm tra kết nối model.
6. Chạy tiếp Demo 02, Demo 03, Demo 04; chụp ảnh từng kết quả.
7. Tải source code lên Google Drive, bảo đảm quyền `Anyone with the link`/công khai theo yêu cầu lớp học, nhưng loại trừ `.env`.
8. Tạo một PDF gồm link Drive và các ảnh chụp có ghi rõ Demo 00–04.

## 7. Lỗi phổ biến

| Hiện tượng | Cách xử lý |
| --- | --- |
| `python is not recognized` | Dùng `py --version` để kiểm tra Python, hoặc chạy theo Cách B với `.\.venv\Scripts\python.exe`. |
| `OPENAI_API_KEY is required` | Tạo `.env` từ `.env.example`, điền key rồi lưu file. |
| `OPENAI_MODEL is required` | Điền model ID hợp lệ vào `.env`. |
| `model_not_found` hoặc `No active credentials` | Kiểm tra lại model ID/quyền truy cập ở provider. |
| Demo 03 không có tool call | Dùng provider/model hỗ trợ OpenAI-compatible function calling. |
| Port 8501 đã dùng | Dừng Streamlit cũ bằng `Ctrl + C`, hoặc chạy thêm `--server.port 8502`. |
| Streamlit hỏi Email | Dùng `--server.headless true`, hoặc để trống và Enter. |

## 8. Checklist PDF nộp bài

- [ ] Link Google Drive source mở được cho người chấm.
- [ ] Drive không có `.env`/API key.
- [ ] Có screenshot Demo 00.
- [ ] Có screenshot Demo 01.
- [ ] Có screenshot Demo 02.
- [ ] Có screenshot Demo 03, nhất là tool trace.
- [ ] Có screenshot Demo 04 trên trình duyệt.
- [ ] Tất cả được đặt trong **một file PDF**.

