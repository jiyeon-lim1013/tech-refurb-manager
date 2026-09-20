import streamlit as st
import pandas as pd
from supabase import create_client, Client
from dataclasses import dataclass
from datetime import datetime

# 1. 페이지 설정
st.set_page_config(page_title="TechRefurb Manager Pro v2", page_icon="🛠️", layout="wide")

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

# 세션 상태로 계좌 목록 관리 (추가/수정/삭제 지원)
if "accounts" not in st.session_state:
    st.session_state.accounts = ["당근페이", "번개페이", "국민은행", "하나은행", "카카오뱅크", "현금"]

# 계산 데이터구조
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

st.title("🛠️ TechRefurb Manager Pro (v2)")
st.caption("애플 디바이스 수리/리셀 데이터베이스 & 입출금·계좌 관리 시스템")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📋 전체 매물 관리", 
    "➕ 신규 매물 등록", 
    "💸 입출금 및 장부 관리", 
    "🏦 계좌 목록 설정", 
    "📊 대시보드 통계"
])

# ==========================================
# TAB 1: 전체 매물 관리
# ==========================================
with tab1:
    st.subheader("📋 전체 매물 목록")
    res = supabase.table("inventory").select("*").order("created_at", desc=True).execute()
    data = res.data

    if not data:
        st.info("등록된 매물이 없습니다. '신규 매물 등록' 탭에서 새 매물을 등록해 보세요!")
    else:
        df = pd.DataFrame(data)
        
        # 한국어 표기 및 컬럼 매핑
        column_mapping = {
            "id": "ID",
            "item_name": "기종명",
            "category": "카테고리",
            "screen_size": "화면 크기",
            "buy_price": "매입가(원)",
            "repair_cost": "수리비(원)",
            "target_price": "목표 판매가(원)",
            "buy_account": "매입 계좌",
            "repair_account": "수리비 계좌",
            "status": "진행 상태",
            "notes": "비고/특이사항",
            "created_at": "생성일시"
        }
        
        # 데이터 프레임에 있는 컬럼만 매핑
        df_display = df.copy()
        
        # 날짜 포맷 변환 (YYYY-MM-DD HH:MM)
        if "created_at" in df_display.columns:
            df_display["created_at"] = pd.to_datetime(df_display["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
        
        # 가격 숫자 포맷팅
        for p_col in ["buy_price", "repair_cost", "target_price"]:
            if p_col in df_display.columns:
                df_display[p_col] = df_display[p_col].apply(lambda x: f"{int(x):,}원" if pd.notnull(x) and x != "" else "0원")

        # 존재하는 컬럼만 한글명 변경
        rename_dict = {k: v for k, v in column_mapping.items() if k in df_display.columns}
        df_display = df_display.rename(columns=rename_dict)
        
        # 표 출력 (자동 너비 최적화)
        st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("---")
        col_mod, col_del = st.columns(2)
        item_ids = [item['id'] for item in data]
        
        with col_mod:
            st.subheader("⚙️ 진행 상태 변경")
            selected_id = st.selectbox("상태를 변경할 매물 ID 선택", item_ids, key="mod_id")
            new_status = st.selectbox("변경할 진행 상태", ["부품 대기", "수리 진행중", "판매 중", "판매 완료"])
            if st.button("상태 변경 적용"):
                supabase.table("inventory").update({"status": new_status}).eq("id", selected_id).execute()
                st.success(f"ID {selected_id}번 매물 상태가 '{new_status}'로 변경되었습니다.")
                st.rerun()

        with col_del:
            st.subheader("🗑️ 매물 삭제")
            del_id = st.selectbox("삭제할 매물 ID 선택", item_ids, key="del_id")
            if st.button("🚨 매물 삭제하기", type="primary"):
                supabase.table("inventory").delete().eq("id", del_id).execute()
                st.warning(f"ID {del_id}번 매물이 완전히 삭제되었습니다.")
                st.rerun()

# ==========================================
# TAB 2: 신규 매물 등록 (인치 선택 & 계좌 연결)
# ==========================================
with tab2:
    st.subheader("➕ 신규 매물 등록 & 마진 산정")
    
    with st.form("device_form", clear_on_submit=True):
        col_main1, col_main2 = st.columns(2)
        
        with col_main1:
            category = st.selectbox("카테고리", ["MacBook", "iPad", "iPhone", "Apple Watch", "기타"])
            
            # 카테고리별 인치/사이즈 동적 선택
            if category == "MacBook":
                screen_size = st.selectbox("맥북 화면 크기 (인치)", ["11인치", "12인치", "13인치", "14인치", "15인치", "16인치"])
            elif category == "iPad":
                screen_size = st.selectbox("아이패드 화면 크기 (인치)", ["7.9인치", "8.3인치", "9.7인치", "10.2인치", "10.5인치", "10.9인치", "11인치", "12.9인치", "13인치"])
            elif category == "iPhone":
                screen_size = st.selectbox("아이폰 화면 크기", ["4.7인치", "5.4인치", "6.1인치", "6.7인치", "6.9인치"])
            elif category == "Apple Watch":
                screen_size = st.selectbox("애플워치 크기 (mm)", ["40mm", "41mm", "42mm", "44mm", "45mm", "49mm"])
            else:
                screen_size = st.text_input("사이즈/규격", value="일반")

            model_name = st.text_input("기종/모델명", value="맥북에어 M1 16GB")
            buy_price = st.number_input("기기 매입가 (KRW)", value=250000, step=10000)
            buy_account = st.selectbox("기기 매입 결제 계좌", st.session_state.accounts, index=0)
            
            parts_cny = st.number_input("해외 부품비 (CNY 위안)", value=400, step=50)
            fx_rate = st.number_input("적용 환율 (원/위안)", value=200, step=5)
            repair_account = st.selectbox("수리비(부품) 결제 계좌", st.session_state.accounts, index=2 if len(st.session_state.accounts)>2 else 0)

        with col_main2:
            base_market = st.number_input("A급 순정 기준 시세 (KRW)", value=650000, step=10000)
            battery = st.slider("배터리 성능 상태 (%)", 50, 100, 85)
            
            c_check1, c_check2 = st.columns(2)
            with c_check1:
                is_oem = st.checkbox("호환(OEM) 액정 사용", value=True)
                is_box = st.checkbox("풀박스 포함 여부", value=True)
            with c_check2:
                has_tt = st.checkbox("트루톤(TrueTone) 지원", value=True)
            
            status = st.selectbox("초기 진행 상태", ["부품 대기", "수리 진행중", "판매 중"])
            notes = st.text_area("수리 메모 및 특이사항", value="액정 교체 완료. 외관 깨끗함.")

        submitted = st.form_submit_button("💰 등록 및 마진 자동 계산")

    if submitted:
        item = DeviceItem(model_name, buy_price, parts_cny, base_market, battery, is_oem, has_tt, is_box, fx_rate)
        total_cost, dangeun_rec, bungeae_rec = calculate_prices(item)
        
        repair_cost_krw = parts_cny * fx_rate
        
        new_data = {
            "item_name": model_name,
            "category": category,
            "screen_size": screen_size,
            "buy_price": buy_price,
            "repair_cost": repair_cost_krw,
            "target_price": dangeun_rec,
            "buy_account": buy_account,
            "repair_account": repair_account,
            "status": status,
            "notes": f"{notes} | [추천가] 당근:{dangeun_rec:,}원 / 번개:{bungeae_rec:,}원"
        }
        
        supabase.table("inventory").insert(new_data).execute()
        st.success(f"'{model_name} ({screen_size})' 등록이 완료되었습니다!")
        st.rerun()

# ==========================================
# TAB 3: 입출금 및 장부 관리
# ==========================================
with tab3:
    st.subheader("💸 입금 및 출금 내역 관리")
    
    col_in, col_out = st.columns(2)
    with col_in:
        st.markdown("##### 📥 입금 등록 (판매/자금입금)")
        with st.form("income_form", clear_on_submit=True):
            inc_amount = st.number_input("입금 금액 (원)", value=100000, step=10000)
            inc_account = st.selectbox("입금받은 계좌", st.session_state.accounts, key="inc_acc")
            inc_category = st.selectbox("구분", ["기기 판매 대금", "시드머니 충전", "기타 입금"])
            inc_note = st.text_input("적요/비고", value="당근마켓 판매완료")
            inc_sub = st.form_submit_button("입금 내역 저장")
            
            if inc_sub:
                st.success(f"{inc_account} 계좌로 {inc_amount:,}원 입금 등록되었습니다.")

    with col_out:
        st.markdown("##### 📤 출금 등록 (부품/기타지출)")
        with st.form("expense_form", clear_on_submit=True):
            exp_amount = st.number_input("출금 금액 (원)", value=50000, step=5000)
            exp_account = st.selectbox("출금 사용 계좌", st.session_state.accounts, key="exp_acc")
            exp_category = st.selectbox("구분", ["공구/소모품 구매", "식비/운반비", "기타 지출"])
            exp_note = st.text_input("적요/비고", value="수리 공구 구매")
            exp_sub = st.form_submit_button("출금 내역 저장")
            
            if exp_sub:
                st.warning(f"{exp_account} 계좌에서 {exp_amount:,}원 출금 등록되었습니다.")

# ==========================================
# TAB 4: 계좌 목록 설정 (수정/삭제 가능)
# ==========================================
with tab4:
    st.subheader("🏦 사용 계좌/거래처 목록 관리")
    st.caption("매입, 수리비, 입출금 시 사용할 계좌 및 거래 플랫폼 목록을 직접 관리하세요.")
    
    col_a1, col_a2 = st.columns(2)
    
    with col_a1:
        st.markdown("##### ➕ 새 계좌/플랫폼 추가")
        new_acc_name = st.text_input("계좌/플랫폼 이름 (예: 토스뱅크, 당근페이)")
        if st.button("계좌 추가"):
            if new_acc_name and new_acc_name not in st.session_state.accounts:
                st.session_state.accounts.append(new_acc_name)
                st.success(f"'{new_acc_name}' 계좌가 추가되었습니다!")
                st.rerun()

    with col_a2:
        st.markdown("##### ✏️ 계좌 수정 및 삭제")
        edit_target = st.selectbox("관리할 계좌 선택", st.session_state.accounts)
        
        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            renamed_acc = st.text_input("변경할 이름 입력", value=edit_target)
            if st.button("이름 변경"):
                idx = st.session_state.accounts.index(edit_target)
                st.session_state.accounts[idx] = renamed_acc
                st.success("계좌 이름이 변경되었습니다.")
                st.rerun()
                
        with col_btn2:
            st.write(" ")
            st.write(" ")
            if st.button("🚨 해당 계좌 삭제"):
                if len(st.session_state.accounts) > 1:
                    st.session_state.accounts.remove(edit_target)
                    st.warning(f"'{edit_target}' 계좌가 삭제되었습니다.")
                    st.rerun()
                else:
                    st.error("최소 1개의 계좌는 유지되어야 합니다.")

    st.markdown("---")
    st.markdown("##### 📜 현재 등록된 전체 계좌 목록")
    st.write(st.session_state.accounts)

# ==========================================
# TAB 5: 대시보드 통계
# ==========================================
with tab5:
    st.subheader("📈 종합 현황 대시보드")
    res = supabase.table("inventory").select("*").execute()
    all_data = res.data

    if all_data:
        df_stat = pd.DataFrame(all_data)
        
        total_cnt = len(df_stat)
        completed_cnt = len(df_stat[df_stat['status'] == '판매 완료'])
        
        sold_df = df_stat[df_stat['status'] == '판매 완료']
        realized_margin = (sold_df['target_price'] - sold_df['buy_price'] - sold_df['repair_cost']).sum() if not sold_df.empty else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("총 매물 건수", f"{total_cnt} 대")
        c2.metric("판매 완료 수", f"{completed_cnt} 대")
        c3.metric("실현 순이익", f"{int(realized_margin):,} 원")
