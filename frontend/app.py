"""Live four-agent orchestration monitor; all calls go through the backend."""
import os
import httpx
import streamlit as st

BASE_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")
ROLES = {"weather_agent": ("Weather agent", "날씨와 실내외 활동"),
         "place_agent": ("Place agent", "장소 후보 비교"),
         "budget_agent": ("Budget agent", "1인 여행 비용 계산"),
         "validation_agent": ("Validation agent", "근거·예산·실행 결과 검토")}
LABELS = {"pending": "대기", "running": "실행 중", "completed": "완료", "mock": "모의 응답", "failed": "실패", "partial_failure": "일부 실패"}


def api(method, path, **kwargs):
    response = httpx.request(method, BASE_URL + path, timeout=12, **kwargs)
    response.raise_for_status()
    return response.json()


st.set_page_config(page_title="Travel Agent Studio", page_icon=":material/route:", layout="wide")
st.title("Travel Agent Studio")
st.write("네 명의 에이전트가 여행 조건을 나누어 검토합니다. 실행 순서와 근거를 직접 확인하세요.")
try:
    config = api("GET", "/api/multi/config")
except httpx.HTTPError:
    st.error("백엔드에 연결할 수 없습니다. 잠시 후 새로고침하세요.")
    st.stop()

with st.sidebar:
    st.header("에이전트별 모델")
    if st.button("전체 모델을 Ollama로 설정"):
        for agent in ROLES:
            st.session_state["provider_" + agent] = "ollama"
    if st.button("전체 모델을 Gemma로 설정"):
        for agent in ROLES:
            st.session_state["provider_" + agent] = "gemma"
    st.caption("EC2 CPU 추론: 네 역할 분석에 약 2~3분이 걸릴 수 있습니다.")
    if config.get("demo_enabled", True) and st.button("전체 모델을 mock으로 전환"):
        for agent in ROLES:
            st.session_state["provider_" + agent] = "mock"
    selected = {}
    for agent, (title, _) in ROLES.items():
        default = config["defaults"].get(agent, "mock")
        choices = config["providers"]
        if st.session_state.get("provider_" + agent) not in choices:
            st.session_state["provider_" + agent] = default if default in choices else "ollama"
        selected[agent] = st.selectbox(title, choices, index=None, format_func=lambda x: {"ollama": "Ollama · Qwen", "gemma": "Gemma · Ollama", "mock": "Mock · 테스트"}.get(x, x), key="provider_" + agent)
        st.caption(config["models"].get(selected[agent], "모델을 선택해 주세요."))
        if not config["configured"].get(selected[agent]):
            st.caption("서버 키/주소 미설정 · 모의 응답 허용 시 대체됩니다.")
    allow_mock = st.checkbox("모델 호출 실패 시 모의 응답 허용", value=False) if config.get("demo_enabled", True) else False
    st.caption("Ollama(Qwen)와 Gemma 모두 EC2에서 실행합니다.")

@st.fragment
def connection_panel():
    with st.expander("DB · Redis 연결과 데이터 흐름", expanded=True):
        st.caption("멀티에이전트 전용 저장소 · 주소와 접속 계정은 공개하지 않습니다.")
        st.button("연결 상태 새로 확인", key="refresh_connections")
        try:
            status = api("GET", "/api/multi/data-status")
            labels = {"connected": "연결 확인", "unavailable": "연결 확인 필요", "not_configured": "미설정"}
            roles = {"facts_postgres": "여행 데이터 · PostgreSQL", "facts_redis": "여행 캐시 · Redis",
                     "history_postgres": "실행 기록 · PostgreSQL", "history_redis": "결과 캐시 · Redis"}
            for col, (key, title) in zip(st.columns(4), roles.items()):
                with col:
                    st.write("**" + title + "**")
                    st.write(labels.get(status["services"].get(key), "확인 대기"))
            st.caption("최근 점검: " + status["checked_at"] + " · 점검 결과는 최대 15초 재사용합니다.")
        except httpx.HTTPError:
            st.info("연결 상태를 조회하지 못했습니다. 새로 확인을 눌러 주세요.")
        st.write("**조회**  프론트 → 백엔드 → MCP → Redis 캐시 → PostgreSQL 여행 데이터")
        st.caption("유효한 캐시가 없으면 DB를 읽고, 자료가 오래되면 출처 API로 갱신합니다.")
        st.write("**저장**  에이전트 실행 → PostgreSQL 실행·역할별 결과·타임라인 + Redis 결과 캐시")
        st.caption("PostgreSQL은 기록을 보관하고 Redis 결과 캐시는 1시간 유지합니다. 실행 중 진행 상태는 백엔드 메모리에서 조회합니다.")
        st.caption("연결 점검은 DB 읽기와 Redis PING입니다. 실제 저장 성공 여부는 아래 실행 결과에서 별도로 확인합니다.")


