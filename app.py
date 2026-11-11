import datetime
from zoneinfo import ZoneInfo

import gspread
import streamlit as st
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="냥이 숙제 펀치!", page_icon="🐱", layout="centered")

st.markdown(
    """
    <style>
    .main { background-color: #fffaf0; }
    h1 { color: #e67e22; text-align: center; font-family: 'Arial', sans-serif; }
    .stButton>button {
        background-color: #f39c12; color: white;
        border-radius: 20px; font-weight: bold; border: none;
    }
    .stButton>button:hover { background-color: #d35400; color: white; }
    </style>
""",
    unsafe_allow_html=True,
)

TASK_POINT = 10   # 숙제 체크 1개당 점수
BOOK_POINT = 10   # 독서인증 1권당 점수
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
ss = st.session_state


# ---------- 구글 시트 연결 ----------
def to_bool(v):
    return v is True or str(v).strip().upper() == "TRUE"


@st.cache_resource
def get_spreadsheet():
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return gspread.authorize(creds).open_by_key(st.secrets["sheet_id"])


def write_ranges(items):
    """items = [(범위, 값들), ...] 를 한 번에 시트에 쓰기"""
    body = {
        "valueInputOption": "USER_ENTERED",
        "data": [{"range": r, "values": v} for r, v in items],
    }
    get_spreadsheet().values_batch_update(body=body)


def load_all():
    sh = get_spreadsheet()
    subjects = [
        r for r in sh.worksheet("과목설정").get_all_records() if to_bool(r["사용여부"])
    ]
    subjects.sort(key=lambda r: int(r["순서"]))
    daily = sh.worksheet("일일숙제1").get_all_records()
    books = sh.worksheet("독서인증").get_all_records()
    summary = sh.worksheet("포인트요약").get_all_records()

    ss.subjects = [
        {"id": r["과목ID"], "name": r["과목명"], "count": min(int(r["숙제개수"]), 5)}
        for r in subjects
    ]
    ss.daily_rows = {}
    for idx, r in enumerate(daily):
        sid = r["과목ID"]
        ss.daily_rows[sid] = idx + 2
        for k in range(1, 6):
            ss[f"chk_{sid}_{k}"] = to_bool(r.get(f"체크{k}"))

    ss.books = []
    for idx, r in enumerate(books):
        name = str(r.get("독서인증", "")).strip()
        if not name:
            continue
        i = len(ss.books)
        ss.books.append({"row": idx + 2, "name": name})
        ss[f"book_{i}"] = to_bool(r.get("완료"))
        ss[f"bdate_{i}"] = str(r.get("완료날짜", "") or "")
        ss[f"settled_{i}"] = to_bool(r.get("정산"))

    ss.base_points = int(float(summary[0]["지난주까지누적"]))


try:
    if "loaded" not in ss:
        load_all()
        ss.loaded = True
except Exception as e:
    st.error("구글 시트를 불러오지 못했어요. 설정을 확인해 주세요.")
    st.exception(e)
    st.stop()


# ---------- 계산 ----------
def count_tasks():
    return sum(
        1
        for s in ss.subjects
        for k in range(1, s["count"] + 1)
        if ss.get(f"chk_{s['id']}_{k}", False)
    )


def count_new_books():
    return sum(
        1
        for i in range(len(ss.books))
        if ss[f"book_{i}"] and not ss[f"settled_{i}"]
    )


# ---------- 버튼/체크박스 동작 ----------
def on_task_change(sid, k):
    row = ss.daily_rows[sid]
    col = chr(ord("B") + k)  # k=1 -> C
    write_ranges([(f"'일일숙제1'!{col}{row}", [[ss[f"chk_{sid}_{k}"]]])])


def on_book_change(i):
    row = ss.books[i]["row"]
    done = ss[f"book_{i}"]
    today = datetime.datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
    ss[f"bdate_{i}"] = today if done else ""
    write_ranges(
        [
            (f"'독서인증'!B{row}", [[done]]),
            (f"'독서인증'!C{row}", [[today if done else ""]]),
        ]
    )


def weekly_settle():
    add = count_tasks() * TASK_POINT + count_new_books() * BOOK_POINT
    new_base = ss.base_points + add

    items = [("'포인트요약'!C2", [[new_base]])]
    for sid, row in ss.daily_rows.items():
        items.append((f"'일일숙제1'!C{row}:G{row}", [[False] * 5]))
        for k in range(1, 6):
            ss[f"chk_{sid}_{k}"] = False
    for i, b in enumerate(ss.books):
        if ss[f"book_{i}"] and not ss[f"settled_{i}"]:
            items.append((f"'독서인증'!D{b['row']}", [[True]]))
            ss[f"settled_{i}"] = True

    write_ranges(items)
    ss.base_points = new_base
    ss.show_reset_msg = add


def refresh():
    ss.pop("loaded", None)


# ---------- 화면 ----------
st.title("🐾 냐옹이와 함께하는 숙제 대작전! 🐱")
st.markdown(
    "<p style='text-align: center; color: #7f8c8d;'>숙제를 완료하고 체크하면 고양이 생선 포인트가 쑥쑥! 🐟</p>",
    unsafe_allow_html=True,
)

total = ss.base_points + count_tasks() * TASK_POINT + count_new_books() * BOOK_POINT
c1, c2, c3 = st.columns([1, 2, 1])
with c2:
    st.metric(label="🐟 모은 생선 포인트", value=f"{total} P")
    st.caption(f"지난주까지 {ss.base_points}P + 이번 주 {total - ss.base_points}P")

st.divider()

tab1, tab2 = st.tabs(["🐱 이번 주 숙제", "📚 독서인증"])

with tab1:
    for s in ss.subjects:
        st.markdown(f"**🐾 {s['name']}**")
        cols = st.columns(s["count"])
        for k in range(1, s["count"] + 1):
            cols[k - 1].checkbox(
                f"{k}회",
                key=f"chk_{s['id']}_{k}",
                on_change=on_task_change,
                args=(s["id"], k),
            )

with tab2:
    st.write("책을 다 읽으면 체크해 주세요! 📖")
    for i, b in enumerate(ss.books):
        label = f"📖 {b['name']}"
        if ss[f"bdate_{i}"]:
            label += f"  ({ss[f'bdate_{i}']})"
        st.checkbox(
            label,
            key=f"book_{i}",
            disabled=ss[f"settled_{i}"],
            on_change=on_book_change,
            args=(i,),
        )

st.divider()

b1, b2 = st.columns(2)
with b1:
    st.button("🔄 시트 다시 불러오기", on_click=refresh)
with b2:
    st.button("🎁 이번 주 정산하고 초기화", on_click=weekly_settle)

if "show_reset_msg" in ss:
    st.success(f"🎉 이번 주 {ss.pop('show_reset_msg')}P를 누적에 저장하고 체크를 초기화했어요!")