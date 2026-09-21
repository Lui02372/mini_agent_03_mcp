# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\frontend\app.py
# [Role] Frontend UI and Backend API calls
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

# os는 운영체제 환경변수(BACKEND_API_URL)를 읽기 위한 표준 라이브러리다.
import os

# httpx는 보안 라이브러리가 아니라 "다른 HTTP 서버에 요청을 보내는 Client"다.
# 브라우저의 fetch(), Java의 HTTP Client와 같은 역할을 Python에서 한다.
# HTTPS 주소를 사용하면 TLS 암호화가 적용되지만, 암호화 자체는 httpx가 단독으로
# 보장하는 것이 아니다. 서버 주소가 http://인지 https://인지가 보안에 중요하다.
import httpx

# Streamlit은 Python 코드의 실행 결과를 웹 화면으로 그리는 Frontend 프레임워크다.
# st.button(), st.text_input() 같은 호출은 화면 요소를 만들고, 사용자의 입력값을
# Python 변수로 가져오는 역할을 한다.
import streamlit as st


# 환경변수에 Backend 주소가 있으면 그것을 사용하고, 없으면 로컬 개발 주소를 쓴다.
# .rstrip("/")는 주소 끝의 /를 제거한다.
# 그래야 BASE_URL + "/api/mcp/run"을 조합할 때 //가 생기지 않는다.
BASE_URL = os.getenv("BACKEND_API_URL", "http://127.0.0.1:8000").rstrip("/")


def get(path: str) -> dict:
    # def는 "이 작업을 나중에 여러 번 실행할 수 있도록 이름을 붙여 저장"하는 문법이다.
    # path: str에서 :는 path 매개변수에 문자열을 기대한다는 타입 힌트다.
    # -> dict에서 ->는 이 함수가 dict 형태를 반환할 예정이라는 반환 타입 힌트다.
    # 타입 힌트는 실행 순서를 만드는 명령이 아니라, 사람·IDE·정적 검사기를 위한 계약이다.

    # f-string은 문자열 안에 변수값을 끼워 넣는 문법이다.
    # 예: path가 "/api/mcp/status"이면 전체 URL은
    # "http://127.0.0.1:8000/api/mcp/status"가 된다.
    response = httpx.get(f"{BASE_URL}{path}", timeout=30)

    # HTTP 요청이 네트워크까지 도착했더라도 404·500 같은 실패 응답일 수 있다.
    # raise_for_status()는 실패 상태를 Python 예외로 바꿔 아래 try/except가 처리하게 한다.
    response.raise_for_status()

    # 서버가 보낸 JSON 문자열을 Python dict/list/str/number 구조로 역직렬화한다.
    # JSON은 Frontend와 Backend가 서로 다른 프로세스·언어여도 해석하기 쉬운 공통 형식이다.
    return response.json()


def post(path: str, payload: dict) -> dict:
    # GET은 보통 "읽기", POST는 "서버에 처리할 데이터 전달"에 사용한다.
    # 여기서 payload는 질문처럼 Backend가 처리해야 할 입력을 담은 운반용 dict다.
    # payload라는 이름 자체가 특별한 키워드는 아니며, data_to_send라고 불러도 된다.
    # 다만 API 요청 본문(body)을 뜻하는 관례적인 이름으로 많이 사용한다.

    # json=payload의 의미
    # 1) payload Python dict를 JSON 문자열로 직렬화한다.
    # 2) 요청 Body에 넣는다.
    # 3) Content-Type: application/json을 알맞게 설정한다.
    # 따라서 아래 payload는 다음 전송 데이터가 된다.
    # {"question": "부산에서 15만원 이하 호텔을 찾아 주세요."}
    # json=를 쓰는 이유는 Backend의 Pydantic 모델(McpRunRequest)이 JSON Body를
    # 읽도록 설계되어 있기 때문이다. query string이나 form-data로 보내면 같은 계약이 아니다.
    response = httpx.post(f"{BASE_URL}{path}", json=payload, timeout=60)

    # POST는 요청을 보냈다는 사실만으로 성공이 아니다.
    # 서버가 400(입력 오류), 503(연결/서버 오류)를 응답할 수 있으므로 상태 코드를 확인한다.
    response.raise_for_status()

    # Backend가 반환한 JSON 응답을 다시 Frontend가 사용할 Python dict로 바꾼다.
    return response.json()


