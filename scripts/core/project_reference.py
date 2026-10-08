"""Read-only comparison-first presentation; media stays inside the project."""
import html
import json
import math
from pathlib import Path
from urllib.parse import quote, urlsplit


def _video(folder, value):
    relative = Path(value)
    video = (folder / relative).resolve()
    if (relative.is_absolute() or not video.is_relative_to(folder) or
            not video.is_file() or video.suffix.lower() not in ('.mp4', '.webm')):
        raise ValueError('Video must be an existing project-local MP4/WebM')
    return html.escape(quote(video.relative_to(folder).as_posix(), safe='/'), quote=True)


def _duration(value):
    try:
        number = float(value)
        return f'{number:.1f} 秒' if math.isfinite(number) and number > 0 else ''
    except (ValueError, TypeError):
        return ''


def _presentation(folder):
    file = folder / 'presentation.json'
    if not file.exists():
        return {}, '复刻成片待完成'
    try:
        meta = json.loads(file.read_text(encoding='utf-8-sig'))
        if not isinstance(meta, dict) or meta.get('schema_version') != 1:
            raise ValueError('Invalid presentation metadata')
        return meta, _video(folder, meta['result_video'])
    except (OSError, ValueError, KeyError, TypeError):
        return {}, '复刻成片暂不可用'


def render(folder):
    folder = Path(folder).resolve()
    metadata = folder / 'source_reference.json'
    if not metadata.exists():
        return ''
    unavailable = '<section id="source-reference"><h2>参考原片不可用</h2><p>请核对项目内参考视频和来源配置。</p></section>'
    try:
        meta = json.loads(metadata.read_text(encoding='utf-8-sig'))
        src = _video(folder, meta['video'])
        esc = lambda value: html.escape(str(value), quote=True)
        links = []
        for field, label in [('origin_url', '原帖链接'), ('lark_url', 'Lark 来源记录')]:
            url = meta.get(field, '')
            parsed = urlsplit(url)
            if parsed.scheme.lower() in ('http', 'https') and parsed.netloc:
                links.append(f'<a href="{esc(url)}" target="_blank" rel="noopener noreferrer">{label}</a>')
        ranges = ''.join(f'<li>{esc(item["name"])}：{esc(item["start"])}–{esc(item["end"])} 秒</li>'
                         for item in meta.get('segments', []))
        presentation, result = _presentation(folder)
        available = bool(presentation)
        result_player = (f'<video id="comparison-result-player" class="comparison-player" controls '
                         f'preload="metadata" src="{result}" aria-label="复刻成片"></video>'
                         if available else f'<div class="comparison-empty" role="status">{result}</div>')
        result_link = f'<a href="{result}" download>下载新片</a>' if available else ''
        def copy_items(field):
            rows = presentation.get(field, [])
            if not isinstance(rows, list):
                return ''
            return ''.join(f'<h4>{esc(item.get("title", "口播"))}</h4><p>{esc(item.get("text", ""))}</p>'
                           for item in rows if isinstance(item, dict))
        source_copy, result_copy = copy_items('source_voiceover'), copy_items('voiceover')
        scripts = ''
        if source_copy or result_copy:
            language = esc(presentation.get('audio_language', '原语言'))
            scripts = ('<section class="voiceover"><h2>口播对照 · 中文翻译</h2>'
                       f'<p class="muted">{language}配音；中文仅用于审阅，不替换视频配音。</p>'
                       '<div class="voiceover-grid"><div class="voiceover-card"><h3>原片口播 · 中文翻译</h3>'
                       f'<p class="muted">{esc(presentation.get("source_transcript_note", ""))}</p>'
                       f'{source_copy or "<p>原片译文待整理</p>"}</div>'
                       '<div class="voiceover-card"><h3>新版口播 · 中文翻译</h3>'
                       f'{result_copy or "<p>新版译文待整理</p>"}</div></div></section>')
        return ('<section id="source-reference" class="comparison" aria-label="原片与复刻对比">'
                '<div class="comparison-grid"><div class="comparison-card">'
                f'<h3>参考原片 <span>{esc(_duration(meta.get("duration_seconds")))}</span></h3>'
                f'<video id="source-reference-player" class="comparison-player" controls preload="metadata" '
                f'src="{src}" aria-label="参考原片"></video>'
                f'<p><a href="{src}">单独打开原片</a></p></div><div class="comparison-card">'
                f'<h3>{esc(presentation.get("result_label", "复刻成片"))} '
                f'<span>{esc(_duration(presentation.get("duration_seconds")))}</span></h3>'
                f'{result_player}<p><small>AI生成 · 待你确认</small> {result_link}</p></div></div>'
                '<details id="source-details"><summary>来源与对照说明</summary>'
                f'<p>{esc(meta.get("title", "本地参考视频"))}</p><p>{" · ".join(links)}</p><p>来源记录：{esc(meta.get("record_id", ""))}<br>'
                f'分析版本：{esc(meta.get("analysis_version", ""))}</p><p>生成段对应原片区间：</p><ul>{ranges}</ul>'
                f'<p>{esc(meta.get("note", "仅作研究参考；不代表原素材再发布授权。"))}</p>'
                f'<details><summary>原片 SHA256</summary><code>{esc(meta.get("sha256", ""))}</code></details>'
                f'</details></section>{scripts}')
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return unavailable


