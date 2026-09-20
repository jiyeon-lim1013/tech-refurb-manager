import streamlit as st
import pandas as pd
from supabase import create_client, Client

# Streamlit 페이지 설정
st.set_page_config(page_title="애플 디바이스 리퍼비시 관리자", page_icon="📱", layout="wide")

# Supabase 클라이언트 연결
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_supabase()
except Exception as e:
    st.error("Supabase 연결 실패: Secrets 설정을 확인해주세요.")
    st.stop()

st.title("📱 애플 디바이스 리퍼비시 매물 관리자")

# Tab 구성
tab1, tab2, tab3 = st.tabs(["📦 매물 목록 / 상태 변경", "➕ 신규 매물 등록", "📊 수익 통계"])

# 1. 매물 목록 및 상태 변경
with tab1:
    st.subheader("현재 등록된 매물")
    res = supabase.table("inventory").select("*").order("created_at", desc=True).execute()
    data = res.data

    if not data:
        st.info("등록된 매물이 없습니다. '신규 매물 등록' 탭에서 등록해 주세요.")
    else:
        df = pd.DataFrame(data)
        st.dataframe(df[["id", "item_name", "category", "buy_price", "repair_cost", "target_price", "status", "notes"]], use_container_width=True)
        
        st.write("---")
        st.write("### ⚙️ 상태 업데이트")
        col1, col2 = st.columns(2)
        with col1:
            item_ids = [item['id'] for item in data]
            selected_id = st.selectbox("수정할 매물 ID 선택", item_ids)
        with col2:
            new_status = st.selectbox("변경할 상태", ["매입 완료", "수리 중", "판매 중", "판매 완료"])
            
        if st.button("상태 변경 저장"):
            supabase.table("inventory").update({"status": new_status}).eq("id", selected_id).execute()
            st.success(f"ID {selected_id} 번 매물의 상태가 '{new_status}'(으)로 변경되었습니다!")
            st.rerun()

# 2. 신규 매물 등록
with tab2:
    st.subheader("새로운 매입 기기 등록")
    with st.form("new_item_form", clear_on_submit=True):
        item_name = st.text_input("기기명 (예: 맥북 에어 M1 8G/256G 스페이스그레이)")
        category = st.selectbox("카테고리", ["MacBook", "iPad", "iPhone", "Apple Watch", "기타 부품/악세서리"])
        
        col_p1, col_p2, col_p3 = st.columns(3)
        with col_p1:
            buy_price = st.number_input("매입가 (원)", min_value=0, step=10000)
        with col_p2:
            repair_cost = st.number_input("부품/수리비 (원)", min_value=0, step=5000)
        with col_p3:
            target_price = st.number_input("목표 판매가 (원)", min_value=0, step=10000)
            
        notes = st.text_area("상태 및 수리 메모 (예: 액정 파손 제품 매입, 배터리 및 상판 교체 완료)")
        
        submitted = st.form_submit_dict = st.form_submit_button("매물 등록하기")
        if submitted:
            if not item_name:
                st.warning("기기명을 입력해 주세요.")
            else:
                new_data = {
                    "item_name": item_name,
                    "category": category,
                    "buy_price": buy_price,
                    "repair_cost": repair_cost,
                    "target_price": target_price,
                    "status": "매입 완료",
                    "notes": notes
                }
                supabase.table("inventory").insert(new_data).execute()
                st.success(f"'{item_name}' 등록이 완료되었습니다!")
                st.rerun()

# 3. 수익 통계
with tab3:
    st.subheader("리퍼비시 수익 요약")
    res = supabase.table("inventory").select("*").execute()
    all_data = res.data
    
    if all_data:
        df_stat = pd.DataFrame(all_data)
        total_items = len(df_stat)
        completed_items = len(df_stat[df_stat['status'] == '판매 완료'])
        
        total_investment = df_stat['buy_price'].sum() + df_stat['repair_cost'].sum()
        
        sold_df = df_stat[df_stat['status'] == '판매 완료']
        expected_margin = (df_stat['target_price'] - df_stat['buy_price'] - df_stat['repair_cost']).sum()
        realized_margin = (sold_df['target_price'] - sold_df['buy_price'] - sold_df['repair_cost']).sum()
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("총 등록 매물", f"{total_items} 개")
        m2.metric("판매 완료", f"{completed_items} 개")
        m3.metric("총 투입 금액(매입+수리)", f"{total_investment:,} 원")
        m4.metric("실현 정산 순이익", f"{realized_margin:,} 원", delta=f"예상 총이익 {expected_margin:,}원")
    else:
        st.info("통계를 산출할 매물 데이터가 없습니다.")