connection_panel()
active = st.session_state.get("active", False)
with st.container(border=True):
    a, b, c = st.columns(3)
    city = a.selectbox("도시", ["부산", "서울", "제주"])
    days = b.number_input("여행 일수", min_value=1, max_value=14, value=2)
    budget = c.number_input("1인 예산 (원)", min_value=10000, max_value=10000000, value=300000, step=10000)
    question = st.text_area("요청 사항", "날씨를 고려해 여행 장소를 고르고 예산이 적절한지 검토해 주세요.", max_chars=1000, height=80)
    data_mode = "auto"
    if config.get("demo_enabled", True):
        data_mode = st.radio("데이터 모드", ["auto", "mock"], format_func=lambda x: "자동: MCP → Redis / PostgreSQL → 없으면 모의 데이터" if x == "auto" else "모의 데이터: 외부 DB 없이 실행", horizontal=True)
    else:
        st.caption("전용 DB의 공식 관광정보와 현재 모델 날씨를 조회합니다. 오래된 날씨는 자동 갱신합니다.")
    st.subheader("1인 예산 상세 계획")
    st.caption("아래 금액은 직접 입력하는 계획 단가입니다. 실제 호텔 예약가·식당 메뉴 가격을 조회한 값이 아닙니다.")
    h1, h2, h3 = st.columns(3)
    travelers = h1.number_input("함께 숙박하는 인원", min_value=1, max_value=10, value=1)
    rooms = h2.number_input("객실 수", min_value=1, max_value=10, value=1)
    lodging = h3.selectbox("숙소 유형", ["호텔", "비즈니스호텔", "게스트하우스", "리조트", "숙박 없음"])
    hotel = st.number_input("객실당 1박 계획 금액 (원)", min_value=0, max_value=10000000, value=80000, step=10000, disabled=lodging == "숙박 없음")
    if lodging == "숙박 없음":
        hotel = 0
    st.caption(f"숙박: {max(0, days - 1)}박 × 객실당 금액 × {rooms}객실 ÷ {travelers}명으로 1인 숙박비를 계산합니다.")
    meal_plan = []
    defaults = {"아침": (8000, ["간단식 · 김밥/샌드위치", "숙소 조식", "국밥/해장국", "숙박비에 포함", "식사 제외"]),
                "점심": (12000, ["현지식 · 국밥/백반", "면류/분식", "고기/생선 정식", "식사 제외"]),
                "저녁": (10000, ["현지식 · 백반/찌개", "고기구이", "해산물/생선 요리", "식사 제외"]),
                "카페·간식": (0, ["이용 안 함", "커피/음료", "디저트/간식"])}
    for col, (meal_name, (price, options)) in zip(st.columns(4), defaults.items()):
        with col:
            style = st.selectbox(meal_name + " 식사 유형", options)
            excluded = style in ("숙박비에 포함", "식사 제외", "이용 안 함")
            unit_price = st.number_input(meal_name + " 1인 1회 금액 (원)", min_value=0, max_value=1000000, value=price, step=1000, disabled=excluded)
            meal_plan.append({"name": meal_name, "style": style, "price": 0 if excluded else unit_price})
    food = sum(m["price"] for m in meal_plan)
    st.caption(f"1인 식비·카페: 하루 {food:,}원 × {days}일. 매일 각 항목 1회 기준이며 첫날·마지막날도 동일하게 계산합니다.")
    transport = st.number_input("현지 교통 1인 1일 계획 금액 (원)", min_value=0, max_value=1000000, value=15000, step=1000)
    submitted = st.button("멀티에이전트 실행", type="primary", disabled=active or any(value is None for value in selected.values()))
if submitted:
    try:
        run = api("POST", "/api/multi/runs", json={"city": city, "days": days, "budget": budget,
                  "question": question, "travelers": travelers, "rooms": rooms, "lodging_type": lodging, "meal_plan": meal_plan, "hotel_per_night": hotel, "food_per_day": food, "transport_per_day": transport, "providers": selected, "data_mode": data_mode, "allow_model_mock": allow_mock})
        st.session_state["lost_run"] = False
        st.session_state.update(run_id=run["run_id"], snapshot=run, active=True)
        st.rerun()
    except httpx.HTTPStatusError as error:
        st.error("실행 요청 실패: " + str(error.response.status_code) + " · 입력과 동시 실행 수를 확인하세요.")
    except httpx.HTTPError:
        st.error("백엔드 요청이 실패했습니다. 다시 시도하세요.")

st.divider()
st.subheader("실행 흐름")
st.caption("Weather + Place 병렬 실행  →  결과 합치기  →  Budget  →  Validation")


def agent_panel(agent, state):
    title, subtitle = ROLES[agent]
    with st.container(border=True):
        st.subheader(title)
        st.caption(subtitle)
        status = state.get("status", "pending")
        st.write("**" + LABELS.get(status, status) + "**")
        if state.get("provider_requested"):
            used = state.get("provider_used") or "대기"
            st.caption(f"요청 {state['provider_requested']} / 실제 {used} · {state.get('model', '')}")
        if state.get("latency_ms") is not None:
            st.caption(f"처리 시간 {state['latency_ms'] / 1000:.2f}초")
        if state.get("error"):
            st.error("선택한 모델의 응답을 받지 못했습니다. 연결 설정을 확인한 뒤 다시 실행하세요.")
            with st.expander("연결 진단"):
                st.code(state["error"])
        if state.get("answer"):
            answer = state["answer"]
            st.write(answer["summary"])
            for line in answer["details"]:
                st.write("• " + line)
            for warning in answer["cautions"]:
                st.caption(warning)


