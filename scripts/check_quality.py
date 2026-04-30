#!/usr/bin/env python3
"""知识库 Wiki 页面质量校验脚本

用法:
    python scripts/check_quality.py                      # 检查所有 wiki 页面
    python scripts/check_quality.py wiki/entities/X.md    # 检查单个文件
    python scripts/check_quality.py --fix                 # 自动标记待改进页面
"""

import argparse
import os
import re
import sys

# ============================================================
# 配置
# ============================================================

# 知识库根目录（脚本所在目录的上级）
KNOWLEDGE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIKI_DIR = os.path.join(KNOWLEDGE_ROOT, "wiki")

# 最低字数要求（排除 frontmatter 和自评表）
MIN_WORD_COUNT = 300

# 最低自评加权总分
MIN_SCORE = 7.0

# 最低技术关键词数量
MIN_TECH_KEYWORDS = 3

# 最低标签数量（frontmatter tags）
MIN_TAGS = 2

# 空洞词列表（中英文）
HOLLOW_WORDS = [
    # 中文
    "赋能", "颠覆", "革命性", "划时代", "一站式", "全方位",
    "极致", "业界领先", "前所未有", "降维打击", "生态闭环",
    "底层逻辑", "认知升级", "价值重构",
    # 英文
    "groundbreaking", "game-changer", "revolutionary", "paradigm shift",
    "cutting-edge", "world-class", "state-of-the-art", "next-generation",
    "disruptive", "leverage", "synergy", "holistic", "seamless",
]

# 技术关键词模式（匹配常见技术术语）
TECH_PATTERNS = [
    r'\bAPI\b', r'\bSDK\b', r'\bREST\b', r'\bGraphQL\b',
    r'\bJSON\b', r'\bXML\b', r'\bYAML\b',
    r'\bPython\b', r'\bJava\b', r'\bKotlin\b', r'\bRust\b', r'\bGo\b', r'\bTypeScript\b', r'\bJavaScript\b', r'\bSwift\b',
    r'\bReact\b', r'\bVue\b', r'\bAngular\b',
    r'\bDocker\b', r'\bKubernetes\b', r'\bK8s\b',
    r'\bRedis\b', r'\bPostgreSQL\b', r'\bMySQL\b', r'\bMongoDB\b', r'\bSQLite\b',
    r'\bTensorFlow\b', r'\bPyTorch\b',
    r'\bLangChain\b', r'\bLangGraph\b', r'\bLlamaIndex\b',
    r'\bGPT\b', r'\bClaude\b', r'\bGemini\b', r'\bGLM\b', r'\bDeepSeek\b',
    r'\bRAG\b', r'\bMCP\b', r'\bBM25\b', r'\bTransformer\b', r'\bAttention\b',
    r'\bAgent\b', r'\bLLM\b', r'\bPrompt\b', r'\bEmbedding\b',
    r'\bOAuth\b', r'\bJWT\b', r'\bWebSocket\b', r'\bHTTP\b', r'\bHTTPS\b',
    r'\bGit\b', r'\bCI/CD\b',
    r'\bMVC\b', r'\bMVVM\b', r'\bSOLID\b', r'\bAOP\b',
    r'\bNLP\b', r'\bCV\b', r'\bRL\b', r'\bRLHF\b', r'\bDPO\b', r'\bSFT\b',
    r'\bGPU\b', r'\bCPU\b', r'\bTPU\b',
    r'\bHarmonyOS\b', r'\bArkTS\b', r'\bArkUI\b',
    r'\bChromaDB\b', r'\bFaiss\b', r'\bPinecone\b', r'\bWeaviate\b',
    r'\bFastAPI\b', r'\bFlask\b', r'\bDjango\b', r'\bExpress\b',
    r'\bNode\.?js\b', r'\bnpm\b', r'\bpip\b',
    r'\bVector[\s-]?Store?\b', r'\bRetrieval\b', r'\bChunking\b',
    r'\bContext[\s-]?Window\b', r'\bToken(?:izer|ization)?\b',
    r'\bFine[\s-]?tun(?:e|ing)\b', r'\bLoRA\b', r'\bQLoRA\b',
    r'\bFunction[\s-]?Call(?:ing)?\b', r'\bTool[\s-]?Use\b',
    r'\bMulti[\s-]?Agent\b', r'\bChain[\s-]?of[\s-]?Thought\b',
    r'\bReAct\b', r'\bPlan[\s-]?and[\s-]?Execute\b',
    r'\bMistral\b', r'\bLlama\b', r'\bQwen\b', r'\bYi\b',
    r'\bOpenAI\b', r'\bAnthropic\b', r'\bGoogle\b', r'\bMeta\b',
    r'\bHugging[\s-]?Face\b',
    # 常见算法/协议
    r'\bOAuth2?\b', r'\bRBAC\b', r'\bABAC\b',
    r'\bK[- ]?Means\b', r'\bKNN\b', r'\bSVM\b', r'\bCNN\b', r'\bRNN\b', r'\bLSTM\b',
    r'\bGRPC\b', r'\bgRPC\b', r'\bTCP\b', r'\bUDP\b', r'\bgRPC\b',
    r'\bS3\b', r'\bCDN\b', r'\bDNS\b', r'\bSSH\b', r'\bTLS\b', r'\bSSL\b',
    r'\bMarkdown\b', r'\bLaTeX\b',
    r'\bTrie\b', r'\bHashMap\b', r'\bHashSet\b', r'\bB[-+]?Tree\b',
    r'\bGraphQL\b', r'\bWebhook\b', r'\bCron\b',
]

