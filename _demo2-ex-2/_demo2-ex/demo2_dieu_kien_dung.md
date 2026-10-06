SE373 · Demo 2 · Slide 34–41

# Khi nào AI agent phải dừng?

Đọc từng bước file `demo2_dieu_kien_dung.py`: cùng model, câu hỏi và tool; chỉ thay **điều kiện dừng**, kết quả chuyển từ lặp tốn tiền sang dừng đúng chỗ và bàn giao đủ thông tin.

> “Ngày mai giao hàng ở Vũng Tàu có mưa không? Nếu mưa thì dời sang ngày kia.”

**Sau bài này, bạn giải thích được:**

* Vì sao agent rơi vào vòng lặp.
* Ba cơ chế dừng khác nhau ở đâu.
* Middleware bắt vòng lặp tại V4 thế nào.
* Vì sao dừng phải đi kèm bàn giao.

[Bức tranh lớn](#buc-tranh)
[Nguyên nhân](#nguyen-nhan)
[Đọc code](#doc-code)
[Ba chế độ](#ba-che-do)
[LoopDetector](#loop-detector)
[Bàn giao](#ban-giao)
[Tổng kết](#tong-ket)

01

Mental model

## Một vòng chạy của agent

Agent không phải một lần gọi model. Nó là vòng lặp **model → tool → observation → model**. Muốn hệ thống an toàn, vòng lặp phải có đường thoát rõ ràng.

Luồng thực thi bên trong create\_agent()
Đường đỏ = dừng bất thường

Vòng lặp thực thi của LangGraph agent
Người dùng gửi câu hỏi cho model. Sau mỗi quyết định của model, router và middleware chọn gọi tool, trả lời bình thường, hoặc dừng bất thường và bàn giao.

1
HUMAN
Đặt câu hỏi
Tạo HumanMessage

2
MODEL
Đề xuất bước kế
AIMessage(...)

AFTER\_MODEL
Router +
middleware
chọn đường tiếp theo

3
TOOL
Thực thi hành động
weather\_forecast(...)

KẾT THÚC BÌNH THƯỜNG
Trả lời cuối → END

DỪNG BẤT THƯỜNG
Báo lý do + bàn giao → END
LoopDetector phát hiện lặp

GỌI TOOL

KHÔNG GỌI TOOL

CÓ CẢNH BÁO

ToolMessage / observation

Vuốt ngang để xem trọn sơ đồ →

**Dừng bình thường**Model không gọi tool nữa và tạo câu trả lời cuối.

**Dừng theo ngân sách**Số lần gọi model đã chạm trần định trước.

**Dừng bất thường**Phát hiện lặp/bế tắc; cần báo lý do và bàn giao.

02

Root cause

## Vì sao ví dụ này chắc chắn lặp?

Không phải vì LangGraph “bị lỗi”. Dữ liệu thiếu, observation nghèo thông tin và model giả luôn chọn gọi lại tool tạo thành chuỗi nguyên nhân hoàn chỉnh.

**Vũng Tàu không có dữ liệu**
`THOI_TIET` không có mục Vũng Tàu.

dẫn đến

**Tool chỉ báo “not found”**
Không có mã lỗi, gợi ý hay danh sách tên hợp lệ.

vì vậy

**Model đổi cách viết rồi thử lại**
Không có hướng mới, model chỉ còn cách đổi tên và gọi lại.

```
# demo2_dieu_kien_dung.py:26–27
os.environ.setdefault("SE373_LOI_TE", "1")

# tools_dulich.py:77–79
if _loi_te():
    return {"error": "not found"}
```

Điểm cần nhớ

### Observation là giao diện điều khiển của agent

Thông báo lỗi tốt phải giúp model quyết định hành động kế tiếp. Chuỗi `{"error":"not found"}` chỉ mô tả thất bại, không đưa ra lối thoát.

**Observation tốt hơn trong chính bộ tool**`town_not_found` + gợi ý gọi `search_travel_info` + ví dụ tên hợp lệ.

03

Walkthrough

## Đọc file theo đúng thứ tự thực thi

Không đọc từ trên xuống một cách máy móc. Theo luồng chạy từ `main()`, qua `chay()`, tới agent và middleware.

1

### `main()` nhận chế độ từ dòng lệnh · dòng 151–155

Tham số `--che-do` chỉ nhận một trong ba giá trị. Giá trị được chuyển thẳng vào `chay(...)`.

```
153p.add_argument("--che-do", default="khong-gioi-han",
154    choices=["khong-gioi-han", "ngan-sach", "phat-hien-lap"])
155chay(p.parse_args().che_do)
```

2

### Tạo cùng model và cùng tool · dòng 91–94

`ModelGia(kich_ban="lap")` luôn sinh lời gọi `weather_forecast`. `tools_langchain()` bọc các hàm Python thành tool cho agent.

```
91def chay(che_do: str) -> None:
92    model = ModelGia(kich_ban="lap")
93    tools = tools_langchain()
95    middleware, config = [], {}
```

**Thiết kế thí nghiệm:** model, câu hỏi và tool là biến kiểm soát; middleware/config là biến độc lập. Vì vậy khác biệt đầu ra đến từ điều kiện dừng.

3

### Chọn “phanh” cho vòng lặp · dòng 96–103

**Không giới hạn riêng**`recursion_limit=36` chỉ là chặn cứng cuối cùng.

**Ngân sách**`run_limit=8` giới hạn số lần gọi model.

**Phát hiện lặp**Middleware tự viết quan sát từng `tool_call`.

4

### Dựng và chạy agent · dòng 105–112

`create_agent` ghép model, tool và middleware thành graph. `invoke` khởi động graph bằng một Human message.

```
105agent = create_agent(model=model, tools=tools, middleware=middleware)
112kq = agent.invoke(
    {"messages": [{"role": "user", "content": CAU_HOI}]}, config
)
```

5

### Xử lý hai kiểu kết thúc · dòng 111–131

Nếu graph chạm trần cứng, khối `except` in `GraphRecursionError`. Nếu middleware kết thúc graph có kiểm soát, chương trình in toàn bộ phiên và lý do dừng.

**Ngoại lệ**Biết graph bị chặn, nhưng không biết vòng nào bắt đầu hỏng.

**Kết quả có cấu trúc**Còn giữ lịch sử message và báo cáo bàn giao.

6

### `_in_phien()` biến message thành trace · dòng 134–148

Hàm duyệt theo `m.type`: Human, AI có `tool_calls`, Tool, rồi AI trả lời. Biến `vong` chỉ tăng khi AI đề xuất tool, nên sinh viên nhìn được V1, V2, V3…

**Đây là phần trình bày, không phải cơ chế dừng.**Sửa `_in_phien()` chỉ đổi log; không thay đổi hành vi agent.

04

Controlled experiment

## So sánh ba chế độ dừng

Chọn từng chế độ để xem agent chạy đến đâu, biết được gì và để lại gì cho người xử lý tiếp.

1 · Không giới hạn riêng
2 · Ngân sách 8 lượt
3 · Phát hiện lặp

Phanh khẩn cấp

### `recursion_limit=36`

Agent không có điều kiện dừng nghiệp vụ. LangGraph cuối cùng ném `GraphRecursionError` để bảo vệ tiến trình.

Lãng phí: rất cao

Dừng xác định?
:   Không theo nghiệp vụ

Chẩn đoán?
:   Rất ít

Bàn giao?
:   Không

```
# Nhánh else · dòng 100–103
config = {"recursion_limit": 36}

# Kết cục
except Exception as e:
    print(type(e).__name__)  # GraphRecursionError

# Ta chỉ biết: graph đã vượt trần.
# Ta không biết: hành vi hỏng bắt đầu ở vòng nào.
```

Cầu chì chi phí

### `ModelCallLimitMiddleware(run_limit=8)`

Agent dừng tại ngân sách cố định, không phụ thuộc model có “tự giác” dừng hay không.

Lãng phí: được giới hạn

Dừng xác định?
:   Có

Chẩn đoán?
:   Chỉ biết hết lượt

Bàn giao?
:   Không đủ

```
# dòng 96–97
if che_do == "ngan-sach":
    middleware = [
        ModelCallLimitMiddleware(
            run_limit=8,
            exit_behavior="end"
        )
    ]

# Tốt: hóa đơn có trần.
# Thiếu: không giải thích được nguyên nhân.
```

Dừng theo ngữ nghĩa

### `PhatHienLapMiddleware()`

Agent dừng ngay khi cùng cặp `(tool, args)` xuất hiện lần thứ hai trong cửa sổ gần nhất.

Lãng phí: thấp

Dừng xác định?
:   Có, tại V4

Chẩn đoán?
:   Có lý do cụ thể

Bàn giao?
:   Đủ 4 trường

```
# dòng 98–99
elif che_do == "phat-hien-lap":
    middleware = [PhatHienLapMiddleware()]

# Khi V4 lặp lại V1:
{
  "jump_to": "end",
  "messages": [AIMessage(content=bao_cao)]
}
```

| Cơ chế | Nó trả lời câu hỏi nào? | Điểm mạnh | Điểm mù |
| --- | --- | --- | --- |
| **Recursion limit** | Graph có chạy quá lâu không? | Chặn sự cố vô hạn | Không hiểu nghiệp vụ |
| **Call budget** | Đã tiêu hết bao nhiêu lượt? | Chi phí dự đoán được | Không biết vì sao bế tắc |
| **Loop detector** | Agent có lặp hành động không? | Dừng sớm, có chẩn đoán | Cần quy tắc đúng với nghiệp vụ |

05

Core mechanism

## LoopDetector bắt vòng lặp tại V4

Dấu vân tay của một hành động là `(tên tool, args đã sắp xếp)`. Chỉ khác cách viết địa danh thì là hành động khác; quay lại đúng `Vung Tau` thì trùng.

V1

**Thử lần đầu**`town='Vung Tau'`Lưu dấu vân tay

V2

**Đổi dấu**`town='Vũng Tàu'`Chưa trùng args

V3

**Thêm “City”**`town='Vung Tau City'`Chưa trùng args

V4

**Quay lại V1**`town='Vung Tau'`Trùng → DỪNG

### Middleware chạy sau mỗi lần model quyết định

```
# dòng 57–64
@hook_config(can_jump_to=["end"])
def after_model(self, state, runtime):
    cuoi = state["messages"][-1]
    if not getattr(cuoi, "tool_calls", None):
        return None

    for c in cuoi.tool_calls:
        canh_bao = self.det.check(
            c["name"], c["args"], progress=0
        )
```

### Ý nghĩa từng chi tiết

* `after_model`: kiểm tra trước khi tool thật sự chạy thêm một lần.
* `can_jump_to=["end"]`: khai báo hook được phép kết thúc graph.
* Không có `tool_calls`: model đã trả lời bình thường, middleware không can thiệp.
* `window=6`: chỉ nhớ sáu hành động gần nhất.
* `repeat_k=2`: lần xuất hiện thứ hai là đủ cảnh báo.
* `progress=0`: đại lượng tiến triển không đổi trong demo này.

Thuật toán trong after\_model()
Đường đỏ = kết thúc graph

Sơ đồ quyết định của LoopDetector
Middleware tạo dấu vân tay cho tool call, kiểm tra số lần lặp, rồi dừng graph hoặc cho phép gọi tool.

TOOL CALL MỚI
Tạo dấu vân tay
name + sorted(args)

Dấu vân tay
đã xuất hiện đủ
repeat\_k = 2?

CÓ · PHÁT HIỆN LẶP
jump\_to = "end"
Tạo báo cáo bàn giao

KHÔNG · CHƯA LẶP
return None
Cho graph tiếp tục gọi tool

CÓ

KHÔNG

Vuốt ngang để xem trọn sơ đồ →

**Vì sao so action thay vì observation?**
Hai observation giống nhau chưa chắc là lỗi. Ví dụ gọi `get_booking(id)` lặp lại để chờ trạng thái chuyển từ `pending` sang `confirmed` là polling hợp lệ. Quy tắc dừng phải gắn với ý nghĩa nghiệp vụ, không chỉ chuỗi dữ liệu.

06

Safe failure

## Dừng không có nghĩa là im lặng

Khi agent không hoàn tất được nhiệm vụ, đầu ra hữu ích nhất là một gói bàn giao để người dùng hoặc nhân viên biết chuyện gì xảy ra và quyết định bước kế tiếp.

**1 · stop\_reason**Vì sao hệ thống dừng: cùng tool và tham số đã lặp lần thứ hai.

**2 · da\_thu**Chuỗi hành động đã thử: Vung Tau → Vũng Tàu → Vung Tau City → Vung Tau.

**3 · trang\_thai**Ảnh chụp trạng thái: số lần gọi tool, số kết quả dùng được.

**4 · cau\_hoi\_cho\_nguoi**Quyết định còn thiếu: dùng nguồn thay thế hay thông báo chưa hỗ trợ?

```
# dòng 67–77
bao_cao = ban_giao(
    ly_do=canh_bao,
    da_thu=self.da_thu,
    trang_thai={
        "so_lan_goi_tool": len(self.da_thu),
        "ket_qua_dung": 0
    },
    cau_hoi="Dùng nguồn nào thay thế, "
            "hay trả lời là chưa hỗ trợ?"
)
return {
    "jump_to": "end",
    "messages": [AIMessage(content=_in_ban_giao(bao_cao))]
}
```

Output kỳ vọng

### DỪNG BẤT THƯỜNG

LOOP · 'weather\_forecast' gọi 2 lần với cùng tham số trong 6 vòng gần nhất

---

**Đã thử:** đầy đủ bốn lời gọi.

**Trạng thái:** 4 lần gọi, 0 kết quả dùng được.

**Hỏi người:** chọn nguồn thay thế hay báo chưa hỗ trợ.

07

Takeaways

## Ba lớp bảo vệ nên đi cùng nhau

Không chọn một và bỏ hai. Mỗi lớp xử lý một loại rủi ro khác nhau.

Lớp cuối

### Trần cứng framework

Ngăn tiến trình chạy vô hạn khi mọi cơ chế khác thất bại.

Lớp chi phí

### Ngân sách model/tool

Đảm bảo chi phí và độ trễ không vượt giới hạn vận hành.

Lớp ngữ nghĩa

### Phát hiện lặp + bàn giao

Dừng sớm, giải thích đúng sự cố và giữ đủ ngữ cảnh để tiếp quản.

### Checklist khi viết agent thật

* Đặt ngân sách hữu hạn cho model và tool.
* Xác định dấu hiệu “có tiến triển” của nghiệp vụ.
* Phân biệt retry hợp lệ với hành động lặp vô ích.
* Thiết kế lỗi tool có mã, gợi ý và dữ liệu hợp lệ.
* Khi dừng bất thường, luôn trả báo cáo bàn giao.

Câu hỏi thảo luận

### Nếu observation được sửa tốt hơn thì sao?

Thử tắt `SE373_LOI_TE=1`. Tool sẽ gợi ý gọi `search_travel_info` và đưa ví dụ tên hợp lệ. Khi đó, sửa model để đổi chiến lược thay vì đổi cách viết tên.

**Mục tiêu:** chữa nguyên nhân gốc bằng giao thức tool tốt; vẫn giữ điều kiện dừng như lớp bảo vệ.

**Một câu để nhớ**
“Agent an toàn không chỉ biết làm tiếp; nó còn biết khi nào phải dừng, vì sao dừng và bàn giao điều gì.”

Tài liệu học kèm `demo2_dieu_kien_dung.py` · Nội dung bám theo các dòng code và hành vi của model/tool giả lập.