STYLE = '''<style>
.replica-review{max-width:1100px;padding:22px 28px}.replica-review>h1{font-size:26px;margin:8px 0 18px}
.replica-review>p:first-child{margin:0;font-size:13px}.comparison h2{margin:0 0 12px;font-size:20px}
.comparison-grid,.voiceover-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:22px}
.comparison-card{min-width:0}.comparison-card h3{display:flex;justify-content:space-between;align-items:center;font-size:16px;margin:8px 0 10px}
.comparison-card h3 span{font-size:13px;font-weight:normal;color:#a9bdc7}.comparison-card p{margin:8px 0;font-size:13px}
.comparison-player,.comparison-empty{width:100%;height:min(58vh,540px);min-height:300px;max-height:540px;object-fit:contain;background:#050a0e;border:1px solid #29434f;border-radius:12px;box-sizing:border-box}
.comparison-empty{display:grid;place-items:center;color:#9aadb8}
#source-details{margin:10px 0 0;color:#a9bdc7;font-size:13px}summary{cursor:pointer}#source-details>p{overflow-wrap:anywhere}
.voiceover{margin:22px 0}.voiceover h2{font-size:18px}.voiceover-card{background:#152630;border:1px solid #29434f;border-radius:12px;padding:14px 18px}
.voiceover-card h3{font-size:15px;margin:0 0 8px}.voiceover-card h4{font-size:13px;color:#a9bdc7;margin:14px 0 5px}.voiceover-card p{margin:0;font-size:14px;color:#c8d7df}
#production-details{margin:26px 0;border-top:1px solid #29434f;padding-top:14px}#production-details>summary{font-size:14px;color:#9aadb8}
@media(max-width:640px){.replica-review{padding:16px}.replica-review>h1{font-size:22px}.comparison-grid,.voiceover-grid{grid-template-columns:1fr}.comparison-player,.comparison-empty{height:60vh;min-height:280px}.comparison-controls{gap:6px}}
</style>'''


def present(folder, page):
    """Keep legacy tracker and scripts intact inside a closed technical drawer."""
    comparison = render(folder)
    if not comparison:
        return page
    prefix, marker, rest = page.partition('<main>')
    content, closing, tail = rest.partition('</main>')
    heading, separator, production = content.partition('</h1>')
    if not marker or not closing or not separator:
        return page
    return (prefix + STYLE + '<main class="replica-review">' + heading + separator + comparison +
            '<details id="production-details"><summary>制作详情 · 分段原件与技术记录</summary>' +
            production + '</details></main>' + tail)
