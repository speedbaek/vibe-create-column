"""참고 글과 발행 글의 구조를 비교 분석"""
import os
import sys
import asyncio
import json

sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv(override=True)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 참고 글 (실제 윤웅채 변리사 글)
REF_URL = "https://blog.naver.com/PostView.naver?blogId=jninsa&logNo=222500419365"
# 방금 발행한 글
MY_URL = "https://blog.naver.com/PostView.naver?blogId=jninsa&logNo=224214058036"


async def analyze_post(page, url, label):
    """글 구조 분석"""
    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await asyncio.sleep(5)

    info = await page.evaluate("""() => {
        var doc = document;
        var mainFrame = doc.querySelector('#mainFrame');
        if (mainFrame && mainFrame.contentDocument) doc = mainFrame.contentDocument;

        var container = doc.querySelector('.se-main-container') || doc.querySelector('.post-view') || doc.querySelector('#postViewArea');
        if (!container) return {error: 'container not found'};

        // 컴포넌트 분석
        var components = container.querySelectorAll('[class*="se-component"]');
        var compTypes = [];
        components.forEach(function(c) {
            var classes = c.className;
            var type = 'unknown';
            if (classes.indexOf('se-text') >= 0) type = 'text';
            else if (classes.indexOf('se-image') >= 0) type = 'image';
            else if (classes.indexOf('se-oglink') >= 0) type = 'oglink';
            else if (classes.indexOf('se-sticker') >= 0) type = 'sticker';
            else if (classes.indexOf('se-horizontalLine') >= 0) type = 'hr';
            else if (classes.indexOf('se-quotation') >= 0) type = 'quote';
            compTypes.push(type);
        });

        // 텍스트 컴포넌트 상세 분석
        var textComps = container.querySelectorAll('.se-text');
        var textDetails = [];
        textComps.forEach(function(tc) {
            var paras = tc.querySelectorAll('.se-text-paragraph');
            var paraTexts = [];
            paras.forEach(function(p) {
                var text = p.innerText.trim();
                if (text) {
                    var hasBold = p.querySelector('b, strong, [style*="font-weight"]') !== null;
                    var fontSize = '';
                    var span = p.querySelector('span');
                    if (span) {
                        var computed = window.getComputedStyle(span);
                        fontSize = computed.fontSize;
                    }
                    paraTexts.push({
                        text: text.substring(0, 80),
                        len: text.length,
                        bold: hasBold,
                        fontSize: fontSize,
                    });
                }
            });
            // 빈 문단 수 (간격 역할)
            var emptyParas = 0;
            paras.forEach(function(p) {
                if (!p.innerText.trim()) emptyParas++;
            });
            textDetails.push({
                totalParas: paras.length,
                emptyParas: emptyParas,
                contentParas: paraTexts,
            });
        });

        // 이미지 분석
        var images = container.querySelectorAll('.se-image');
        var imgDetails = [];
        images.forEach(function(img) {
            var imgEl = img.querySelector('img');
            var width = imgEl ? imgEl.width : 0;
            var height = imgEl ? imgEl.height : 0;
            var classes = img.className;
            var layout = 'default';
            if (classes.indexOf('se-l-align_left') >= 0) layout = 'align_left';
            else if (classes.indexOf('se-l-align_center') >= 0) layout = 'align_center';
            imgDetails.push({width: width, height: height, layout: layout});
        });

        // oglink 분석
        var oglinks = container.querySelectorAll('.se-oglink');
        var ogDetails = [];
        oglinks.forEach(function(og) {
            var title = og.querySelector('.se-oglink-title');
            var desc = og.querySelector('.se-oglink-summary');
            var url = og.querySelector('.se-oglink-url');
            ogDetails.push({
                title: title ? title.innerText.substring(0, 60) : '',
                desc: desc ? desc.innerText.substring(0, 60) : '',
                url: url ? url.innerText : '',
            });
        });

        // 전체 텍스트 길이
        var fullText = container.innerText;

        return {
            componentOrder: compTypes,
            componentCount: compTypes.length,
            textDetails: textDetails,
            imageDetails: imgDetails,
            oglinkDetails: ogDetails,
            totalTextLen: fullText.length,
        };
    }""")

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")

    if info.get('error'):
        print(f"  ERROR: {info['error']}")
        return

    print(f"\n[컴포넌트 순서] (총 {info['componentCount']}개)")
    order = info['componentOrder']
    for i, t in enumerate(order):
        print(f"  {i+1}. {t}")

    print(f"\n[텍스트 컴포넌트 상세] (총 {len(info['textDetails'])}개)")
    for i, td in enumerate(info['textDetails']):
        empty = td['emptyParas']
        content = td['contentParas']
        print(f"  Text#{i+1}: {td['totalParas']}개 문단 (빈줄 {empty}개)")
        for j, cp in enumerate(content[:5]):
            bold_mark = "[B]" if cp['bold'] else "   "
            print(f"    {bold_mark} [{cp['fontSize']}] {cp['text']}")
        if len(content) > 5:
            print(f"    ... +{len(content)-5}개 문단")

    print(f"\n[이미지] (총 {len(info['imageDetails'])}개)")
    for i, img in enumerate(info['imageDetails']):
        print(f"  Image#{i+1}: {img['width']}x{img['height']} layout={img['layout']}")

    print(f"\n[OG Link] (총 {len(info['oglinkDetails'])}개)")
    for i, og in enumerate(info['oglinkDetails']):
        print(f"  OGLink#{i+1}: {og['title']} | {og['url']}")

    print(f"\n[전체 텍스트 길이] {info['totalTextLen']}자")

    # 스크린샷
    ss_path = os.path.join(PROJECT_ROOT, "outputs", f"analyze_{label.replace(' ', '_')}.png")
    await page.screenshot(path=ss_path, full_page=True)
    print(f"  스크린샷: {ss_path}")


async def main():
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = context.pages[0] if context.pages else await context.new_page()

    await analyze_post(page, REF_URL, "참고글 (윤웅채 원본)")
    await analyze_post(page, MY_URL, "내 발행글")

    await browser.close()
    await pw.stop()


if __name__ == "__main__":
    asyncio.run(main())
