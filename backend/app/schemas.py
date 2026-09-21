# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\backend\app\schemas.py
# [Role] Backend API, agent, service, and storage layer
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

# Any는 값의 구체적인 타입이 Tool마다 달라질 수 있을 때 쓰는 타입 힌트다.
from typing import Any

# BaseModel은 JSON을 Python 객체로 검증하고 다시 JSON으로 변환하는 기반 클래스다.
# Field는 문자열 길이 같은 입력 제약을 선언한다.
from pydantic import BaseModel, Field


class McpRunRequest(BaseModel):
    # Frontend의 POST Body가 따라야 할 입력 계약이다.
    # {"question": "..."}이 들어오면 FastAPI/Pydantic이 이 모델 객체로 변환한다.
    question: str = Field(min_length=1, max_length=500)
    # question: str은 문자열만 허용한다는 힌트이고,
    # Field는 빈 질문과 500자를 넘는 질문을 API 입구에서 막는다.


class ToolExecutionTrace(BaseModel):
    # Agent가 각 Round에서 실행한 Tool 하나의 기록 구조다.
    # Frontend가 "어떤 Tool에 어떤 인자를 주었나"를 보여줄 때 사용한다.
    round: int
    # 1부터 시작하는 Agent 반복 번호다.
    server: str
    # 실제 MCP Server 이름. 예: travel, policy
    tool: str
    # Server 안의 원래 Tool 이름. 예: search_hotels
    public_tool: str
    # GPT에게 공개한 prefix 포함 이름. 예: travel__search_hotels
    arguments: dict[str, Any]
    # 실제 Tool에 전달한 인자 dict다. Tool마다 값 타입이 달라 Any를 사용한다.
    is_error: bool
    # MCP 결과가 오류였는지 나타내는 참/거짓 값이다.
    result: str
    # MCP 결과의 텍스트 content를 합친 문자열이다.


class McpRunResult(BaseModel):
    # /api/mcp/run 성공 시 Frontend로 반환할 전체 응답 계약이다.
    question: str
    # 처리한 원본 질문이다.
    model: str
    # 사용한 LLM 모델 이름이다.
    available_tools: list[str]
    # 이번 실행에서 GPT에게 공개된 Tool 이름 목록이다.
    llm_calls: int
    # Responses API 호출 횟수다.
    trace: list[ToolExecutionTrace]
    # Tool 실행 기록을 실행 순서대로 담는다.
    answer: str
    # Tool 호출이 끝난 뒤 LLM이 만든 최종 답변이다.
