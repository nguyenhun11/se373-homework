# Project memory (generated from memory.json — do not edit)

## Active
- **revenue_column_alias**: Cột doanh thu trong kết quả truy vấn đặt alias là revenue_vnd.  _(since 2026-10-21T03:05:28+00:00, session s-20261021-100516-139821)_
- **month_format**: Tháng hiển thị trong kết quả dạng YYYY-MM.  _(since 2026-10-21T03:05:32+00:00, session s-20261021-100516-139821)_
- **revenue_definition**: Doanh thu = doanh thu thuần = SUM(orders.total_amount - orders.discount_amount) của các đơn có status = 'delivered'.  _(since 2026-10-21T03:06:03+00:00, session s-20261021-100558-332805)_

## Superseded (history)
- ~~revenue_definition: Doanh thu = SUM(orders.total_amount) của các đơn có status = 'delivered'.~~ → replaced by #4 at 2026-10-21T03:06:03+00:00 (reason: Người dùng yêu cầu đổi quy ước doanh thu từ SUM(total_amount) sang doanh thu thuần SUM(total_amount - discount_amount) cho đơn delivered.)
