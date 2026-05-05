#!/usr/bin/env python3
"""批量给 wiki 文章添加 YAML frontmatter 并生成 dashboard 数据 JS"""

import os
import re
from datetime import datetime

KB_ROOT = "/Users/liujun/Nutstore Files/我的坚果云/knowledge"
WIKI_DIR = os.path.join(KB_ROOT, "wiki")
DOCS_DIR = os.path.join(KB_ROOT, "docs")

# 文章元数据配置：手动设置每篇文章的 tags, rating, description
# 没有配置的会从标题自动生成
ARTICLE_META = {
    # Concepts
    "AI-Agent-Self-Improving": {"tags": ["AI-Agent", "Self-Improvement", "LLM"], "rating": 8.5, "description": "AI Agent 自我改进机制，包括代码质量评估、记忆管理与技能迭代"},
    "AST-Driven-AI-Editing": {"tags": ["AST", "代码编辑", "AI"], "rating": 8.0, "description": "基于 AST 的 AI 代码编辑技术，绕过 DOM 实现精准代码操作"},
    "Claude-Ecosystem-Tools": {"tags": ["Claude", "Ecosystem", "Tool"], "rating": 8.5, "description": "Claude 生态工具全景分析，包括 Claude Code、MCP、Skills 等"},
    "Client-Side-Tool-Calling": {"tags": ["Tool-Calling", "Client-Side", "LLM"], "rating": 7.5, "description": "客户端 Tool Calling 方案，在浏览器端直接调用 LLM 工具"},
    "Context-Window-Optimization": {"tags": ["Context-Window", "优化", "Coding-Agent"], "rating": 9.0, "description": "AI Coding Agent 的上下文窗口优化策略，核心效率问题深度解析"},
    "DeepEP": {"tags": ["DeepSeek", "EP", "专家并行"], "rating": 7.5, "description": "DeepSeek DeepEP 专家并行通信机制"},
    "Memory-Management": {"tags": ["Memory", "AI-Agent", "记忆"], "rating": 8.0, "description": "AI Agent 记忆管理方案，包括短期记忆、长期记忆和检索策略"},
    "PersonalAI-KG-Comparison": {"tags": ["知识图谱", "LLM", "个性化"], "rating": 8.0, "description": "PersonalAI 方案中知识图谱存储与检索方案的对比分析"},
    "PersonalAI-KG-Retrieval": {"tags": ["知识图谱", "检索", "LLM"], "rating": 8.0, "description": "个性化 LLM 中的知识图谱存储与检索方案"},
    "Pretext-js": {"tags": ["JavaScript", "排版", "性能"], "rating": 7.5, "description": "Pretext.js 绕过 DOM 布局重排的高性能文本排版方案"},
    "Prompt-Caching-Pitfalls": {"tags": ["Prompt-Caching", "成本优化", "LLM"], "rating": 9.0, "description": "Prompt Caching 的常见陷阱和最佳实践，避免缓存失效"},
    "Real-world-AI-Applications": {"tags": ["AI", "应用", "落地"], "rating": 7.5, "description": "AI 在真实场景中的应用案例分析"},
    "Self-RAG": {"tags": ["RAG", "Self-Reflection", "检索"], "rating": 9.0, "description": "自反思检索增强生成，解决传统 RAG 盲目检索和无差别注入问题"},
    "Skill-Auto-Creation": {"tags": ["Skill", "自动化", "AI-Agent"], "rating": 8.5, "description": "AI Agent Skill 自动创建机制，从使用中学习生成新技能"},
    "Skill-Evaluation-Framework": {"tags": ["Skill", "评估", "量化"], "rating": 8.5, "description": "8 维度 Skill 量化评估框架，系统化衡量 Agent 技能质量"},
    "TNL-Persistent-Plan-Mode": {"tags": ["TNL", "Agent", "规划"], "rating": 7.5, "description": "Typed Natural Language 实现的 Agent 持久化规划方案"},
    "Weak-Model-Orchestration": {"tags": ["弱模型", "协作", "编排"], "rating": 8.5, "description": "弱模型协作架构，低成本实现复杂任务的模型编排策略"},
    "andrej-karpathy-skills": {"tags": ["Karpathy", "Skill", "教程"], "rating": 8.0, "description": "Andrej Karpathy 的 AI 技能体系深度分析报告"},

    # Entities
    "Claude-Code-Source-Analysis": {"tags": ["Claude-Code", "源码分析", "Coding-Agent"], "rating": 9.5, "description": "Claude Code v2.1.88 源码深度分析，架构设计与实现细节"},
    "DeepSeek-V4": {"tags": ["DeepSeek", "开源模型", "长上下文"], "rating": 8.5, "description": "DeepSeek V4 百万上下文窗口开源模型分析"},
    "Fewshell": {"tags": ["Shell", "AI", "终端"], "rating": 7.0, "description": "Fewshell AI 驱动的终端工具"},
    "GKE-Agent-Sandbox": {"tags": ["GKE", "Sandbox", "Agent"], "rating": 7.5, "description": "GKE Agent Sandbox 安全沙箱方案"},
    "GPT-5.5": {"tags": ["GPT", "OpenAI", "大模型"], "rating": 8.0, "description": "GPT-5.5 模型分析"},
    "Ghostty-Leaving-GitHub": {"tags": ["Ghostty", "开源", "GitHub"], "rating": 8.0, "description": "Ghostty 离开 GitHub 事件，开源基础设施信任危机分析"},
    "GoClick": {"tags": ["Go", "AI", "Agent"], "rating": 7.0, "description": "GoClick Go 语言 AI Agent 框架"},
    "Hermes-Agent": {"tags": ["Hermes", "Agent", "源码分析"], "rating": 9.0, "description": "Hermes Agent 深度分析报告，架构与核心实现"},
    "Hy-MT-Offline-Translation": {"tags": ["翻译", "离线", "移动端"], "rating": 7.5, "description": "Hy-MT 手机端离线翻译模型方案"},
    "Kora-AI-Native-OS": {"tags": ["AI-OS", "操作系统", "原生"], "rating": 8.0, "description": "Kora AI 原生操作系统层设计"},
    "OpenClaw": {"tags": ["OpenClaw", "Agent", "网关"], "rating": 9.5, "description": "多通道 AI Agent 网关平台，个人 AI 助手的运行时基础设施"},
    "Operit": {"tags": ["Operit", "Android", "AI-Agent"], "rating": 8.5, "description": "Operit Android 平台最强 AI Agent 应用分析"},
    "SmartPerfetto": {"tags": ["SmartPerfetto", "性能分析", "Android"], "rating": 8.0, "description": "SmartPerfetto 性能分析工具"},
    "Warp-Terminal-Analysis": {"tags": ["Warp", "终端", "源码分析"], "rating": 8.5, "description": "Warp Terminal 源码深度分析，现代终端设计"},
    "Zed-1.0": {"tags": ["Zed", "编辑器", "Rust"], "rating": 7.5, "description": "Zed 1.0 编辑器分析"},
    "claude-context": {"tags": ["Claude", "Context", "记忆"], "rating": 8.0, "description": "Claude Context 上下文管理工具"},
    "claude-mem": {"tags": ["Claude", "Memory", "持久化"], "rating": 8.0, "description": "Claude-Mem 持久化记忆方案深度分析"},
    "deer-flow": {"tags": ["字节跳动", "Agent", "框架"], "rating": 8.5, "description": "字节跳动 Deer-Flow 长周期 SuperAgent 框架"},
    "harmonist": {"tags": ["Agent", "编排", "零依赖"], "rating": 7.5, "description": "Harmonist 零依赖 Agent 编排框架"},
    "llm_wiki": {"tags": ["LLM", "Wiki", "知识库"], "rating": 7.0, "description": "LLM Wiki 大语言模型知识库"},
    "mattpocock-skills": {"tags": ["Skill", "TypeScript", "教程"], "rating": 7.5, "description": "Matt Pocock 的 TypeScript 技能集合"},
    "ml-intern": {"tags": ["HuggingFace", "ML", "实习"], "rating": 7.0, "description": "HuggingFace ml-intern 机器学习实习项目"},
    "open-design": {"tags": ["设计", "本地优先", "AI"], "rating": 8.0, "description": "Open Design 本地优先的 AI 设计工具"},
    "trycua-cua": {"tags": ["CUA", "Computer-Use", "Agent"], "rating": 8.5, "description": "trycua/cua Computer-Use Agent 基础设施"},

    # Sources
    "AI-Code-Tool-Pricing-2026": {"tags": ["定价", "Copilot", "Claude", "成本"], "rating": 8.0, "description": "2026年 AI 代码工具涨价潮分析，Copilot 和 Claude 成本对比"},
    "Apple-Foundation-Models-Practice": {"tags": ["Apple", "Foundation-Models", "实战"], "rating": 8.0, "description": "Apple Foundation Models Framework 实战指南"},
    "CISA-NSA-Agent-Security": {"tags": ["CISA", "NSA", "安全", "Agent"], "rating": 7.5, "description": "CISA/NSA 发布的 AI Agent 安全部署指南"},
    "Claude-Code-Linux-Kernel-Vuln": {"tags": ["Claude-Code", "Linux", "安全", "漏洞"], "rating": 8.5, "description": "Claude Code 发现 Linux 内核 23 年历史漏洞"},
    "Coding-Agents-Critique-2026": {"tags": ["Coding-Agent", "批评", "开源"], "rating": 8.0, "description": "17年开源老兵对 Coding Agents 堆功能现象的深度批评"},
    "Hermes-Agent-源码分析": {"tags": ["Hermes", "源码分析", "Agent"], "rating": 9.0, "description": "Hermes Agent 源码级分析，架构设计与核心机制"},
    "OpenClaw-源码分析": {"tags": ["OpenClaw", "源码分析", "Agent"], "rating": 9.5, "description": "OpenClaw 源码级深度分析，多通道 Agent 网关实现"},
    "OpenMobile-Paper-V2": {"tags": ["OpenMobile", "移动端", "Agent", "论文"], "rating": 8.0, "description": "OpenMobile 开放移动 Agent 框架论文 V2"},
    "OpenMobile-Paper": {"tags": ["OpenMobile", "移动端", "Agent", "论文"], "rating": 8.0, "description": "OpenMobile 开放移动端 Agent 框架论文"},
    "claude-context-源码分析": {"tags": ["claude-context", "源码分析", "记忆"], "rating": 8.5, "description": "claude-context 源码分析，上下文管理实现"},
    "推荐书单-2026年4月": {"tags": ["书单", "推荐", "AI"], "rating": 7.5, "description": "2026年4月推荐书单，涵盖 AI 和技术方向"},

    # Syntheses
    "Agent-Dev-Tools-2026-04": {"tags": ["Agent", "工具生态", "趋势"], "rating": 9.0, "description": "2026年4月 AI Agent 编排与开发工具生态综述"},
    "Hermes-vs-OpenClaw对比分析": {"tags": ["Hermes", "OpenClaw", "对比", "Agent"], "rating": 9.0, "description": "Hermes vs OpenClaw 深度对比分析，架构与功能差异"},
    "SmartPerfetto-vs-SmartInspector对比分析": {"tags": ["SmartPerfetto", "对比", "性能分析"], "rating": 8.5, "description": "SmartPerfetto vs SmartInspector 性能分析工具对比"},
}


