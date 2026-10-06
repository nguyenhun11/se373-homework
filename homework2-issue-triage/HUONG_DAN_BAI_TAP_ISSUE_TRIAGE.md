# Giải thích bài tập Homework 2 — Issue Triage

Tài liệu này giải thích mã nguồn trong thư mục `Demo Issue Triage-20260919` và tóm tắt đúng phần việc cần nộp. Tài liệu không thay thế code, không chứa API key và không yêu cầu sửa code mẫu.

## 1. Mục tiêu và sản phẩm phải nộp

Theo `_Task.md`, sinh viên cần:

1. Xem và hiểu demo Issue Triage.
2. Thực hiện lại các demo theo hướng dẫn trong `demo-guide.html`.
3. Nộp **một file PDF**, gồm:
   - link Google Drive chứa mã nguồn, đặt quyền chia sẻ công khai (người chấm mở được không cần xin quyền);
   - ảnh chụp kết quả chạy demo.

Nên chụp ít nhất các bằng chứng sau:

| Phần | Cần thấy trong ảnh |
| --- | --- |
| Demo 00 | câu trả lời phân loại issue từ model |
| Demo 01 | số token EN/VI cho `cl100k_base` và `o200k_base` |
| Demo 02 | cả phần prompt-only và JSON `IssueTriage` đã parse |
| Demo 03 | tool call, kết quả application thực thi và final response |
| Demo 04 | giao diện Streamlit, component và team phụ trách; phần trace nên được mở |

Không chụp hoặc đưa `OPENAI_API_KEY` vào PDF, ảnh chụp, Git/Drive hay source code.

## 2. Ý tưởng chung của demo

**Issue triage** là bước đọc mô tả lỗi để xác định mức độ nghiêm trọng, thành phần bị ảnh hưởng và nhóm cần xử lý. Ví dụ lỗi nút thanh toán trả HTTP 500 cho mọi thẻ Visa là lỗi thuộc `payment`, có thể cần mức độ ưu tiên cao.

Năm demo tăng dần từ gọi model đơn giản đến một giao diện web:

```text
Demo 00: LLM trả văn bản tự do
Demo 01: Đếm token offline, không cần API
Demo 02: Ép kết quả về JSON có schema
Demo 03: Model yêu cầu tool → ứng dụng kiểm tra/chạy tool → model trả lời cuối
Demo 04: Đưa luồng Demo 03 vào giao diện Streamlit
```

## 3. Cấu trúc thư mục và vai trò từng file

| File | Vai trò |
| --- | --- |
| `requirements.txt` | Danh sách thư viện: `openai`, `pydantic`, `python-dotenv`, `tiktoken`, `streamlit`. |
| `.env.example` | Mẫu cấu hình API. Phải sao chép thành `.env` ở máy cá nhân và điền giá trị thật, không commit/chia sẻ file này. |
| `demo_common.py` | Hàm dùng chung để đọc biến môi trường, lấy model ID và tạo `OpenAI` client. |
| `00_minimal_triage.py` | Demo gọi LLM cơ bản, trả về văn bản tự do. |
| `01_measure_tokens.py` | Demo offline so sánh token tiếng Anh và tiếng Việt. |
| `02_structured_output.py` | So sánh JSON do prompt yêu cầu với structured output đã được schema kiểm tra. |
| `triage_workflow.py` | Lõi function calling: định nghĩa tool, xác thực dữ liệu và điều phối hai lần gọi model. |
| `03_function_calling.py` | Chương trình dòng lệnh in trace của `triage_workflow.py`. |
| `04_streamlit_triage.py` | Giao diện Streamlit sử dụng lại `triage_workflow.py`. |
| `demo-guide.html` | Hướng dẫn chính thức về cách chuẩn bị, chạy từng demo và xử lý lỗi thông thường. |

## 4. Cấu hình dùng chung: `demo_common.py`

File này tránh việc lặp lại phần cấu hình trong các demo.

- `load_environment()` đọc `.env` ở repository root và trong thư mục demo. Nó không ghi đè biến môi trường đã có của hệ điều hành.
- `model_name()` lấy `OPENAI_MODEL`. Nếu thiếu, chương trình dừng với lỗi giải thích rõ cần cấu hình model.
- `openai_client()` lấy `OPENAI_API_KEY` và `OPENAI_BASE_URL`, rồi tạo `OpenAI(api_key=..., base_url=...)`. Nếu thiếu key hoặc URL thì báo lỗi.

Ba biến trong `.env` có ý nghĩa:

```dotenv
OPENAI_API_KEY=API_key_cua_ban
OPENAI_BASE_URL=https://dia_chi_API_openai_compatible/v1
OPENAI_MODEL=model-id-ma-provider-cho-phep
```

