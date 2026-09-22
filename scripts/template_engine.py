"""
极简模板引擎（零依赖）

语法：
  {{TOKEN}}                              变量替换，缺失时渲染为空字符串
  <!--BEGIN:list--> … <!--END:list-->    循环，支持任意层级嵌套

渲染策略：由外向内展开。展开某个循环时，把父级上下文与该行数据合并后
递归渲染循环体，因此内层循环可以直接访问外层循环项的字段。
"""

import re

_BEGIN = re.compile(r"<!--BEGIN:(\w+)-->")
_END = re.compile(r"<!--END:(\w+)-->")
_TOKEN = re.compile(r"\{\{(\w+)\}\}")


def _locate(text):
    """找到文本中第一对外层 BEGIN/END（用深度计数匹配同名标记）。"""
    for begin in _BEGIN.finditer(text):
        seg = text[begin.end():]
        idx = 0
        depth = 0
        matched = None
        while True:
            nb = _BEGIN.search(seg, idx)
            ne = _END.search(seg, idx)
            if ne is None:
                break
            if nb and nb.start() < ne.start():
                depth += 1
                idx = nb.end()
                continue
            if depth == 0:
                matched = ne
                break
            depth -= 1
            idx = ne.end()
        if matched is None:
            continue
        return begin.group(1), begin.start(), begin.end(), begin.end() + matched.start(), begin.end() + matched.end()
    return None


def _substitute(text, ctx):
    def _rep(match):
        value = ctx.get(match.group(1), "")
        return "" if value is None else str(value)

    return _TOKEN.sub(_rep, text)


def render(template_text, ctx):
    """把模板渲染成字符串。ctx 中形如 {"list": [{...}, {...}]} 的键驱动对应循环。"""
    text = template_text
    guard = 0
    while True:
        loc = _locate(text)
        if loc is None:
            return _substitute(text, ctx)
        guard += 1
        if guard > 2000:
            raise RuntimeError("模板循环展开次数异常，请检查 BEGIN/END 是否配对")
        name, b0, b1, e0, e1 = loc
        body = text[b1:e0]
        rows = ctx.get(name) or []
        chunks = []
        for row in rows:
            merged = dict(ctx)
            merged.update(row)
            chunks.append(render(body, merged))
        text = text[:b0] + "".join(chunks) + text[e1:]
