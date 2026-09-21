# DETAIL_COMMENT_HEADER
# ???뚯씪? 肄붾뱶???ㅽ뻾 寃곌낵肉??꾨땲??媛?援щЦ???낅젰쨌異쒕젰쨌怨꾩링 愿怨꾨? ?댄빐?섍린 ?꾪븳 ?숈뒿??二쇱꽍???ы븿?쒕떎.

# LEARNING_COMMENT_HEADER
# [File] mini_agent_03_mcp\backend\app\mcp_client.py
# [Role] Backend API, agent, service, and storage layer
# [Reading order] imports/settings -> data structures -> inputs -> processing -> return/UI/API
# These comments explain intent and structure; executable behavior is unchanged.

# os: 환경변수 읽기, sys: 현재 실행 중인 Python 인터프리터 경로 얻기
import os
import sys
# AsyncExitStack은 여러 비동기 연결을 한 번에 열고 반드시 닫기 위한 자원 관리자다.
# asynccontextmanager는 yield 전후에 실행될 연결 준비/정리 함수를 만들게 한다.
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
# ClientSession은 MCP 메시지를 주고받는 대화 세션이고,
# StdioServerParameters는 자식 MCP Server를 실행할 명령과 인자를 담는 구조다.
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

MCP_SERVERS: dict[str, dict[str, Any]] = {
    "travel": {
        "transport": "streamable-http",
        "url": os.getenv("TRAVEL_MCP_URL", "http://127.0.0.1:8010/mcp"),
    },
    "policy": {
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(PROJECT_ROOT / "mcp_server" / "policy_stdio_server.py")],
    },
}


async def open_session(
    stack: AsyncExitStack,
    config: dict[str, Any],
) -> ClientSession:
    # async def: HTTP/stdio처럼 기다림이 발생하는 I/O 함수를 비동기로 선언한다.
    # stack: AsyncExitStack은 이 함수가 연 Transport를 나중에 닫을 책임을 가진다.
    # config: dict[str, Any]는 문자열 키와 다양한 값의 설정 사전이라는 타입 힌트다.
    # -> ClientSession은 초기화가 끝난 MCP 세션을 반환한다는 뜻이다.
    """설정에 맞는 Transport를 열고 초기화된 MCP Session을 반환합니다."""
    transport = config["transport"]

    # 같은 MCP 규칙을 쓰더라도 메시지를 보내는 통로(Transport)는 설정에 따라 달라진다.
    if transport == "streamable-http":
        # HTTP Client가 서버와 통신할 읽기/쓰기 스트림을 만든다.
        # _는 이번 코드에서 사용하지 않는 세 번째 값을 일부러 버리는 관례다.
        read_stream, write_stream, _ = await stack.enter_async_context(
            streamable_http_client(config["url"])
        )
    elif transport == "stdio":
        # stdio는 포트/URL 대신 자식 프로세스의 stdin/stdout으로 메시지를 주고받는다.
        parameters = StdioServerParameters(
            command=config["command"],
            args=config.get("args", []),
            env=config.get("env"),
        )
        read_stream, write_stream = await stack.enter_async_context(
            stdio_client(parameters)
        )
    else:
        raise ValueError(f"지원하지 않는 MCP Transport입니다: {transport}")

    # Transport는 우편 통로이고, ClientSession은 그 통로 위에서 MCP 대화를 관리하는 객체다.
    session = await stack.enter_async_context(
        ClientSession(read_stream, write_stream)
    )
    # initialize()는 Server와 MCP 세션을 시작하는 초기 handshake다.
    await session.initialize()
    return session


@asynccontextmanager
async def mcp_sessions():
    # @asynccontextmanager는 이 함수를 다음처럼 쓸 수 있게 만든다.
    # async with mcp_sessions() as sessions:
    #     ... 작업 ...
    # 블록을 빠져나갈 때 내부 AsyncExitStack이 Session과 자식 프로세스를 정리한다.
    """등록된 모든 MCP Server를 열고 이름별 Session을 제공합니다."""
    async with AsyncExitStack() as stack:
        sessions: dict[str, ClientSession] = {}
        # items()는 {이름: 설정}을 (이름, 설정) 쌍으로 순회한다.
        for server_name, config in MCP_SERVERS.items():
            sessions[server_name] = await open_session(stack, config)
        yield sessions


def result_text(result) -> str:
    # MCP 결과는 여러 content 조각을 가질 수 있다.
    # hasattr()로 text 속성이 있는 조각만 골라 줄바꿈으로 합친다.
    return "\n".join(
        content.text for content in result.content if hasattr(content, "text")
    )


async def discover_tools() -> list[dict[str, Any]]:
    # list[...]는 "dict들의 list"라는 반환 타입 힌트다.
    # 이 함수의 목적은 Tool을 실행하는 것이 아니라 Server가 공개한 Tool 계약을 읽는 것이다.
    async with mcp_sessions() as sessions:
        tools: list[dict[str, Any]] = []
        for server_name, session in sessions.items():
            # list_tools()는 MCP의 tools/list에 해당한다.
            response = await session.list_tools()
            for tool in response.tools:
                # SDK 모델 객체를 일반 dict로 바꿔 API 응답/OpenAI 변환에 사용할 수 있게 한다.
                raw = tool.model_dump(by_alias=True)
                tools.append({
                    "server": server_name,
                    "name": tool.name,
                    "public_name": f"{server_name}__{tool.name}",
                    "description": tool.description,
                    "input_schema": raw.get("inputSchema", {}),
                })
        return tools


async def discover_resources() -> list[dict[str, Any]]:
    # Tool이 "작업"이라면 Resource는 URI로 식별되는 "읽을 대상"이다.
    async with mcp_sessions() as sessions:
        resources: list[dict[str, Any]] = []
        for server_name, session in sessions.items():
            response = await session.list_resources()
            resources.extend(
                {
                    "server": server_name,
                    "name": resource.name,
                    "uri": str(resource.uri),
                    "description": resource.description,
                }
                for resource in response.resources
            )
        return resources


async def read_resource(server_name: str, uri: str) -> str:
    # server_name으로 여러 Session 중 목적지를 고르고,
    # uri로 그 Server 안의 읽을 대상을 고른다.
    async with mcp_sessions() as sessions:
        response = await sessions[server_name].read_resource(uri)
        return "\n".join(
            content.text for content in response.contents if hasattr(content, "text")
        )
