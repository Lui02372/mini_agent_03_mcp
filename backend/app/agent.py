# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\backend\app\agent.py
# [Role] Backend API, agent, service, and storage layer
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

"""HTTP와 stdio MCP Tool을 순차 실행하는 Agent Loop입니다.

전체 흐름
    질문 → 각 MCP Server의 tools/list → Server prefix가 붙은 Tool Schema 생성
    → GPT가 이번 단계에 필요한 Tool 하나 선택
    → Backend가 라우팅 테이블로 원래 Server의 Tool 실행
    → function_call_output을 GPT에 전달하고 반복
    → GPT가 Function Call 없이 답변하면 종료
"""

# json은 GPT가 문자열로 준 arguments를 dict로 바꾸고, Tool 결과를 다시 문자열로 포장할 때 쓴다.
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
# AsyncOpenAI는 네트워크 대기 동안 다른 비동기 작업을 막지 않는 OpenAI Client다.
from openai import AsyncOpenAI

from .mcp_client import mcp_sessions, result_text
from .schemas import McpRunResult, ToolExecutionTrace


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
MAX_AGENT_ROUNDS = 8
INSTRUCTIONS = (
    "당신은 한국 여행 도우미입니다. 질문을 완전히 해결하는 데 필요한 Tool을 "
    "한 단계씩 사용하세요. 호텔 정책을 요청받으면 반드시 먼저 호텔을 검색하고, "
    "검색 결과에서 얻은 hotel_id로 정책을 조회하세요. Tool 결과만 근거로 한국어 "
    "최종 답변을 작성하세요."
)


