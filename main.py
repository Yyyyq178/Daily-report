import google.generativeai as genai
import requests
import os
import datetime
import time
import re

# =================配置区域=================
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GENAI_API_KEY)

# 推荐使用 Flash 模型进行快速评分，Pro 模型进行深度分析
MODEL_FAST = 'gemini-1.5-flash' 
MODEL_DEEP = 'gemini-1.5-pro' 

# 核心关注领域（影响评分权重）
CORE_KEYWORDS = ["Image Restoration", "Masked Autoregressive", "Flow Matching", "Super-Resolution", "Diffusion", "Image Generation"]

# =================数据结构=================
class Paper:
    def __init__(self, title, summary, url, source):
        self.title = title.replace('\n', ' ')
        self.summary = summary.replace('\n', ' ')
        self.url = url
        self.source = source
        self.score = 0
        self.reasoning = ""

# =================抓取模块=================
def get_huggingface_papers():
    """获取 Hugging Face 前 10 篇热门论文"""
    print("正在抓取 Hugging Face Daily Papers...")
    results = []
    try:
        url = "https://huggingface.co/api/daily_papers"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for item in data[:10]: # 仅取前 10
                paper_info = item['paper']
                aid = paper_info['id']
                results.append(Paper(
                    title=paper_info['title'],
                    summary=paper_info['summary'],
                    url=f"https://arxiv.org/abs/{aid}",
                    source="HuggingFace 🔥"
                ))
    except Exception as e:
        print(f"HF 抓取失败: {e}")
    return results

def get_openreview_papers():
    """获取 OpenReview 最新投稿 (以最近的大会为例)"""
    print("正在抓取 OpenReview 最新投稿...")
    results = []
    try:
        # 抓取 ICLR 2025 的提交作为示例，OpenReview API v2
        # 注意：venue id 会随赛季变化
        api_url = "https://api2.openreview.net/notes?content.venueid=ICLR.cc/2025/Conference&limit=10"
        response = requests.get(api_url, timeout=10)
        if response.status_code == 200:
            notes = response.json().get('notes', [])
            for note in notes:
                content = note.get('content', {})
                title = content.get('title', {}).get('value', 'No Title')
                abstract = content.get('abstract', {}).get('value', 'No Abstract')
                note_id = note.get('id')
                results.append(Paper(
                    title=title,
                    summary=abstract,
                    url=f"https://openreview.net/forum?id={note_id}",
                    source="OpenReview 🎓"
                ))
    except Exception as e:
        print(f"OpenReview 抓取失败: {e}")
    return results

# =================AI 分析模块=================
def score_paper(paper):
    """使用 Gemini 对论文进行 1-10 分打分"""
    model = genai.GenerativeModel(MODEL_FAST)
    prompt = f"""
    Role: Senior CV Researcher.
    Task: Rate the importance (1-10) of this paper for someone working on Image Restoration and Masked Autoregressive (MAR) models.
    Paper Title: {paper.title}
    Abstract: {paper.summary}
    
    Output format: Score | One-sentence reason in Chinese.
    """
    try:
        response = model.generate_content(prompt)
        text = response.text.strip()
        score_match = re.search(r"(\d+)", text)
        score = int(score_match.group(1)) if score_match else 5
        reason = text.split('|')[1].strip() if '|' in text else text
        return score, reason
    except Exception as e:
        print(f"评分出错: {e}")
        return 0, "Error"

def deep_analyze(paper):
    """对 Top 2 论文进行深度中文解读"""
    model = genai.GenerativeModel(MODEL_DEEP)
    prompt = f"""
    请作为计算机视觉专家，深度解析这篇论文，并用中文输出：
    1. 核心创新点：
    2. 对图像恢复(Image Restoration)任务的启发：
    3. 潜在的局限性：
    
    论文标题：{paper.title}
    摘要：{paper.summary}
    """
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"深度分析失败: {e}"

# =================主程序=================
def main():
    # 1. 抓取数据
    all_papers = get_huggingface_papers() + get_openreview_papers()
    print(f"总计抓取候选论文: {len(all_papers)} 篇")
    
    # 2. 依次打分（带冷却防止 429）
    print("开始进行 AI 筛选与打分...")
    for i, p in enumerate(all_papers):
        p.score, p.reasoning = score_paper(p)
        print(f"[{i+1}/{len(all_papers)}] {p.score}分 - {p.title[:40]}...")
        time.sleep(10) # 评分阶段每篇间隔 10 秒
        
    # 3. 排序并取 Top 2
    top_2 = sorted(all_papers, key=lambda x: x.score, reverse=True)[:2]
    
    # 4. 输出最终结果
    print("\n" + "="*50)
    print(f"🚀 今日顶级推荐 (TOP 2)")
    print("="*50 + "\n")
    
    for i, p in enumerate(top_2):
        print(f"第 {i+1} 篇：{p.title}")
        print(f"来源: {p.source} | 评分: {p.score}/10")
        print(f"链接: {p.url}")
        print("-" * 20)
        
        # 深度分析需要较多 Token，再次等待确保 API 稳定
        time.sleep(30)
        analysis = deep_analyze(p)
        print(f"【深度解读】\n{analysis}\n")
        print("="*50 + "\n")

if __name__ == "__main__":
    main()
