# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\backend\app\main.py
# [Role] Backend API, agent, service, and storage layer
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

# FastAPI는 Python 함수에 HTTP 주소를 연결해 Backend API 서버를 만든다.
# HTTPException은 내부 오류를 HTTP 상태 코드와 메시지로 변환할 때 쓴다.
from fastapi import FastAPI, HTTPException

from .agent import run_agent
from .mcp_client import MCP_SERVERS, discover_resources, discover_tools, read_resource
from .schemas import McpRunRequest, McpRunResult


# FastAPI()는 애플리케이션 객체를 만든다.
# 아래 데코레이터들은 이 객체에 "어떤 URL이 어떤 함수를 호출하는가"를 등록한다.
app = FastAPI(title="Mini Agent 03 MCP", version="1.0.0")


# @app.get(...)은 데코레이터다.
# 함수 자체를 실행하는 것이 아니라, health() 함수를 GET /health 경로에 등록한다.
# 즉 브라우저/클라이언트가 GET /health를 요청하면 FastAPI가 health()를 호출한다.
# [HTTP route] Maps an HTTP method and URL to the function below.
@app.get("/health")
def health() -> dict:
    # -> dict는 health()의 반환값이 Python dict라는 타입 힌트다.
    # FastAPI는 dict를 JSON 응답으로 변환해 네트워크로 보낸다.
    return {
        "status": "ok",
        "stage": "mini_agent_03_mcp",
        "mcp_servers": {
            name: config["transport"]
            for name, config in MCP_SERVERS.items()
        },
    }


# /api/mcp/status는 함수명이 아니라 API 리소스 주소다.
# GET은 서버 상태를 읽는 요청이므로 @app.get을 사용한다.
# [HTTP route] Maps an HTTP method and URL to the function below.
@app.get("/api/mcp/status")
async def mcp_status():
    # async def는 네트워크 대기 중 다른 작업이 멈추지 않도록 설계된 비동기 함수다.
    # await discover_tools()는 결과가 올 때까지 기다리되, 대기 시간 동안 이벤트 루프에
    # 제어권을 돌려준다. MCP 연결은 네트워크/프로세스 I/O이므로 async가 적합하다.
    try:
        tools = await discover_tools()
        return {
            "status": "connected",
            "servers": [
                {
                    "name": name,
                    "transport": config["transport"],
                    "endpoint": config.get("url", "child process"),
                }
                for name, config in MCP_SERVERS.items()
            ],
            "tool_count": len(tools),
        }
    except Exception as error:
        raise HTTPException(
            status_code=503,
            detail=f"MCP Server 연결 실패: {error}",
        ) from error


# Tool 목록 조회는 데이터를 읽는 작업이므로 GET으로 표현한다.
# [HTTP route] Maps an HTTP method and URL to the function below.
@app.get("/api/mcp/tools")
async def list_mcp_tools():
    try:
        return {"tools": await discover_tools()}
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Tool 발견 실패: {error}") from error


# Resource 목록 조회도 읽기 작업이므로 GET이다.
# [HTTP route] Maps an HTTP method and URL to the function below.
@app.get("/api/mcp/resources")
async def list_mcp_resources():
    try:
        return {"resources": await discover_resources()}
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Resource 발견 실패: {error}") from error


# 특정 Resource 내용을 읽는 주소다. URL에 동작 동사보다 대상 이름을 표현한다.
# [HTTP route] Maps an HTTP method and URL to the function below.
@app.get("/api/mcp/baggage-policy")
async def baggage_policy():
    try:
        content = await read_resource("travel", "travel://policy/baggage")
        return {"uri": "travel://policy/baggage", "content": content}
    except Exception as error:
        raise HTTPException(status_code=503, detail=f"MCP Resource 읽기 실패: {error}") from error


# @app.post는 POST 요청과 Python 함수를 연결한다.
# /api/mcp/run은 "run이라는 함수를 URL로 쓴 것"이 아니라, Agent 실행을 요청하는 API 주소다.
# 질문은 요청 Body에 들어가므로 GET보다 POST가 알맞다.
# response_model은 반환 JSON의 구조를 McpRunResult로 검증·문서화한다.
# [HTTP route] Maps an HTTP method and URL to the function below.
@app.post("/api/mcp/run", response_model=McpRunResult)
async def run_mcp_agent(payload: McpRunRequest) -> McpRunResult:
    # payload는 Frontend가 보낸 JSON Body를 FastAPI가 McpRunRequest 객체로 변환한 값이다.
    # 즉 payload는 단순한 문자열이 아니라 question 필드를 가진 입력 객체다.
    # payload.question처럼 읽는 이유는 입력 데이터의 구조를 명확하게 유지하기 위해서다.
    # -> McpRunResult는 성공 시 반환할 응답 구조를 나타내는 타입 힌트다.
    try:
        # await는 Agent 내부의 OpenAI 호출과 MCP 호출이 끝날 때까지 기다린다.
        return await run_agent(payload.question)
    except ValueError as error:
        # ValueError는 입력값/API Key 등 요청 자체의 문제로 보고 400을 반환한다.
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        # 그 외 예상하지 못한 연결·서버 오류는 503으로 변환한다.
        raise HTTPException(status_code=503, detail=f"MCP Agent 실행 실패: {error}") from error