def to_openai_tool(
    server_name: str,
    tool,
) -> tuple[dict[str, Any], dict[str, str]]:
    # [1] server_name: str에서 :와 str의 의미
    # server_name은 매개변수(함수가 호출될 때 외부에서 받는 값)의 이름이다.
    # 콜론(:) 뒤의 str은 "이 값은 문자열이어야 한다"는 타입 힌트다.
    # 예: server_name = "travel"
    # 타입 힌트는 변수에 값을 강제로 막는 문법이 아니다. Python은 기본적으로
    # 실행할 때 타입 힌트를 강제하지 않으며, 사람·IDE·정적 검사기가 계약을 이해하도록 돕는다.

    # [2] tool에 타입 힌트가 없는 이유
    # tool은 MCP SDK의 response.tools에서 들어오는 객체인데, 이 프로젝트에서는
    # SDK의 구체적인 Tool 모델 타입을 직접 import하지 않고 있다.
    # 따라서 tool은 어떤 객체든 받을 수 있는 "타입을 생략한 매개변수"가 되었다.
    # 실제 실행 시에는 name, description, model_dump()를 가진 MCP Tool 객체가 들어온다.
    # 즉 "타입이 없다"기보다 이 함수 선언에서 타입을 명시하지 않은 것이다.
    # 더 엄격하게 쓰려면 SDK가 제공하는 Tool 타입을 찾아 다음처럼 적을 수 있다.
    #     tool: SomeMcpToolType
    # 하지만 SDK 버전에 따라 타입 이름과 import 위치가 달라질 수 있어 현재 코드는 생략했다.

    # [3] 편집기에서 tool이 주황색으로 보이는 이유
    # 주황색은 Python 문법이 정한 의미가 아니라 VS Code/PyCharm 등의
    # 테마와 semantic highlighting(의미 기반 색상)이 정한 표시 방식이다.
    # 테마에 따라 매개변수는 주황색, 함수는 노란색, 문자열은 초록색처럼 보일 수 있다.
    # 색 자체가 "보안", "오류", "특별한 Python 타입"을 의미하지는 않는다.

    # [4] -> tuple[...]을 해석하는 법
    # -> 뒤는 함수의 반환 타입 힌트다.
    # tuple[A, B]는 "tuple 하나를 반환하는데, 그 안에 A 타입 값과 B 타입 값이
    # 순서대로 들어 있다"는 뜻이다.
    # 여기서 반환 tuple은 정확히 다음 모양이다.
    #     (openai_tool, route)
    # 첫 번째 값: dict[str, Any]  → GPT에게 전달할 OpenAI Tool 설명서
    # 두 번째 값: dict[str, str]  → Backend가 실제 MCP Server를 찾는 라우팅 지도
    # tuple은 서로 관련된 여러 값을 순서를 유지한 채 한 번에 반환할 때 쓴다.
    # 예: return ("여행", 3) 후 category, count = 함수()처럼 받을 수 있다.
    # 함수 안에 public_name, raw, openai_tool, route라는 변수가 여러 개 만들어져도
    # 반환하는 값은 return 문에 적힌 openai_tool과 route, 즉 2개뿐이다.
    # [5] public_name: 공개용 이름 만들기
    # tool.name은 Server 안에서의 원래 이름이고, server_name은 소속 Server 이름이다.
    # f"..."는 f-string이며 중괄호 안의 값을 문자열에 삽입한다.
    # 예: server_name="travel", tool.name="search_hotels"
    #     public_name = "travel__search_hotels"
    # 밑줄 2개(__)는 Python 문법의 특별한 명령이 여기서 실행되는 것이 아니다.
    # 이 프로젝트가 정한 "Server 이름과 Tool 이름을 나누는 구분자"다.
    # Server prefix를 붙이는 이유는 travel Server와 policy Server에 같은 Tool 이름이
    # 생겨도 GPT에게는 서로 다른 공개 이름으로 보이게 하기 위해서다.
    public_name = f"{server_name}__{tool.name}"

    # [6] raw: SDK 객체를 일반 Python dict로 펼친 중간 자료
    # tool은 MCP SDK가 만든 객체다. 객체의 속성에 직접 접근할 수도 있지만,
    # OpenAI에 보낼 JSON 모양을 조립하려면 일반 dict가 편하다.
    # model_dump()는 Pydantic 계열 모델 객체를 dict로 변환하는 함수다.
    # raw라는 이름은 "가공 전 원본에 가까운 dict"라는 뜻의 관례적인 변수명이다.
    # raw 안에는 보통 name, description, inputSchema 같은 정보가 들어 있다.
    #
    # by_alias=True의 의미
    # 모델 내부 Python 필드명이 input_schema일 수 있지만, 외부 프로토콜이 요구하는
    # 이름은 inputSchema일 수 있다. alias는 "외부에 보여줄 별칭"이다.
    # True는 model_dump()에게 "Python 내부 이름 대신 외부 별칭을 사용하라"고 지시한다.
    # 그래서 아래 raw["inputSchema"]가 정상적으로 동작하도록 한다.
    raw = tool.model_dump(by_alias=True)

    # [7] openai_tool: GPT가 읽을 최종 Tool 설명서
    # 이 변수는 실제 Tool을 실행한 결과가 아니다. GPT에게 선택지를 알려주는
    # JSON-compatible Python dict다. 나중에 responses.create(tools=openai_tools)에 들어간다.
    openai_tool = {
        # OpenAI에게 이것은 "함수 호출 형태의 Tool"이라고 알려주는 고정 표식이다.
        "type": "function",
        # OpenAI가 function_call에서 돌려줄 이름이다. 원래 MCP 이름이 아니라 prefix 이름이다.
        "name": public_name,
        # GPT가 언제 이 Tool을 선택할지 판단하는 자연어 설명이다.
        "description": f"[{server_name} MCP Server] {tool.description or ''}",
        # [8] parameters: 함수가 받을 입력의 JSON Schema
        # parameters는 실제 값이 아니라 "어떤 인자를 어떤 타입으로 받아야 하는가"를
        # 설명하는 Schema 자리다. OpenAI function Tool 계약에서 이 키 이름을 사용한다.
        # raw["inputSchema"]에서 대괄호 []는 raw dict 안의 "inputSchema"라는 키를
        # 조회하는 dict indexing 문법이다. 문자열로 쓰는 이유는 dict의 키가 문자열이기 때문이다.
        # 예: raw = {"inputSchema": {"type": "object", ...}}라면
        #     raw["inputSchema"] = {"type": "object", ...}
        # 즉 대괄호 안의 "inputSchema"는 함수 호출이 아니라 dict에서 값을 꺼내는 열쇠다.
        "parameters": raw["inputSchema"],
        # strict=False는 Schema를 엄격하게 강제하는 수준을 낮추는 설정이다.
        # 이 프로젝트는 MCP에서 받은 Schema를 그대로 연결하는 교육용 구조다.
        "strict": False,
    }

    # [9] route: 실행용 목적지 지도
    # openai_tool은 GPT가 읽는 이름을 사용하지만, 실제 MCP 호출은 Server Session과
    # 원래 Tool 이름을 알아야 한다. 그래서 공개 이름과 실행 목적지를 따로 보관한다.
    route = {"server": server_name, "tool": tool.name}

    # [10] return은 "함수 안에서 계산한 값을 호출자에게 돌려주는 문장"이다.
    # 호출자는 다음처럼 두 변수에 순서대로 받을 수 있다.
    #     openai_tool, route = to_openai_tool(server_name, tool)
    # 변수 4개(public_name, raw, openai_tool, route)를 만든 것과
    # 반환 값 2개(openai_tool, route)는 서로 다른 개념이다.
    return openai_tool, route


