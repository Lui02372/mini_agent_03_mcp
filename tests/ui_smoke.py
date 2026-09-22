"""Run against an existing Streamlit server: python tests/ui_smoke.py [URL]."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:18501'
out = Path('.local-test')
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1440, 'height': 1100})
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url, wait_until='networkidle')
    expect(page.get_by_role('heading', name='Travel Agent Studio')).to_be_visible()
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    page.get_by_role('button', name='전체 모델을 mock으로 전환').click()
    expect(page.locator('[data-testid="stSidebar"]').get_by_text('deterministic-demo', exact=True)).to_have_count(4, timeout=15000)
    page.get_by_text('모의 데이터: 외부 DB 없이 실행', exact=True).click()
    page.get_by_role('button', name='멀티에이전트 실행', exact=True).click()
    expect(page.get_by_text('4개 역할 중 4개 처리', exact=True)).to_be_visible(timeout=45000)
    expect(page.get_by_text('추가 확인 필요: 모의 데이터·모의 응답·예산 초과·실패 항목을 확인하세요.', exact=True)).to_be_visible()
    for name in ['Weather agent', 'Place agent', 'Budget agent', 'Validation agent']:
        expect(page.get_by_role('heading', name=name, exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='실행 결과 JSON 다운로드')).to_be_visible()
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    import json
    with page.expect_download() as download_info:
        page.get_by_role('button', name='실행 결과 JSON 다운로드').click()
    run = json.loads(Path(download_info.value.path()).read_text(encoding='utf-8'))
    assert all(a['provider_requested'] == 'mock' for a in run['agents'].values()), run['request']['providers']
    assert all(a['provider_used'] == 'mock' for a in run['agents'].values())
    assert 'DeltaGenerator' not in page.locator('body').inner_text()
    page.get_by_role('heading', name='Weather agent', exact=True).scroll_into_view_if_needed()
    page.screenshot(path=str(out / 'multi-agent-desktop.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.screenshot(path=str(out / 'multi-agent-mobile.png'), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    assert not errors, errors
    browser.close()
print('PASS browser: four agents, mock fallback labels, result download, mobile width, no page errors')
