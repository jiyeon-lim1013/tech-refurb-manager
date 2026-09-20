import streamlit as st
import pandas as pd
from supabase import create_client, Client
from dataclasses import dataclass

# 1. 페이지 설정
st.set_page_config(page_title="TechRefurb Manager Pro", page_icon="🛠️", layout="wide")

# 2. Supabase 연결
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

# 데이터구조 및 알고리즘
@dataclass
class DeviceItem:
    model_name: str
    buy_price_krw: int
    parts_cost_cny: int
    base_market_price: int
    battery_health: int
    is_oem_screen: bool
    has_truetone: bool
    is_fullbox: bool
    fx_rate: int = 200

def calculate_prices(item: DeviceItem):
    total_cost = item.buy_price_krw + (item.parts_cost_cny * item.fx_rate)
    deduction = 0.0
    if item.battery_health < 80: deduction += 0.08
    elif item.battery_health <= 84: deduction += 0.04
    if item.is_oem_screen:
        deduction += 0.04 if item.has_truetone else 0.10
    add_value = 30000 if item.is_fullbox else 0
    
    dangeun = round((item.base_market_price * (1 - deduction)) + add_value, -4)
    bungeae = round(dangeun * 1.04, -4)
    return int(total_cost), int(dangeun), int(bungeae)

st.title("🛠️ TechRefurb Manager Pro")
st.caption("애플 디바이스 수리/리셀 데이터베이스 & 자금 관리 시스템")

tab1, tab2, tab3, tab4 = st.tabs(["📋 전체 매물 관리", "➕ 신규 매물 등록 & 마진 시뮬레이터", "💳 계좌 및 시드머니 관리", "📊 대시보드 및 통계"])

# TAB 1: 전체 매물 관리 (수정 & 삭제 기능 포함)
with tab1:
    st.subheader("현재 등록된 매물 현황")
    res = supabase.table("inventory").select("*").order("created_at", desc=True).execute()
    data = res.data

    if not data:
        st.info("등록된 매물이 없습니다. '신규 매물 등록' 탭에서 새 매물을 등록해 보세요!")
    else:
        df = pd.DataFrame(data)
        st.dataframe(df, use_container_width=True)

        st.markdown("---")
        col_mod, col_del = st.columns(2)
        
        # 상태 업데이트
        with col_mod:
            st.subheader("⚙️ 상태 빠른 변경")
            item_ids = [item['id'] for item in data]
            selected_id = st.selectbox("상태 변경할 매물 ID 선택", item_ids, key="mod_id")
            new_status = st.selectbox("변경할 진행 상태", ["부품 대기", "수리 진행중", "판매 중", "판매 완료"])
            if st.button("상태 변경 적용"):
                supabase.table("inventory").update({"status": new_status}).eq("id", selected_id).execute()
                st.success(f"ID {selected_id}번 매물의 상태가 '{new_status}'로 변경되었습니다.")
                st.rerun()

        # 삭제 기능
        with col_del:
            st.subheader("🗑️ 매물 삭제")
            del_id = st.selectbox("삭제할 매물 ID 선택", item_ids, key="del_id")
            if st.button("🚨 매물 삭제하기", type="primary"):
                supabase.table("inventory").delete().eq("id", del_id).execute()
                st.warning(f"ID {del_id}번 매물이 완전히 삭제되었습니다.")
                st.rerun()

