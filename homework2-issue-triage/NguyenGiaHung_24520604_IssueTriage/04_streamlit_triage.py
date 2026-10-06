import os

import streamlit as st

from demo_common import get_client, get_model, read_settings
from triage_workflow import triage


DEFAULT_ISSUE = "Tất cả giao dịch Visa bị HTTP 500 từ 14:30. Hãy phân loại lỗi và tìm team xử lý."


st.set_page_config(page_title="Issue Triage", page_icon="🔎", layout="wide")


def show_result(result):
    first_log = result.logs[0]
    left, right = st.columns(2)
    left.metric("Component", first_log.output["component"])
    right.metric("Team phụ trách", first_log.output["owner"])
    with st.expander("Function calling trace", expanded=True):
        for item in result.logs:
            st.write(f"Tool: `{item.tool_name}`")
            st.json({"arguments": item.arguments, "result": item.output})
    st.subheader("Kết quả triage")
    st.write(result.answer)


def main():
    read_settings()
    with st.sidebar:
        st.header("Cấu hình đang dùng")
        st.code(os.getenv("OPENAI_BASE_URL") or "Chưa có base URL")
        st.code(os.getenv("OPENAI_MODEL") or "Chưa có model")

    st.title("Issue Triage")
    with st.form("triage_form"):
        issue = st.text_area("Mô tả issue", value=DEFAULT_ISSUE, height=180)
        submitted = st.form_submit_button("Phân loại issue", use_container_width=True)

    if submitted:
        if not issue.strip():
            st.error("Hãy nhập mô tả issue")
            return
        try:
            with st.spinner("Đang xử lý..."):
                result = triage(get_client(), get_model(), issue.strip())
            show_result(result)
        except Exception as error:
            st.error(str(error))


if __name__ == "__main__":
    main()