# 编译正则
TECH_REGEX = re.compile('|'.join(TECH_PATTERNS), re.IGNORECASE)


# ============================================================
# 解析函数
# ============================================================

def parse_frontmatter(content: str) -> tuple[str, str]:
    """分离 frontmatter 和正文。返回 (frontmatter_text, body_text)。"""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[3:end].strip(), content[end + 3:].strip()
    return "", content


def extract_self_evaluation(body: str) -> tuple[str, float]:
    """从正文中提取自评表并返回加权总分。返回 (自评段落, 分数)。"""
    # 查找 ## 自评 段落
    match = re.search(r'##\s*自评\s*\n(.*?)(?=\n##|\Z)', body, re.DOTALL)
    if not match:
        return "", 0.0

    eval_block = match.group(1)

    # 查找加权总分：格式如 **加权总分** | | | **7.65**
    score_match = re.search(
        r'\*\*加权总分\*\*\s*\|?\s*\|?\s*\|?\s*\*\*(\d+\.?\d*)\*\*',
        eval_block
    )
    if score_match:
        return eval_block, float(score_match.group(1))

    # 备用格式：加权总分后面直接跟数字
    score_match2 = re.search(r'加权总分.*?(\d+\.?\d*)', eval_block)
    if score_match2:
        return eval_block, float(score_match2.group(1))

    return eval_block, 0.0


def extract_tags(frontmatter: str) -> list[str]:
    """从 frontmatter 中提取标签。"""
    tags = []
    # 匹配 tags: #tag1 #tag2 或 tags: [tag1, tag2]
    match = re.search(r'tags\s*:\s*(.+)', frontmatter, re.IGNORECASE)
    if match:
        tag_line = match.group(1)
        # #tag 格式
        tags.extend(re.findall(r'#(\S+)', tag_line))
        # [tag1, tag2] 格式
        tags.extend(re.findall(r'[\[",\s](\S+?)[\]",\s]', tag_line))
    return tags


def remove_self_eval_from_body(body: str) -> str:
    """从正文中移除自评表，用于字数统计。"""
    return re.sub(r'##\s*自评\s*\n.*', '', body, flags=re.DOTALL).strip()


def count_chinese_words(text: str) -> int:
    """统计字数：中文字符 + 英文单词数。"""
    chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
    # 移除中文后统计英文单词
    english_text = re.sub(r'[\u4e00-\u9fff]', ' ', text)
    english_words = len(re.findall(r'\b[a-zA-Z]+\b', english_text))
    return chinese_chars + english_words


def count_tech_keywords(text: str) -> int:
    """统计文本中出现的技术关键词数量（去重）。"""
    matches = TECH_REGEX.findall(text)
    # findall with groups returns list of tuples when groups exist
    if matches and isinstance(matches[0], tuple):
        # flatten
        all_matches = set(m for group in matches for m in group if m)
    else:
        all_matches = set(matches)
    return len(all_matches)


def find_hollow_words(text: str) -> list[str]:
    """查找文本中的空洞词。"""
    found = []
    text_lower = text.lower()
    for word in HOLLOW_WORDS:
        if word.lower() in text_lower:
            found.append(word)
    return found


# ============================================================
# 检查函数
# ============================================================

