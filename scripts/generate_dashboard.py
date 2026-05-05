#!/usr/bin/env python3
"""
知识库 Dashboard 数据生成脚本
- 扫描 wiki/ 下所有文章
- 自动生成/更新 frontmatter（rating、tags、description、date）
- 自动生成 dashboard-data.js 供前端使用
- 评分规则：基于文章内容质量的多维度加权计算

评分维度（满分10分）：
1. 内容长度（权重30%）：越长说明越详细
2. 结构化程度（权重25%）：标题层级、表格、代码块数量
3. 时效性（权重20%）：更新时间越近分越高
4. 标签丰富度（权重15%）：标签数量
5. 引用链接（权重10%）：内外部链接数量

用法: python3 scripts/generate_dashboard.py
"""
import os
import re
import json
import glob
from datetime import datetime, date
from pathlib import Path

KB = Path(__file__).parent.parent
WIKI = KB / "wiki"
OUTPUT = KB / "docs" / "overrides" / "dashboard-data.js"

# 分类对应的标签颜色和默认标签池
CATEGORY_TAGS = {
    "concepts": ["AI-Agent", "LLM", "Prompt", "Context", "Memory", "Caching", "RAG", "MCP", "Skill", "Agent"],
    "entities": ["GitHub", "开源项目", "工具", "框架", "终端", "翻译", "OS", "编辑器", "性能", "安全"],
    "sources": ["论文", "源码分析", "书单", "对比", "实践", "安全"],
    "syntheses": ["对比分析", "工具链", "技术栈", "方案", "总结"]
}

# 标题到标签的映射规则（启发式）
TITLE_TAG_RULES = {
    r"(?i)claude": ["Claude"],
    r"(?i)openclaw": ["OpenClaw", "Agent"],
    r"(?i)hermes": ["Hermes", "Agent"],
    r"(?i)perfetto": ["Perfetto", "性能分析"],
    r"(?i)context.?window": ["Context-Window", "优化"],
    r"(?i)memory": ["Memory", "记忆管理"],
    r"(?i)rag": ["RAG", "检索增强"],
    r"(?i)skill": ["Skill", "技能"],
    r"(?i)prompt.?cach": ["Prompt-Caching", "缓存"],
    r"(?i)deepep": ["DeepEP", "MoE"],
    r"(?i)self.?improv": ["Self-Improvement", "自我改进"],
    r"(?i)tool.?call": ["Tool-Calling", "函数调用"],
    r"(?i)ast": ["AST", "代码编辑"],
    r"(?i)weak.?model": ["弱模型编排", "成本优化"],
    r"(?i)knowledge.?graph": ["知识图谱", "KG"],
    r"(?i)pretext": ["Pretext", "富文本"],
    r"(?i)karpathy": ["Karpathy", "教育"],
    r"(?i)mattpocock": ["MattPocock", "TypeScript"],
    r"(?i)deepseek": ["DeepSeek", "模型"],
    r"(?i)gpt": ["GPT", "OpenAI"],
    r"(?i)ghostty": ["Ghostty", "终端"],
    r"(?i)warp": ["Warp", "终端"],
    r"(?i)zed": ["Zed", "编辑器"],
    r"(?i)harmonist": ["Harmonist", "鸿蒙"],
    r"(?i)deer.?flow": ["DeerFlow", "RAG"],
    r"(?i)operit": ["Operit", "Agent"],
    r"(?i)go.?click": ["GoClick", "自动化"],
    r"(?i)fewshell": ["Fewshell", "Agent"],
    r"(?i)kora": ["Kora", "OS", "AI-Native"],
    r"(?i)open.?design": ["OpenDesign", "设计"],
    r"(?i)trycua": ["Cua", "计算机使用"],
    r"(?i)open.?mobile": ["OpenMobile", "论文"],
    r"(?i)ml.?intern": ["ML-Intern", "机器学习"],
    r"(?i)hy.?mt": ["离线翻译", "NLP"],
    r"(?i)claude.?context": ["Claude", "Context"],
    r"(?i)claude.?mem": ["Claude", "Memory"],
    r"(?i)llm.?wiki": ["LLM", "Wiki"],
    r"(?i)coding.?agent": ["Coding-Agent", "代码生成"],
    r"(?i)pricing": ["定价", "成本"],
    r"(?i)书单|book": ["书单", "推荐"],
    r"(?i)安全|security|vuln": ["安全"],
}


def parse_frontmatter(content):
    """解析 YAML frontmatter"""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    fm_str = content[3:end].strip()
    body = content[end + 3:].strip()

    fm = {}
    for line in fm_str.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 处理列表 [a, b, c]
        if val.startswith("[") and val.endswith("]"):
            val = [x.strip().strip('"\'') for x in val[1:-1].split(",") if x.strip()]
        elif val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        elif val.isdigit():
            val = float(val) if "." in val else int(val)
        fm[key] = val

    return fm, body