# 이 호출은 화면의 기본 설정을 만든다. 일반적으로 다른 Streamlit UI 호출보다 먼저 둔다.
st.set_page_config(page_title="Mini Agent 03 MCP", page_icon="🔌", layout="wide")
st.title("Mini Agent 03 · MCP")
st.caption(
    "FastAPI가 Streamable HTTP와 stdio MCP Server의 Tool을 발견하고 "
    "순차 Agent Loop로 호출합니다."
)

try:
    # Streamlit 파일은 위에서 아래로 다시 실행된다.
    # 이 시점에서 GET 요청을 보내 Backend와 MCP Server 연결 상태를 화면에 보여준다.
    status = get("/api/mcp/status")
    st.success(f"MCP 연결: {status['status']} · Tool {status['tool_count']}개")
    for server in status["servers"]:
        st.write(
            f"- `{server['name']}` · {server['transport']} · "
            f"{server['endpoint']}"
        )
except httpx.HTTPError:
    st.warning(
        "MCP Server에 연결할 수 없습니다. Travel 서버가 8010 포트에서 "
        "실행 중인지 확인하세요."
    )

if st.button("MCP Tool 발견"):
    # st.button()은 버튼을 그리고, 이번 실행에서 사용자가 클릭했으면 True를 반환한다.
    # 버튼 클릭이 없으면 아래 블록은 실행되지 않는다.
    try:
        st.json(get("/api/mcp/tools"))
    except httpx.HTTPError as error:
        st.error(f"Backend 호출 실패: {error}")

# text_input()은 화면에 입력창을 만들고 현재 입력값을 문자열로 반환한다.
# 반환된 문자열이 아래 post()의 payload 안에 들어간다.
question = st.text_input(
    "질문",
    "부산 날씨와 15만원 이하 호텔을 찾고, 검색된 호텔의 정책도 알려 주세요.",
)
if st.button("MCP Agent 실행", type="primary"):
    try:
        # Frontend의 질문을 Backend의 POST API로 전달한다.
        # URL의 /api/mcp/run은 Python 함수 이름이 아니라 HTTP 주소 규칙이다.
        # 이 주소를 실제 Python 함수 run_mcp_agent()에 연결하는 것은 Backend의 데코레이터다.
        result = post("/api/mcp/run", {"question": question})
        st.success(result["answer"])
        left, right = st.columns(2)
        left.metric("GPT 호출 횟수", result["llm_calls"])
        right.metric("실행된 Tool 수", len(result["trace"]))
        st.subheader("GPT가 선택하고 MCP가 실행한 Tool")
        # enumerate()는 리스트의 순번과 원소를 함께 준다.
        # index는 현재 코드에서 제목 번호에 직접 쓰이지 않지만, 학습용으로 순번을 받을 수 있다.
        for index, item in enumerate(result["trace"], start=1):
            title = (
                f"Round {item['round']} · {item['server']} · "
                f"{item['tool']}"
            )
            with st.expander(title, expanded=True):
                st.caption(f"Public Tool: {item['public_tool']}")
                st.write("Arguments")
                st.json(item["arguments"])
                st.write("Tool Result")
                st.code(item["result"])
                if item["is_error"]:
                    st.error("MCP Tool 실행 오류")
        with st.expander("전체 응답 JSON"):
            st.json(result)
    except httpx.HTTPError as error:
        st.error(f"Backend 호출 실패: {error}")

with st.expander("MCP Resource 확인"):
    if st.button("수하물 정책 읽기"):
        try:
            st.json(get("/api/mcp/baggage-policy"))
        except httpx.HTTPError as error:
            st.error(f"Backend 호출 실패: {error}")