def get_file_mtime(filepath):
    """获取文件修改日期"""
    ts = os.path.getmtime(filepath)
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")


def extract_title(content):
    """从 markdown 内容中提取第一个 # 标题"""
    match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
    return match.group(1).strip() if match else None


def extract_description(content, meta):
    """提取描述：优先用配置的，否则从文章第一段提取"""
    if meta and "description" in meta:
        return meta["description"]
    
    # 跳过 frontmatter，找到第一个非空段落
    lines = content.split('\n')
    desc_lines = []
    in_frontmatter = False
    started = False
    for line in lines:
        if line.strip() == '---':
            if not started:
                in_frontmatter = True
                started = True
                continue
            else:
                in_frontmatter = False
                continue
        if in_frontmatter:
            continue
        if line.startswith('#'):
            continue
        if line.startswith('>') or line.startswith('|'):
            continue
        stripped = line.strip()
        if stripped:
            desc_lines.append(stripped)
            if len(desc_lines) >= 2:
                break
    return ' '.join(desc_lines) if desc_lines else ""


def add_frontmatter(filepath, category, name):
    """给文件添加 YAML frontmatter"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 检查是否已有 frontmatter
    has_frontmatter = content.startswith('---')
    
    meta = ARTICLE_META.get(name, {})
    title = extract_title(content) or name
    tags = meta.get("tags", [])
    rating = meta.get("rating", 7.0)
    description = extract_description(content, meta)
    date = get_file_mtime(filepath)
    
    if has_frontmatter:
        # 已有 frontmatter，检查是否需要追加字段
        # 简单处理：如果已有 category 就跳过
        if 'category:' in content[:500]:
            return title, tags, rating, description, date
    
    # 构建 frontmatter
    tags_str = ', '.join(tags)
    fm = f"""---
