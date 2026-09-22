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
    st.caption("EC2 CPU 추론: 네 역할 분석에 약 2~3분이 걸릴 수 있습니다.")
    if config.get("demo_enabled", True) and st.button("전체 모델을 mock으로 전환"):
        for agent in ROLES:
            st.session_state["provider_" + agent] = "mock"
    selected = {}
    for agent, (title, _) in ROLES.items():
        default = config["defaults"].get(agent, "mock")
        choices = config["providers"]
        st.session_state.setdefault("provider_" + agent, default if default in choices else "mock")
        selected[agent] = st.selectbox(title, choices, index=None, key="provider_" + agent)
        st.caption(config["models"].get(selected[agent], "모델을 선택해 주세요."))
        if not config["configured"].get(selected[agent]):
            st.caption("서버 키/주소 미설정 · 모의 응답 허용 시 대체됩니다.")
    allow_mock = st.checkbox("모델 호출 실패 시 모의 응답 허용", value=False) if config.get("demo_enabled", True) else False
    st.caption("기본 모델은 EC2 Ollama입니다. OpenAI·Gemini는 유효한 키와 사용 한도가 필요합니다.")

active = st.session_state.get("active", False)
with st.form("trip_request"):
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
    with st.expander("계획 단가 · 실제 예약 견적 아님"):
        hotel = st.number_input("숙박 1박 계획 단가 (원)", min_value=0, max_value=10000000, value=80000, step=10000)
        food = st.number_input("식비 1일 계획 단가 (원)", min_value=0, max_value=1000000, value=30000, step=5000)
        transport = st.number_input("현지 교통 1일 계획 단가 (원)", min_value=0, max_value=1000000, value=15000, step=1000)
    submitted = st.form_submit_button("멀티에이전트 실행", type="primary", disabled=active or any(value is None for value in selected.values()))
if submitted:
    try:
        run = api("POST", "/api/multi/runs", json={"city": city, "days": days, "budget": budget,
                  "question": question, "hotel_per_night": hotel, "food_per_day": food, "transport_per_day": transport, "providers": selected, "data_mode": data_mode, "allow_model_mock": allow_mock})
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