def build_frontmatter(fm, updates):
    """重建 frontmatter 字符串"""
    merged = {**fm, **updates}
    lines = ["---"]
    for key, val in merged.items():
        if isinstance(val, list):
            val_str = "[" + ", ".join(f'"{v}"' for v in val) + "]"
            lines.append(f'{key}: {val_str}')
        elif isinstance(val, float):
            lines.append(f'{key}: {val}')
        elif isinstance(val, (int, bool)):
            lines.append(f'{key}: {val}')
        else:
            lines.append(f'{key}: "{val}"')
    lines.append("---")
    return "\n".join(lines)


def extract_tags(title, body, category):
    """从标题和内容中提取标签"""
    tags = set()

    # 标题规则匹配
    for pattern, tag_list in TITLE_TAG_RULES.items():
        if re.search(pattern, title):
            tags.update(tag_list)

    # 内容中高频关键词提取
    body_lower = body.lower()
    category_keywords = CATEGORY_TAGS.get(category, [])
    for kw in category_keywords:
        kw_lower = kw.lower()
        if kw_lower in body_lower and kw not in tags:
            # 标签要出现至少2次才加入（避免误匹配）
            count = body_lower.count(kw_lower)
            if count >= 2 or len(kw) >= 5:  # 短标签需要更高频次
                tags.add(kw)

    # 确保标签数量在2-5之间
    if len(tags) < 2:
        # 补充分类默认标签
        for default in category_keywords[:3]:
            if default not in tags:
                tags.add(default)
                if len(tags) >= 3:
                    break

    return sorted(list(tags))[:6]


def extract_description(title, body):
    """从内容中提取一句话描述"""
    # 优先取引用块（> 开头的第一行）
    quote_match = re.search(r'^>\s*(.+)$', body, re.MULTILINE)
    if quote_match:
        desc = quote_match.group(1).strip()
        if 10 <= len(desc) <= 100:
            return desc

    # 取第一个非空段落
    paragraphs = re.split(r'\n\s*\n', body)
    for p in paragraphs:
        p = p.strip()
        # 跳过标题、表格、代码块
        if p.startswith('#') or p.startswith('|') or p.startswith('```'):
            continue
        # 去掉列表标记
        p = re.sub(r'^[-*]\s+', '', p, flags=re.MULTILINE).strip()
        if 10 <= len(p) <= 120:
            # 截断到第一个句号
            for sep in ['。', '.', '，', ',']:
                if sep in p:
                    idx = p.index(sep)
                    if idx >= 10:
                        return p[:idx + 1]
            return p

    # fallback: 用标题
    return title


def calculate_rating(body, file_mtime, tags, category):
    """多维度评分计算"""
    scores = {}

    # 1. 内容长度（权重30%，满分3分）
    word_count = len(body)
    if word_count >= 5000:
        scores["length"] = 3.0
    elif word_count >= 3000:
        scores["length"] = 2.5
    elif word_count >= 1500:
        scores["length"] = 2.0
    elif word_count >= 800:
        scores["length"] = 1.5
    elif word_count >= 300:
        scores["length"] = 1.0
    else:
        scores["length"] = 0.5

    # 2. 结构化程度（权重25%，满分2.5分）
    headings = len(re.findall(r'^#{2,4}\s+', body, re.MULTILINE))
    tables = len(re.findall(r'^\|.+\|$', body, re.MULTILINE))
    code_blocks = len(re.findall(r'```', body)) // 2
    lists = len(re.findall(r'^\s*[-*]\s+', body, re.MULTILINE))

    structure_score = min(
        headings * 0.3 + tables * 0.5 + code_blocks * 0.3 + lists * 0.05,
        2.5
    )
    scores["structure"] = round(structure_score, 1)

    # 3. 时效性（权重20%，满分2分）
    days_old = (date.today() - file_mtime.date()).days
    if days_old <= 7:
        scores["recency"] = 2.0
    elif days_old <= 14:
        scores["recency"] = 1.8
    elif days_old <= 30:
        scores["recency"] = 1.5
    elif days_old <= 60:
        scores["recency"] = 1.0
    else:
        scores["recency"] = 0.5

    # 4. 标签丰富度（权重15%，满分1.5分）
    tag_count = len(tags)
    if tag_count >= 5:
        scores["tags"] = 1.5
    elif tag_count >= 3:
        scores["tags"] = 1.2
    elif tag_count >= 2:
        scores["tags"] = 0.9
    else:
        scores["tags"] = 0.5

    # 5. 引用链接（权重10%，满分1分）
    links = len(re.findall(r'\[([^\]]+)\]\([^)]+\)', body))
    if links >= 10:
        scores["links"] = 1.0
    elif links >= 5:
        scores["links"] = 0.8
    elif links >= 2:
        scores["links"] = 0.5
    else:
        scores["links"] = 0.3

    total = sum(scores.values())
    # 四舍五入到0.5的倍数
    total = round(total * 2) / 2
    total = min(total, 9.8)  # 最高不超过9.8
    total = max(total, 5.0)  # 最低不低于5.0

    return total, scores