@st.fragment(run_every=1.0 if st.session_state.get("active") else None)
def monitor():
    run = st.session_state.get("snapshot")
    if st.session_state.get("active"):
        try:
            run = api("GET", "/api/multi/runs/" + st.session_state["run_id"])
            st.session_state["snapshot"] = run
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                st.session_state["active"] = False
                st.session_state["lost_run"] = True
                st.rerun()
            st.warning("상태 조회에 실패했습니다. 자동으로 다시 확인합니다.")
        except httpx.HTTPError:
            st.warning("연결이 잠시 끊겼습니다. 자동으로 다시 확인합니다.")
        if run and run["status"] != "running":
            st.session_state["active"] = False
            st.rerun()
    if st.session_state.get("lost_run"):
        st.warning("배포·재시작으로 실행 기록이 만료되었습니다. 새 실행을 시작하세요.")
    if run:
        if run.get("error"):
            st.error("분석을 완료하지 못했습니다. 데이터 또는 모델 연결 상태를 확인해 주세요.")
        st.caption(f"실행 ID {run['run_id']} · {LABELS.get(run['status'], run['status'])}")
        done = sum(s["status"] not in ("pending", "running") for s in run["agents"].values())
        st.progress(done / 4, text=f"4개 역할 중 {done}개 처리")
        evidence = run.get("evidence")
        if evidence:
            message = f"데이터 출처: {evidence['source']} · {evidence['reason']}"
            if evidence["source"] == "mock" or evidence["facts"].get("is_mock"):
                st.warning(message)
            else:
                st.info(message)
            st.caption("자료 기준: " + evidence["facts"]["as_of"])
            with st.expander("데이터 출처 확인"):
                for source in evidence["facts"].get("sources", []):
                    st.link_button(source["title"], source["url"])
    for pair in [("weather_agent", "place_agent"), ("budget_agent", "validation_agent")]:
        for column, agent in zip(st.columns(2), pair):
            with column:
                agent_panel(agent, run["agents"][agent] if run else {})
    if run and run.get("budget"):
        st.subheader("계산된 예산")
        costs = run["budget"]
        if costs.get("line_items"):
            st.dataframe([{"항목": line["category"], "유형·계획": line["detail"], "계산 근거": line["formula"], "1인 합계 (원)": "미확인 · 제외" if line["per_person_total"] is None else f"{line['per_person_total']:,}"} for line in costs["line_items"]], hide_index=True)
        else:
            st.table([{"항목": k, "금액 (원)": f"{v:,}"} for k, v in costs["items"].items()])
        st.write(f"**합계 {costs['total']:,}원 / 남은 예산 {costs['remaining']:,}원**")
        st.caption(costs["scope"])
        if costs.get("unpriced_places"):
            st.caption("요금 미확인 · 합계 제외: " + ", ".join(costs["unpriced_places"]))
    if run and run.get("validation"):
        validation = run["validation"]
        if validation["verdict"] == "passed":
            st.success("검증 완료: 실행 및 예산 조건을 충족했습니다.")
        else:
            st.warning("추가 확인 필요: 요금 미확인·예산 초과·모의 사용·실패 항목을 확인하세요.")
        st.caption(validation["notice"])
    if run:
        if run.get("storage"):
            st.caption("실행 기록 저장 · PostgreSQL: " + run["storage"].get("postgres", "대기") + " / Redis: " + run["storage"].get("redis", "대기"))
        with st.expander("실행 타임라인", expanded=True):
            st.dataframe(run["trace"], hide_index=True)
        with st.expander("백엔드 응답 · 데이터 연결 결과"):
            st.json(run)
        st.download_button("실행 결과 JSON 다운로드", data=__import__('json').dumps(run, ensure_ascii=False, indent=2), file_name="trip-" + run["run_id"] + ".json", mime="application/json")


monitor()
with st.expander("저장된 실행 내역"):
    if st.button("DB 실행 내역 조회"):
        try:
            records = api("GET", "/api/multi/history")
            st.session_state["history"] = records
        except httpx.HTTPError:
            st.warning("실행 내역 저장소에 연결할 수 없습니다.")
    if st.session_state.get("history"):
        records = st.session_state["history"]
        st.caption("조회 저장소: " + records["storage"])
        st.dataframe(records["runs"], hide_index=True)
        if records["runs"]:
            record_id = st.selectbox("저장된 실행 선택", [r["run_id"] for r in records["runs"]])
            if st.button("저장된 결과 열기", disabled=st.session_state.get("active", False)):
                try:
                    st.session_state["snapshot"] = api("GET", "/api/multi/runs/" + record_id)
                    st.rerun()
                except httpx.HTTPError:
                    st.warning("해당 결과를 불러오지 못했습니다.")
st.caption("실행 내역은 전용 PostgreSQL에, 상태 캐시는 Redis에 저장합니다. 연결 실패 시 메모리로 동작하며 이 경우 재배포 시 기록이 사라집니다.")