async def run_agent(question: str) -> McpRunResult:
    # 질문 하나를 해결하는 전체 Agent 오케스트레이터다.
    # 내부에서 LLM 판단과 MCP 실제 실행을 번갈아 수행한다.
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY가 필요합니다.")

    trace: list[ToolExecutionTrace] = []
    llm_calls = 0

    # async with는 네트워크 Client와 MCP Session을 열고, 함수가 끝나면 자동으로 닫는다.
    async with AsyncOpenAI() as client, mcp_sessions() as sessions:
        openai_tools: list[dict[str, Any]] = []
        routes: dict[str, dict[str, str]] = {}

        # 먼저 모든 Server의 Tool Schema를 모아 GPT에게 선택지로 제공한다.
        for server_name, session in sessions.items():
            discovered = (await session.list_tools()).tools
            for tool in discovered:
                openai_tool, route = to_openai_tool(server_name, tool)
                openai_tools.append(openai_tool)
                routes[openai_tool["name"]] = route

        previous_response_id: str | None = None
        # 첫 Round에는 사용자의 질문 문자열을 넣고, Tool을 실행한 뒤에는
        # function_call_output 목록으로 바뀐다. 같은 변수지만 Agent Loop의 단계에 따라
        # "새 질문"과 "직전에 요청한 Tool의 결과"를 번갈아 운반하는 입력 버스다.
        input_items: str | list[dict[str, str]] = question

        # Agent Loop: 판단 → Tool 실행 → 결과 전달 → 다음 판단.
        # +1은 range의 끝 숫자를 포함하지 않기 때문에 8회까지 포함하려는 것이다.
        for round_number in range(1, MAX_AGENT_ROUNDS + 1):
            # round_number는 단순 반복 횟수가 아니라 한 번의 LLM 판단 사이클 번호다.
            # 1부터 시작하면 trace 화면에서 사람이 읽기 쉽고, +1은 range의 끝을 포함시키기 위한 것이다.
            # GPT 호출은 Tool을 직접 실행하는 것이 아니라 function_call 제안을 받는 단계다.
            response = await client.responses.create(
                model=OPENAI_MODEL,
                instructions=INSTRUCTIONS,
                input=input_items,
                previous_response_id=previous_response_id,
                tools=openai_tools,
                parallel_tool_calls=False,
            )
            # response는 텍스트, function_call, id가 들어 있는 응답 객체다.
            # 다음 단계에서 response.output을 검사해 "답변 완료"인지 "외부 Tool 실행 필요"인지 결정한다.
            llm_calls += 1
            # 일반 텍스트 응답과 function_call 응답이 섞일 수 있으므로 호출만 필터링한다.
            tool_calls = [
                item for item in response.output if item.type == "function_call"
            ]

            if not tool_calls:
                return McpRunResult(
                    question=question,
                    model=OPENAI_MODEL,
                    available_tools=sorted(routes),
                    llm_calls=llm_calls,
                    trace=trace,
                    # function_call이 없다는 것은 이번 응답이 최종 자연어 답변이라는 뜻이다.
                    # output_text는 response 전체나 output 항목 목록을 노출하지 않고
                    # 프론트에 전달할 텍스트만 추출한 값이다.
                    answer=response.output_text,
                )

            # parallel_tool_calls=False이므로 이 예제에서는 첫 번째 호출 하나만 순차 실행한다.
            call = tool_calls[0]
            route = routes.get(call.name)
            if route is None:
                raise ValueError(
                    f"MCP Server가 제공하지 않는 Tool입니다: {call.name}"
                )

            # call.arguments는 JSON 문자열이다.
            # json.loads는 문자열을 Python dict로 역직렬화해야 call_tool 인자로 넘길 수 있다.
            arguments = json.loads(call.arguments)
            # 모델은 arguments를 JSON 문자열로 보낸다. MCP Session의 call_tool은
            # Python dict를 인자로 기대하므로 여기서 문자열(JSON) -> dict로 변환한다.
            # 이 변환이 없으면 Tool은 "문자열 하나"를 받아 필드별 인자를 읽을 수 없다.
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments는 JSON Object여야 합니다.")

            # GPT는 공개 이름(travel__search_hotels)을 골랐지만,
            # 실제 실행은 route가 가리키는 Session의 원래 Tool 이름으로 한다.
            result = await sessions[route["server"]].call_tool(
                route["tool"],
                arguments,
            )
            output = result_text(result)
            trace.append(ToolExecutionTrace(
                # round를 기록하면 같은 요청 안에서 Tool이 몇 번째 판단 후 실행됐는지
                # 확인할 수 있다. 디버깅·발표·평가에서 LLM과 Tool의 순서를 복원하는 정보다.
                round=round_number,
                server=route["server"],
                tool=route["tool"],
                public_tool=call.name,
                arguments=arguments,
                is_error=bool(result.isError),
                result=output,
            ))

            # Tool 결과를 다시 GPT가 읽는 function_call_output 구조로 포장한다.
            tool_output = {
                "server": route["server"],
                "tool": route["tool"],
                "success": not bool(result.isError),
                "content": output,
            }
            previous_response_id = response.id
            # 다음 responses.create에 이전 응답 id를 넘기면 OpenAI가 앞선 판단과 연결한다.
            # call_id와 함께 사용해야 모델이 "내가 요청한 바로 그 호출의 결과"로 이해한다.
            # 다음 LLM Round의 입력이다. 앞 호출의 call_id와 결과를 연결해야
            # GPT가 "내가 요청한 Tool의 결과"로 이해할 수 있다.
            input_items = [{
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": json.dumps(tool_output, ensure_ascii=False),
            }]

    raise RuntimeError(
        f"최대 Agent 반복 횟수({MAX_AGENT_ROUNDS})를 초과했습니다."
    )