def check_file(filepath: str) -> dict:
    """检查单个文件的质量。返回检查结果字典。"""
    result = {
        "file": filepath,
        "status": "pass",  # pass / warn / fail
        "issues": [],
        "score": 0.0,
    }

    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    frontmatter, body = parse_frontmatter(content)
    body_no_eval = remove_self_eval_from_body(body)
    word_count = count_chinese_words(body_no_eval)
    eval_block, score = extract_self_evaluation(body)
    tags = extract_tags(frontmatter)
    tech_kw_count = count_tech_keywords(body_no_eval)
    hollow_words = find_hollow_words(body_no_eval)

    result["score"] = score

    # 1. 字数检查
    if word_count < MIN_WORD_COUNT:
        result["issues"].append(f"字数不足: {word_count}字 (需要≥{MIN_WORD_COUNT})")
        result["status"] = "fail"

    # 2. 自评表检查
    if not eval_block.strip():
        result["issues"].append("缺少自评表 (## 自评)")
        result["status"] = "fail"
    elif score < MIN_SCORE:
        result["issues"].append(f"自评分过低: {score} (需要≥{MIN_SCORE})")
        result["status"] = "fail"

    # 3. 技术关键词检查
    if tech_kw_count < MIN_TECH_KEYWORDS:
        result["issues"].append(f"技术关键词不足: {tech_kw_count}个 (需要≥{MIN_TECH_KEYWORDS})")
        result["status"] = "warn"

    # 4. 空洞词检测
    if hollow_words:
        result["issues"].append(f"包含空洞词: {', '.join(hollow_words)}")
        result["status"] = "warn"

    # 5. 标签检查
    if len(tags) < MIN_TAGS:
        result["issues"].append(f"标签不足: {len(tags)}个 (需要≥{MIN_TAGS})")
        result["status"] = "warn"

    return result


# ============================================================
# 修复函数
# ============================================================

def fix_file(filepath: str, result: dict):
    """对不合格文件添加待改进标记。"""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经有标记
    if content.startswith("> ⚠️ 待改进"):
        return

    issues_text = "；".join(result["issues"])
    warning = f"> ⚠️ 待改进 — {issues_text}\n\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(warning + content)


# ============================================================
# 主函数
# ============================================================

def find_wiki_files(targets: list[str] | None = None) -> list[str]:
    """查找要检查的 wiki 文件。"""
    files = []
    if targets:
        for t in targets:
            # 支持相对于知识库根目录的路径
            if not os.path.isabs(t):
                t = os.path.join(KNOWLEDGE_ROOT, t)
            if os.path.isfile(t) and t.endswith(".md") and os.path.basename(t) != "index.md":
                files.append(t)
            elif os.path.isdir(t):
                for root, _, filenames in os.walk(t):
                    for fn in filenames:
                        if fn.endswith(".md") and fn != "index.md":
                            files.append(os.path.join(root, fn))
    else:
        for subdir in ["concepts", "entities", "sources", "syntheses"]:
            dir_path = os.path.join(WIKI_DIR, subdir)
            if os.path.isdir(dir_path):
                for fn in sorted(os.listdir(dir_path)):
                    if fn.endswith(".md") and fn != "index.md":
                        files.append(os.path.join(dir_path, fn))
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(description="知识库 Wiki 页面质量校验")
    parser.add_argument("targets", nargs="*", help="要检查的文件或目录（默认检查所有wiki页面）")
    parser.add_argument("--fix", action="store_true", help="自动标记不合格页面")
    args = parser.parse_args()

    files = find_wiki_files(args.targets)

    if not files:
        print("未找到要检查的文件。")
        sys.exit(0)

    results = []
    for filepath in files:
        result = check_file(filepath)
        results.append(result)

    # 输出结果
    pass_count = 0
    warn_count = 0
    fail_count = 0

    for r in results:
        # 使用相对于知识库根目录的路径显示
        rel_path = os.path.relpath(r["file"], KNOWLEDGE_ROOT)

        if r["status"] == "pass":
            print(f"✅ {rel_path} (score: {r['score']:.2f})")
            pass_count += 1
        elif r["status"] == "warn":
            print(f"⚠️  {rel_path} — {'；'.join(r['issues'])}")
            warn_count += 1
        else:
            print(f"❌ {rel_path} — {'；'.join(r['issues'])}")
            fail_count += 1

        if args.fix and r["status"] != "pass":
            fix_file(r["file"], r)

    # 汇总
    total = len(results)
    print(f"\n--- 汇总 ---")
    print(f"总计: {total} | ✅ 通过: {pass_count} | ⚠️ 警告: {warn_count} | ❌ 失败: {fail_count}")

    if args.fix and (warn_count + fail_count) > 0:
        print(f"已标记 {warn_count + fail_count} 个待改进页面。")

    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