# TAB 2: 신규 매물 등록
with tab2:
    st.subheader("매물 상세 조건 입력 및 마진 계산")
    
    with st.form("device_form", clear_on_submit=True):
        col_main1, col_main2 = st.columns(2)
        
        with col_main1:
            model_name = st.text_input("기종/기기명", value="맥북에어 M1 16GB")
            category = st.selectbox("카테고리", ["MacBook", "iPad", "iPhone", "Apple Watch", "기타"])
            buy_price = st.number_input("기기 매입가 (KRW)", value=250000, step=10000)
            parts_cny = st.number_input("해외 부품비 (CNY 위안)", value=400, step=50)
            fx_rate = st.number_input("적용 환율 (원/위안)", value=200, step=5)
            
        with col_main2:
            base_market = st.number_input("A급 순정 기준 시세 (KRW)", value=650000, step=10000)
            battery = st.slider("배터리 성능 상태 (%)", 50, 100, 85)
            
            c_check1, c_check2 = st.columns(2)
            with c_check1:
                is_oem = st.checkbox("호환(OEM) 액정 사용", value=True)
                is_box = st.checkbox("풀박스 포함 여부", value=True)
            with c_check2:
                has_tt = st.checkbox("트루톤(TrueTone) 지원", value=True)
            
            status = st.selectbox("초기 상태", ["부품 대기", "수리 진행중", "판매 중"])
            notes = st.text_area("수리 메모 및 특이사항", value="상판/액정 교체 필요.")

        submitted = st.form_submit_button("💰 마진 계산 및 Supabase DB 저장")

    if submitted:
        item = DeviceItem(model_name, buy_price, parts_cny, base_market, battery, is_oem, has_tt, is_box, fx_rate)
        total_cost, dangeun_rec, bungeae_rec = calculate_prices(item)
        
        new_data = {
            "item_name": model_name,
            "category": category,
            "buy_price": buy_price,
            "repair_cost": parts_cny * fx_rate,
            "target_price": dangeun_rec,
            "status": status,
            "notes": f"{notes} | [추천가] 당근:{dangeun_rec:,}원 / 번개:{bungeae_rec:,}원"
        }
        
        supabase.table("inventory").insert(new_data).execute()
        st.success(f"'{model_name}' 등록 완료!")
        st.rerun()

# TAB 3: 계좌 및 자금 관리
with tab3:
    st.subheader("💳 사업 자금 및 계좌 관리 시뮬레이터")
    
    st.info("💡 매입 자금(시드머니) 설정 및 매물 거래에 따른 잔액 변화 관리")
    
    initial_seed = st.number_input("초기 설정 시드머니 (원)", value=3000000, step=500000)
    
    res = supabase.table("inventory").select("*").execute()
    all_items = res.data
    
    if all_items:
        df_acc = pd.DataFrame(all_items)
        
        # 총 매입가 + 부품비 합계 (지출)
        total_spent = df_acc['buy_price'].fillna(0).sum() + df_acc['repair_cost'].fillna(0).sum()
        
        # 판매 완료된 건의 목표가 합계 (수익)
        sold_items = df_acc[df_acc['status'] == '판매 완료']
        total_revenue = sold_items['target_price'].fillna(0).sum() if not sold_items.empty else 0
        
        current_balance = initial_seed - total_spent + total_revenue
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("기본 시드머니", f"{int(initial_seed):,} 원")
        c2.metric("총 지출 (기기+부품)", f"{int(total_spent):,} 원", delta=f"-{int(total_spent):,}", delta_color="inverse")
        c3.metric("총 회수 금액 (판매)", f"{int(total_revenue):,} 원", delta=f"+{int(total_revenue):,}")
        c4.metric("현재 계좌 잔액", f"{int(current_balance):,} 원", delta=f"{int(current_balance - initial_seed):,} 원")

# TAB 4: 대시보드 통계
with tab4:
    st.subheader("📈 리퍼비시 비즈니스 종합 현황")
    res = supabase.table("inventory").select("*").execute()
    all_data = res.data

    if all_data:
        df_stat = pd.DataFrame(all_data)
        
        total_cnt = len(df_stat)
        completed_cnt = len(df_stat[df_stat['status'] == '판매 완료'])
        
        sold_df = df_stat[df_stat['status'] == '판매 완료']
        realized_margin = (sold_df['target_price'] - sold_df['buy_price'] - sold_df['repair_cost']).sum() if not sold_df.empty else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("총 누적 매물 수", f"{total_cnt} 대")
        c2.metric("판매 완료 수", f"{completed_cnt} 대")
        c3.metric("실현 순이익", f"{int(realized_margin):,} 원")