`OPENAI_BASE_URL` và `OPENAI_MODEL` là bắt buộc. Provider phải hỗ trợ API tương thích OpenAI; riêng Demo 02 và 03 còn đòi hỏi các khả năng tương ứng ở model/provider.

## 5. Giải thích từng demo

### Demo 00 — `00_minimal_triage.py`

Chương trình nhận đối số `--issue`; nếu không truyền thì dùng issue thanh toán mẫu. Nó gửi hai message cho API:

1. `system`: giao vai trò hỗ trợ phân loại issue phần mềm.
2. `user`: nội dung issue.

Sau đó lệnh `client.chat.completions.create(...)` gọi model và in `response.choices[0].message.content`.

Ý nghĩa: đây là phép kiểm tra cơ bản nhất cho API key, base URL, model ID và kết nối. Kết quả là văn bản tự do, nên chưa có cấu trúc chắc chắn để chương trình khác xử lý.

Ví dụ Windows PowerShell sau khi môi trường đã được kích hoạt:

```powershell
python 00_minimal_triage.py
python 00_minimal_triage.py --issue "API đăng nhập trả HTTP 503 cho toàn bộ người dùng từ 09:15."
```

### Demo 01 — `01_measure_tokens.py`

Demo định nghĩa một đoạn tiếng Anh và một đoạn tiếng Việt có cùng ý nghĩa. Với mỗi tokenizer `cl100k_base` và `o200k_base`, mã:

1. Lấy tokenizer bằng `tiktoken.get_encoding(name)`.
2. Mã hóa từng đoạn với `encoding.encode(...)`.
3. Đếm số phần tử token bằng `len(...)`.
4. In số token tiếng Anh, tiếng Việt và tỉ lệ `VI / EN`.

Điểm quan trọng: demo này **không gửi request đến API**, nên không cần API key hợp lệ. Nó minh họa rằng số token phụ thuộc tokenizer và ngôn ngữ; token không tương đương trực tiếp với số từ hoặc số ký tự.

```powershell
python 01_measure_tokens.py
```

### Demo 02 — `02_structured_output.py`

Lớp Pydantic `IssueTriage` là hợp đồng dữ liệu giữa ứng dụng và model:

- `status` chỉ nhận `classified`, `insufficient_data` hoặc `out_of_scope`.
- `severity` chỉ nhận `P0` đến `P3`, hoặc `null`.
- `component` là chuỗi hoặc `null`.
- `needs_urgent_response` là boolean, mặc định `False`.
- `reason` bắt buộc có.
- `ConfigDict(extra="forbid")` cấm các trường thừa.

Script gọi model hai lần với cùng prompt:

1. `chat.completions.create(...)`: chỉ dùng câu nhắc “trả về JSON”. Model vẫn có thể thêm Markdown, thêm trường, sai tên trường hoặc sai kiểu dữ liệu.
2. `client.beta.chat.completions.parse(..., response_format=IssueTriage)`: yêu cầu provider trả kết quả theo schema và SDK parse/validate thành object `IssueTriage`.

Cuối cùng `model_dump_json(indent=2)` in JSON đã xác thực. Đây là lý do structured output phù hợp hơn khi chương trình cần dùng kết quả một cách tin cậy.

```powershell
python 02_structured_output.py
```

Provider/model phải hỗ trợ structured output theo OpenAI-compatible API; nếu không, Demo 00 có thể chạy nhưng Demo 02 vẫn có thể lỗi.

### Demo 03 — `triage_workflow.py` và `03_function_calling.py`

Đây là phần trung tâm của bài. Model **không tự thực thi** hàm; model chỉ đề xuất gọi hàm. Ứng dụng kiểm soát việc có cho phép lời gọi đó hay không.

`triage_workflow.py` định nghĩa bảng dữ liệu cục bộ:

```text
payment  → checkout-platform
identity → identity-platform
search   → search-platform
```

Tool `get_component_owner` có JSON Schema giới hạn `component` chỉ thuộc ba giá trị trên. `strict: True` làm schema chặt chẽ hơn.

Luồng `triage_issue(...)`:

```text
Issue người dùng + system prompt
          ↓
Lần gọi model thứ nhất, bắt buộc đề xuất tool (`tool_choice="required"`)
          ↓
Ứng dụng nhận tool call
          ↓
`execute_tool_call` kiểm tra: tên tool, JSON object, đúng một trường `component`, đúng kiểu str, component hợp lệ
          ↓
`get_component_owner` tra bảng dữ liệu cục bộ
          ↓
Ứng dụng gửi tool result lại vào message history
          ↓
Lần gọi model thứ hai
          ↓
Final response
```

