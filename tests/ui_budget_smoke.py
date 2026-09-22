import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
with sync_playwright() as p:
    b=p.chromium.launch()
    page=b.new_page(viewport={'width':1440,'height':1100})
    page.goto('http://127.0.0.1:18501',wait_until='networkidle')
    page.get_by_role('button',name='전체 모델을 Gemma로 설정').click()
    expect(page.locator('[data-testid="stSidebar"]').get_by_text('gemma3:1b',exact=True)).to_have_count(4)
    page.get_by_role('button',name='전체 모델을 mock으로 전환').click()
    expect(page.locator('[data-testid="stSidebar"]').get_by_text('deterministic-demo',exact=True)).to_have_count(4)
    page.get_by_role('spinbutton',name='함께 숙박하는 인원',exact=True).fill('2')
    page.get_by_role('spinbutton',name='함께 숙박하는 인원',exact=True).press('Tab')
    page.get_by_role('spinbutton',name='객실당 1박 계획 금액 (원)',exact=True).fill('120000')
    page.get_by_role('spinbutton',name='객실당 1박 계획 금액 (원)',exact=True).press('Tab')
    page.get_by_role('combobox',name='저녁 식사 유형',exact=True).click()
    page.get_by_role('option',name='해산물/생선 요리',exact=True).click()
    page.get_by_role('spinbutton',name='저녁 1인 1회 금액 (원)',exact=True).fill('20000')
    page.get_by_role('spinbutton',name='저녁 1인 1회 금액 (원)',exact=True).press('Tab')
    expect(page.get_by_text('1인 식비·카페: 하루 40,000원 × 2일. 매일 각 항목 1회 기준이며 첫날·마지막날도 동일하게 계산합니다.',exact=True)).to_be_visible()
    page.get_by_text('모의 데이터: 외부 DB 없이 실행',exact=True).click()
    page.get_by_role('button',name='멀티에이전트 실행',exact=True).click()
    expect(page.get_by_text('4개 역할 중 4개 처리',exact=True)).to_be_visible(timeout=45000)
    with page.expect_download() as item:
        page.get_by_role('button',name='실행 결과 JSON 다운로드').click()
    run=json.loads(Path(item.value.path()).read_text(encoding='utf-8'))
    assert all(a['provider_used']=='mock' for a in run['agents'].values()), run['request']['providers']
    assert run['budget']['items']['숙박']==60000
    assert run['budget']['items']['식비·카페']==80000
    assert run['budget']['total']==178000
    assert run['request']['meal_plan'][2]['style']=='해산물/생선 요리'
    page.get_by_role('heading',name='1인 예산 상세 계획').scroll_into_view_if_needed()
    page.screenshot(path='.local-test/detailed-budget.png')
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
    expect(page.locator('[data-testid="stException"]')).to_have_count(0)
    b.close()
print('PASS detailed budget: room sharing, meal styles, live totals, Gemma selection, mobile width')
