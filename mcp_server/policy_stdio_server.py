# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\mcp_server\policy_stdio_server.py
# [Role] MCP Server tools and resources
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

"""호텔 정책을 제공하는 stdio MCP Server입니다.

stdio의 stdout은 MCP 메시지 전용이므로 일반 로그는 출력하지 않습니다.
"""

# Literal은 호텔 ID처럼 허용된 값의 집합을 타입 힌트로 문서화한다.
from typing import Literal

# FastMCP는 Python 함수를 MCP Tool로 공개하는 서버 구성 도구다.
from mcp.server.fastmcp import FastMCP


# 이 Server는 HTTP 포트가 아니라 Backend가 만든 자식 프로세스의 stdio를 사용한다.
mcp = FastMCP(
    "mini-agent-policy",
    instructions="호텔 ID로 체크인 및 취소 정책을 제공합니다.",
)


# 함수명·docstring·타입 힌트를 읽어 tools/list에 Tool Schema로 등록한다.
# [MCP registration] Publishes the function as a Tool or Resource contract.
@mcp.tool()
def get_hotel_policy(
    hotel_id: Literal["hotel-busan-001", "hotel-seoul-001"],
) -> dict:
    """호텔 검색 결과의 hotel_id로 체크인 및 취소 정책을 조회합니다."""
    # hotel_id는 앞선 호텔 검색 결과의 식별자다.
    # Literal은 존재하는 호텔 ID만 허용하는 입력 계약이다.
    policies = {
        # 바깥 dict의 key가 hotel_id이고, 값은 해당 호텔의 세부 정책 dict다.
        "hotel-busan-001": {
            "hotel_name": "바다 호텔",
            "check_in": "15:00",
            "check_out": "11:00",
            "cancellation": "체크인 2일 전까지 무료 취소",
        },
        "hotel-seoul-001": {
            "hotel_name": "도시 호텔",
            "check_in": "15:00",
            "check_out": "11:00",
            "cancellation": "체크인 1일 전까지 무료 취소",
        },
    }
    # **는 안쪽 dict의 key/value를 현재 결과 dict에 펼치는 unpacking 문법이다.
    # 예: {"hotel_name": "바다 호텔", "check_in": "15:00"}가 합쳐진다.
    return {
        "hotel_id": hotel_id,
        **policies[hotel_id],
        "source": "hotel-policy-service",
    }


# [Execution boundary] Starts only when run directly, not when imported.
if __name__ == "__main__":
    # Backend가 이 파일을 자식 Python 프로세스로 실행할 때만 Server를 시작한다.
    # stdio의 stdout은 MCP 메시지 전용 통로이므로 일반 print 로그를 섞으면 안 된다.
    # transport="stdio"는 stdin/stdout을 MCP 통신 채널로 선택한다.
    mcp.run(transport="stdio")