def process_file(filepath, category):
    """处理单个文件，返回 (url, article_data, updated_content_or_None)"""
    rel_path = filepath.relative_to(KB)
    url = str(rel_path.with_suffix(''))

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    fm, body = parse_frontmatter(content)
    file_mtime = datetime.fromtimestamp(filepath.stat().st_mtime)

    # 提取/更新字段
    title = fm.get("title", filepath.stem.replace("-", " "))
    # 标题保留原始 frontmatter 中的（可能有中文）
    existing_tags = fm.get("tags", [])
    existing_rating = fm.get("rating")
    existing_desc = fm.get("description")

    # 确保rating是float类型
    try:
        existing_rating = float(existing_rating) if existing_rating else None
    except (ValueError, TypeError):
        existing_rating = None
    # 确保tags是list类型
    if isinstance(existing_tags, str):
        existing_tags = [t.strip() for t in existing_tags.strip("[]").split(",") if t.strip()]

    # 如果已有完整的 frontmatter，保留人工修改的值
    if existing_rating and existing_desc and existing_tags:
        # 但评分可以重新计算（文章更新后可能变化）
        new_rating, _ = calculate_rating(body, file_mtime, existing_tags, category)
        # 如果差异大于0.5才更新
        if abs(new_rating - existing_rating) < 0.5:
            article = {
                "title": title,
                "category": category,
                "tags": existing_tags,
                "rating": existing_rating,
                "description": existing_desc,
                "date": fm.get("date", file_mtime.strftime("%Y-%m-%d")),
                "url": url
            }
            return url, article, None
        else:
            fm["rating"] = new_rating
            updated = build_frontmatter(fm, {})
            new_content = updated + "\n\n" + body
            article = {
                "title": title,
                "category": category,
                "tags": existing_tags,
                "rating": new_rating,
                "description": existing_desc,
                "date": fm.get("date", file_mtime.strftime("%Y-%m-%d")),
                "url": url
            }
            return url, article, new_content

    # 自动生成
    tags = extract_tags(title, body, category)
    description = extract_description(title, body)
    rating, _ = calculate_rating(body, file_mtime, tags, category)
    file_date = file_mtime.strftime("%Y-%m-%d")

    # 更新 frontmatter
    updates = {
        "title": title,
        "category": category,
        "tags": tags,
        "rating": rating,
        "description": description,
        "date": file_date,
    }

    # 如果已有部分字段，保留
    for k in list(updates.keys()):
        if k in fm and fm[k]:
            # 保留原始值，除非是我们想自动更新的
            if k == "rating":
                continue  # 评分总是重新计算
            del updates[k]

    new_fm = build_frontmatter(fm, updates)
    new_content = new_fm + "\n\n" + body

    article = {
        "title": updates.get("title", fm.get("title", title)),
        "category": category,
        "tags": updates.get("tags", fm.get("tags", tags)),
        "rating": updates.get("rating", fm.get("rating", rating)),
        "description": updates.get("description", fm.get("description", description)),
        "date": updates.get("date", fm.get("date", file_date)),
        "url": url
    }

    return url, article, new_content


def main():
    articles = []
    updated_files = 0

    # 扫描 wiki/ 目录
    categories = ["concepts", "entities", "sources", "syntheses"]
    for category in categories:
        cat_dir = WIKI / category
        if not cat_dir.exists():
            continue

        for md_file in sorted(cat_dir.glob("*.md")):
            if md_file.name == "index.md":
                continue

            try:
                url, article, new_content = process_file(md_file, category)
                articles.append(article)

                if new_content is not None:
                    with open(md_file, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    updated_files += 1
            except Exception as e:
                print(f"⚠️ 处理失败: {md_file.name}: {e}")

    # 按评分降序排序
    articles.sort(key=lambda x: x.get("rating", 0), reverse=True)

    # 生成 dashboard-data.js
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    js_content = "// Auto-generated dashboard data\n"
    js_content += f"// Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    js_content += f"// Total articles: {len(articles)}\n"
    js_content += f"// Updated files this run: {updated_files}\n"
    js_content += "window.__kb_articles = " + json.dumps(articles, ensure_ascii=False, indent=2) + ";\n"

    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write(js_content)

    print(f"✅ 生成完成: {len(articles)} 篇文章, {updated_files} 篇更新了frontmatter")
    print(f"📊 评分分布:")
    rating_dist = {}
    for a in articles:
        r = a["rating"]
        bucket = int(r)
        rating_dist[bucket] = rating_dist.get(bucket, 0) + 1
    for bucket in sorted(rating_dist.keys(), reverse=True):
        bar = "█" * rating_dist[bucket]
        print(f"   {bucket}.0-{bucket}.9: {bar} ({rating_dist[bucket]})")


if __name__ == "__main__":
    main()
