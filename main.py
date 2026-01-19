import google.generativeai as genai
import requests
import os
import time
import re
import json
from datetime import datetime

# =================配置区域=================
# 建议检查 Key 是否存在
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GENAI_API_KEY:
    raise ValueError("❌ 未检测到 GEMINI_API_KEY，请检查环境变量设置")

genai.configure(api_key=GENAI_API_KEY)

MODEL_FAST = 'gemini-3.0-flash' 
MODEL_DEEP = 'gemini-3.0-flash' 

# 核心关注领域
CORE_KEYWORDS = ["Image Restoration", "Masked Autoregressive", "Flow Matching", "Super-Resolution", "Diffusion", "Image Generation"]

# =================数据结构=================
class Paper:
    def __init__(self, title, summary, url, source):
        self.title = title.replace('\n', ' ').strip()
        self.summary = summary.replace('\n', ' ').strip()
        self.url = url
        self.source = source
        self.score = 0
        self.reasoning = ""

# =================抓取模块=================
def get_huggingface_papers():
    print("📡 正在抓取 Hugging Face Daily Papers...")
    results = []
    try:
        url = "https://huggingface.co/api/daily_papers"
        response = requests.get(url, timeout=8)
        if response.status_code == 200:
            data = response.json()
            # HF API 有时返回的是 list 有时是按日期分类的 dict，做个兼容
            items = data if isinstance(data, list) else []
            if not items and isinstance(data, dict):
                 # 尝试获取最新日期的数据 (简化逻辑)
                 items = list(data.values())[0] if data else []

            for item in items[:8]: # 限制数量以加快测试
                paper_info = item['paper']
                results.append(Paper(
                    title=paper_info['title'],
                    summary=paper_info['summary'],
                    url=f"https://arxiv.org/abs/{paper_info['id']}",
                    source="HuggingFace 🔥"
                ))
    except Exception as e:
        print(f"⚠️ HF 抓取遇到问题: {e}")
    return results

def get_openreview_papers():
    print("📡 正在抓取 OpenReview (ICLR 2025)...")
    results = []
    try:
        # 使用更通用的 API 搜索关键词，避免 venueid 变动导致抓空
        # 这里演示搜索 'Image Restoration' 相关的最新投稿
        domain = "ICLR.cc/2025/Conference" # 或 use search query
        api_url = f"https://api2.openreview.net/notes?content.venueid={domain}&limit=8"
        
        response = requests.get(api_url, timeout=8)
        if response.status_code == 200:
            notes = response.json().get('notes', [])
            for note in notes:
                content = note.get('content', {})
                # V2 API 结构兼容
                title = content.get('title', {}).get('value', 'No Title')
                abstract = content.get('abstract', {}).get('value', 'No Abstract')
                results.append(Paper(
                    title=title,
                    summary=abstract,
                    url=f"https://openreview.net/forum?id={note.get('id')}",
                    source="OpenReview 🎓"
                ))
        else:
            print(f"OpenReview API 状态码: {response.status_code}")
    except Exception as e:
        print(f"⚠️ OpenReview 抓取遇到问题: {e}")
    return results

# =================AI 分析模块=================
def score_paper(paper):
    """
    使用 Gemini Flash 打分
    优化点：传入了 CORE_KEYWORDS，并强制 JSON 输出以便解析
    """
    model = genai.GenerativeModel(
        MODEL_FAST,
        generation_config={"response_mime_type": "application/json"} # 强制 JSON
    )
    
    # 将关键词列表转为字符串
    keywords_str = ", ".join(CORE_KEYWORDS)
    
    prompt = f"""
    You are a Senior Computer Vision Researcher acting as a paper filter.
    
    My Core Interests: [{keywords_str}].
    
    Task: Rate the following paper from 1 to 10 based on relevance to my interests and potential impact.
    - 10: Must read. Directly addresses core interests with high novelty.
    - 1: Irrelevant.
    
    Paper Title: {paper.title}
    Abstract: {paper.summary[:1000]} (truncated)
    
    Output strictly in JSON format:
    {{
        "score": int,
        "reason": "short explanation in Chinese"
    }}
    """
    try:
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        return data.get("score", 0), data.get("reason", "解析失败")
    except Exception as e:
        print(f"⚠️ 评分出错 ({paper.title[:10]}...): {e}")
        return 0, "Error"

