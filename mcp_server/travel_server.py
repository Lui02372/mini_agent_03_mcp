# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\mcp_server\travel_server.py
# [Role] MCP Server tools and resources
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

"""8010 포트에서 독립 실행되는 여행 Streamable HTTP MCP Server입니다."""

# os는 서버 Host와 Port를 환경변수에서 읽기 위한 표준 모듈이다.
import os

# Literal은 허용할 입력값의 집합을 타입 힌트로 표현한다.
from typing import Literal

# FastMCP는 Python 함수에 MCP Tool/Resource 등록 기능을 제공한다.
from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse


# 환경변수와 기본값을 분리하면 같은 코드를 로컬/Docker 환경에서 재사용할 수 있다.
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
# getenv 결과는 문자열이므로 포트 계산에 쓰기 전에 int로 변환한다.
MCP_PORT = int(os.getenv("MCP_PORT", "8010"))

# 이 객체에 등록된 Tool과 Resource가 MCP Server의 공개 목록이 된다.
# instructions는 Client가 Server의 역할을 이해할 수 있는 설명이다.
mcp = FastMCP(
    "mini-agent-travel",
    instructions="현재 날씨, 호텔, 여행 정책을 제공하는 교육용 서버입니다.",
    host=MCP_HOST,
    port=MCP_PORT,
    stateless_http=True,
    json_response=True,
)


# @mcp.tool()은 아래 함수를 tools/list 결과에 등록하는 데코레이터다.
# FastMCP는 함수명·docstring·타입 힌트를 읽어 Tool Schema를 만든다.
# [MCP registration] Publishes the function as a Tool or Resource contract.
@mcp.tool()
def get_current_weather(city: Literal["부산", "서울"]) -> dict:
    """도시의 현재 날씨를 조회합니다."""
    # city: Literal[...]은 모든 문자열이 아니라 부산/서울만 허용하는 입력 계약이다.
    # -> dict는 결과가 JSON Object로 표현될 수 있는 Python dict라는 뜻이다.
    normalized = city.strip()
    # 앞뒤 공백을 제거해 입력 비교를 안정적으로 만든다.
    if not normalized:
        # 잘못된 입력은 조용히 빈 결과를 만들기보다 명확한 오류로 알려준다.
        raise ValueError("city는 빈 문자열일 수 없습니다.")
    # Tool의 Python 반환값은 MCP 결과로 직렬화되어 Client로 전달된다.
    return {
        "city": normalized,
        "condition": "맑음",
        "temperature_c": 24,
        "source": "travel-weather-service",
    }


# 같은 Tool 등록 데코레이터지만, 이번 함수는 검색 조건 인자가 두 개다.
# [MCP registration] Publishes the function as a Tool or Resource contract.
@mcp.tool()
def search_hotels(
    city: Literal["부산", "서울"],
    max_price: int = 150_000,
) -> dict:
    """도시와 1박 최대 가격으로 호텔을 검색합니다."""
    # max_price=150_000에서 숫자 중간의 _는 가독성을 위한 표기이며 값은 150000이다.
    normalized = city.strip()
    if not normalized:
        raise ValueError("city는 빈 문자열일 수 없습니다.")
    if max_price < 1:
        raise ValueError("max_price는 1 이상이어야 합니다.")
    # 실제 DB 대신 학습용 고정 목록을 사용한다.
    # list 안의 dict 구조는 여러 검색 결과를 JSON 배열로 만들기 쉽다.
    hotels = [
        {
            "hotel_id": "hotel-busan-001",
            "name": "바다 호텔",
            "city": "부산",
            "price": 120_000,
        },
        {
            "hotel_id": "hotel-seoul-001",
            "name": "도시 호텔",
            "city": "서울",
            "price": 140_000,
        },
    ]
    # list comprehension은 hotels를 순회하며 조건에 맞는 호텔만 새 list로 만든다.
    return {
        "items": [
            hotel for hotel in hotels
            if hotel["city"] == normalized and hotel["price"] <= max_price
        ],
        "source": "travel-hotel-catalog",
    }


# Tool은 작업 실행, Resource는 URI로 읽는 정보다.
# 이 데코레이터는 함수 결과를 travel://policy/baggage 주소에 연결한다.
# [MCP registration] Publishes the function as a Tool or Resource contract.
@mcp.resource("travel://policy/baggage")
def baggage_policy() -> str:
    """교육용 국내선 수하물 정책입니다."""
    # -> str은 Resource 내용이 문자열이라는 반환 타입 힌트다.
    return "교육용 국내선의 위탁 수하물은 15kg까지 허용합니다."


# [Execution boundary] Starts only when run directly, not when imported.

@mcp.tool()
async def get_trip_evidence(city: Literal["서울", "부산", "제주"], mode: Literal["auto", "mock"] = "auto") -> dict:
    """Read cached/database travel facts; explicitly label sample data on failure."""
    from backend.app.multi_data import load_evidence
    return (await load_evidence(city, mode)).model_dump()


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    # 파일을 직접 실행할 때만 Server를 시작한다.
    # 다른 코드가 이 모듈을 import해도 서버가 자동으로 켜지지 않는다.
    # streamable-http는 MCP 메시지를 HTTP endpoint로 제공하는 Transport다.
    mcp.run(transport="streamable-http")