title: "{title.replace('"', '\\"')}"
category: {category}
tags: [{tags_str}]
rating: {rating}
description: "{description.replace('"', '\\"')}"
date: {date}
---
"""
    
    if has_frontmatter:
        # 替换已有的 frontmatter
        end_idx = content.index('---', 3) + 3
        content = fm + content[end_idx:].lstrip('\n')
    else:
        content = fm + '\n' + content
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return title, tags, rating, description, date


def main():
    articles = []
    
    categories = {
        'concepts': 'wiki/concepts',
        'entities': 'wiki/entities',
        'sources': 'wiki/sources',
        'syntheses': 'wiki/syntheses',
    }
    
    for category, subdir in categories.items():
        dirpath = os.path.join(KB_ROOT, subdir)
        if not os.path.isdir(dirpath):
            continue
        for fname in sorted(os.listdir(dirpath)):
            if not fname.endswith('.md') or fname == 'index.md':
                continue
            name = fname[:-3]
            filepath = os.path.join(dirpath, fname)
            
            title, tags, rating, description, date = add_frontmatter(filepath, category, name)
            
            # URL 路径
            url = f"wiki/{category}/{fname}"
            
            articles.append({
                "title": title,
                "category": category,
                "tags": tags,
                "rating": rating,
                "description": description,
                "date": date,
                "url": url,
            })
            print(f"  ✓ {category}/{name}")
    
    # 生成 JS 数据文件
    js_content = "// Auto-generated dashboard data\nwindow.__kb_articles = " + __import__('json').dumps(articles, ensure_ascii=False, indent=2) + ";\n"
    
    js_path = os.path.join(DOCS_DIR, "overrides", "dashboard-data.js")
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(js_content)
    
    print(f"\n✅ 共处理 {len(articles)} 篇文章")
    print(f"✅ 数据文件: {js_path}")


if __name__ == '__main__':
    main()