def deep_analyze(paper):
    print(f"🧠 正在深度阅读: {paper.title}...")
    model = genai.GenerativeModel(MODEL_DEEP)
    prompt = f"""
    请作为计算机视觉专家，深度解析这篇论文。
    核心关注点：{", ".join(CORE_KEYWORDS)}
    
    论文标题：{paper.title}
    摘要：{paper.summary}
    
    请用中文 Markdown 格式输出：
    1. **核心创新点 (Key Contribution)**: 一句话总结。
    2. **技术细节 (Methodology)**: 它是如何结合 {CORE_KEYWORDS[0]} 或相关技术的？
    3. **对我的启发 (Takeaway)**: 针对做 Image Restoration 的研究员，这就话有什么借鉴意义？
    4. **潜在缺陷 (Limitations)**.
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"深度分析失败: {e}"

# =================报告生成模块=================
def save_report(all_papers, top_data):
    """
    生成 Markdown 报告并写入 README.md
    """
    print("\n📝 正在生成日报文件...")
    
    # 获取当前日期
    current_date = datetime.now().strftime("%Y-%m-%d")
    
    # 构建 Markdown 内容
    md_content = []
    md_content.append(f"# 🚀 CV 论文日报 | {current_date}\n")
    md_content.append(f"> 🤖 今日动态：扫描 {len(all_papers)} 篇，精选 {len(top_data)} 篇深度解读。\n")
    
    # 目录部分
    md_content.append("## 📋 目录 (Quick View)\n")
    if not top_data:
        md_content.append("今日无高分推荐。\n")
    else:
        for idx, item in enumerate(top_data):
            paper = item['paper']
            # 创建简单的锚点链接
            anchor = f"item-{idx}"
            md_content.append(f"- [{paper.title}](#{anchor}) (Score: {paper.score})\n")
    
    md_content.append("\n---\n")
    
    # 深度解读部分
    md_content.append("## 🧠 深度解读 (Deep Dive)\n")
    if not top_data:
        md_content.append("暂时没有深度分析内容。\n")
    else:
        for idx, item in enumerate(top_data):
            paper = item['paper']
            analysis = item['analysis']
            anchor = f"item-{idx}"
            
            md_content.append(f"### <a id='{anchor}'></a>{idx+1}. {paper.title}\n")
            md_content.append(f"**来源**: {paper.source} | **评分**: {paper.score}/10\n")
            md_content.append(f"**原文链接**: [{paper.url}]({paper.url})\n\n")
            md_content.append(f"{analysis}\n")
            md_content.append("\n---\n")

    # 写入文件
    try:
        with open("README.md", "w", encoding="utf-8") as f:
            f.writelines(md_content)
        print("✅ README.md 更新成功！")
    except Exception as e:
        print(f"❌ 写入文件失败: {e}")

# =================主程序=================
def main():
    # 1. 抓取
    all_papers = get_huggingface_papers() + get_openreview_papers()
    print(f"📚 总计获取候选论文: {len(all_papers)} 篇")
    
    if not all_papers:
        print("❌ 未获取到任何论文，请检查 API 或网络。")
        return

    # 2. 快速打分 (去除长时间 sleep，Flash 很快且限额高)
    print("\n⚡ 开始 AI 极速筛选...")
    for i, p in enumerate(all_papers):
        # 简单的进度显示
        print(f"\r处理中 [{i+1}/{len(all_papers)}]: {p.title[:30]}...", end="")
        p.score, p.reasoning = score_paper(p)

        time.sleep(20) 
    
    print("\n✅ 筛选完成！")

    # 3. 排序并取 Top 2
    # 过滤掉低分 (例如 5 分以下)，然后排序
    top_candidates = [p for p in all_papers if p.score >= 5]
    top_2 = sorted(top_candidates, key=lambda x: x.score, reverse=True)[:2]
    
    if not top_2:
        print("😅 没有找到高分论文，可能是今天的论文都与关注点无关。")
        # 兜底：取原始最高分
        top_2 = sorted(all_papers, key=lambda x: x.score, reverse=True)[:2]

    # 4. 输出结果并收集数据用于报告
    print("\n" + "="*50)
    print(f"🚀 今日顶级推荐 (TOP 2)")
    print("="*50 + "\n")
    
    report_data = [] # 用于存储生成的报告内容

    for i, p in enumerate(top_2):
        print(f"🏆 第 {i+1} 名：{p.title}")
        print(f"来源: {p.source} | 💡 评分: {p.score}/10")
        print(f"理由: {p.reasoning}")
        print(f"链接: {p.url}")
        print("-" * 30)
        
        # 深度分析
        analysis = deep_analyze(p)
        print(f"\n{analysis}\n")
        print("="*50 + "\n")
        
        # 收集数据
        report_data.append({
            "paper": p,
            "analysis": analysis
        })

        # Pro 模型稍微多歇一会
        time.sleep(100)
    
    # 5. 生成并保存 Markdown 报告
    save_report(all_papers, report_data)

if __name__ == "__main__":
    main()