Các `dataclass` hỗ trợ hiển thị kết quả:

- `ToolTrace`: lưu ID lời gọi, tên tool, arguments và kết quả thực thi.
- `TriageResult`: gồm toàn bộ trace và phần trả lời cuối.

`03_function_calling.py` chỉ là lớp CLI: gọi `triage_issue(...)`, rồi in rõ ba phần cần quan sát là lời gọi tool do model yêu cầu, lần thực thi của application, và tool result gửi lại model.

```powershell
python 03_function_calling.py
```

Provider/model phải hỗ trợ tool/function calling. Mã đã chủ động xác thực dữ liệu, vì không nên tin tool arguments từ model mà thực thi trực tiếp.

### Demo 04 — `04_streamlit_triage.py`

Demo này không viết lại logic triage mà import `triage_issue` từ `triage_workflow.py`. Việc dùng chung logic đảm bảo CLI ở Demo 03 và UI ở Demo 04 xử lý tool an toàn theo cùng một cách.

Giao diện gồm:

- sidebar hiển thị base URL và model đang cấu hình (không hiển thị API key);
- ô nhập mô tả issue và nút **Phân loại issue**;
- spinner trong lúc gọi model;
- hai chỉ số: component đã xác thực và team phụ trách;
- expander hiển thị trace function calling;
- final response của model.

Chương trình cũng kiểm tra người dùng đã nhập issue chưa, và bắt các exception để gợi ý kiểm tra URL, model và quyền truy cập.

```powershell
streamlit run 04_streamlit_triage.py --server.headless true
```

Mở `Local URL` mà Streamlit in ra. Giữ terminal đang chạy; nhấn `Ctrl + C` để dừng server.

## 6. Trình tự thực hiện bài trên Windows

Guide HTML dùng cú pháp macOS/Linux. Trên Windows PowerShell, dùng các lệnh tương đương dưới đây trong thư mục demo:

```powershell
cd "D:\2.Study\SE373.AI\Homework2\Demo Issue Triage-20260919"
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Sau đó mở `.env` bằng trình soạn thảo, điền API key, base URL và model ID. Không đưa file `.env` lên Drive công khai. Nếu PowerShell chặn việc activate, có thể dùng tạm cho **cửa sổ hiện tại**:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Chạy theo thứ tự `00`, `01`, `02`, `03`, `04`. Demo 01 có thể chạy ngay sau khi cài thư viện; bốn demo còn lại cần cấu hình API.

## 7. Checklist trước khi nộp PDF

- [ ] Đã chạy Demo 00 và có prose output.
- [ ] Đã chạy Demo 01 và có so sánh token EN/VI.
- [ ] Đã chạy Demo 02 và thấy JSON structured output hợp lệ.
- [ ] Đã chạy Demo 03 và thấy `tool_call → application execution → tool_result → final response`.
- [ ] Đã chạy Demo 04, nhập issue và thấy component/team/trace.
- [ ] Source trên Google Drive mở công khai được.
- [ ] Đã loại `.env`, API key, token và dữ liệu nhạy cảm khỏi Drive, ảnh chụp và PDF.
- [ ] PDF chứa link Drive và các screenshot rõ ràng, có nhãn Demo 00–04.

## 8. Lỗi được guide nêu và cách hiểu

| Thông báo / hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Streamlit hỏi email | Lần chạy đầu chưa dùng headless | Bỏ trống, Enter; hoặc dùng `--server.headless true`. |
| `Port 8501 is not available` | Một tiến trình Streamlit khác đang dùng cổng | Dừng tiến trình cũ bằng `Ctrl + C`, hoặc dùng `--server.port 8502`. |
| `No active credentials` / `model_not_found` | Sai model ID hoặc tài khoản không có quyền dùng model | Kiểm tra danh sách model của provider và dùng ID đầy đủ. |
| Demo 03 không gọi tool | Model/provider không hỗ trợ OpenAI-compatible function calling | Chọn model/provider hỗ trợ tool calling. |
| `OPENAI_* is required` | Chưa có `.env` hoặc thiếu biến | Sao chép `.env.example`, điền đủ key, base URL, model. |

## 9. Giới hạn bảo mật khi mở trong LAN

Guide có lệnh để mở Streamlit cho các thiết bị cùng mạng qua `--server.address 0.0.0.0`. Đây là tùy chọn, không bắt buộc cho bài. Chỉ dùng trên mạng tin cậy: API key vẫn nằm ở server, nhưng người mở URL có thể gửi issue khiến server gọi model bằng tài khoản của bạn.

