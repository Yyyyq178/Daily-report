import arxiv
import google.generativeai as genai
import requests
import os
import datetime
import time
import re

# =================配置区域=================
# API 配置
GENAI_API_KEY = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=GENAI_API_KEY)

# 模型选择
# 强烈建议使用 'gemini-1.5-flash'，这是目前 Free Tier 最稳定、额度最高的模型。
# 如果你有 gemini-3 的权限，可以改回 'gemini-3-flash-preview'
MODEL_FAST = 'gemini-3-flash-preview' 
MODEL_DEEP = 'gemini-2.5-pro' 

# 核心关键词 (命中这些词的论文将优先处理)
CORE_KEYWORDS = [
    "Image Restoration", "Super-Resolution", "Denoising", "Flow Based",
    "Masked Autoregressive", "Diffusion Model", "Generative Prior",
    "High-Fidelity", "Perceptual Quality"
]

# 广泛关键词 (用于保留候选)
BROAD_KEYWORDS = [
    "Computer Vision", "Generative", "Transformer", "Gaussian Splatting", 
    "NeRF", "3D Generation", "Video Synthesis", "Multimodal"
]

# 排除关键词 (过滤无关领域)
EXCLUDE_KEYWORDS = ["Medical", "MRI", "CT Scan"]

# =================数据结构=================
class Paper:
    def __init__(self, arxiv_id, title, summary, url, source="arXiv"):
        self.id = arxiv_id
        self.title = title.replace('\n', ' ')
        self.summary = summary.replace('\n', ' ')
        self.url = url
        self.source = source # "HuggingFace" or "arXiv"
        self.score = 0
        self.reasoning = ""
        self.analysis = ""

# =================抓取模块=================
def get_huggingface_papers():
    """获取 HF Daily Papers (高质量源)"""
    print("正在抓取 Hugging Face Daily Papers...")
    papers = {}
    try:
        url = "https://huggingface.co/api/daily_papers"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for item in data[:10]: # 只取前10热度
                aid = item['paper']['id']
                papers[aid] = "HuggingFace Hot"
    except Exception as e:
        print(f"HF 抓取失败 (非致命错误): {e}")
    return papers

def fetch_papers_data(hf_ids):
    """主抓取逻辑：合并 HF 和 arXiv 数据"""
    client = arxiv.Client()
    
    print("正在搜索 arXiv 最新论文 (Max: 40)...")
    search_arxiv = arxiv.Search(
        query="cat:cs.CV",
        max_results=40, # 保持 40 篇以节省额度
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    
    results = []
    seen_ids = set()

    # 处理 arXiv 结果
    for result in client.results(search_arxiv):
        aid = result.get_short_id().split('v')[0]
        seen_ids.add(aid)
        
        source = "arXiv Latest"
        if aid in hf_ids:
            source = "🔥 HuggingFace Hot"
        
        p = Paper(aid, result.title, result.summary, result.entry_id, source)
        results.append(p)

    # 补充抓取 HF 遗漏的论文
    missing_ids = [hid for hid in hf_ids if hid not in seen_ids]
    if missing_ids:
        print(f"补充抓取 {len(missing_ids)} 篇 HF 热门论文...")
        try:
            search_missing = arxiv.Search(id_list=missing_ids)
            for result in client.results(search_missing):
                aid = result.get_short_id().split('v')[0]
                p = Paper(aid, result.title, result.summary, result.entry_id, "🔥 HuggingFace Hot")
                results.append(p)
        except Exception as e:
            print(f"补充抓取失败: {e}")
            
    return results

# =================AI 分析模块=================
def filter_and_score(papers):
    """
    第一层：Python 关键词硬过滤
    第二层：Gemini Flash 快速评分
    """
    candidates = []
    
    # 1. 硬过滤
    for p in papers:
        text = (p.title + p.summary).lower()
        if any(ex.lower() in text for ex in EXCLUDE_KEYWORDS):
            continue
        
        if any(k.lower() in text for k in (CORE_KEYWORDS + BROAD_KEYWORDS)) or "Hot" in p.source:
            candidates.append(p)
            
    print(f"初筛通过: {len(candidates)} 篇，开始 AI 评分...")
    
    # 2. AI 评分
    model = genai.GenerativeModel(MODEL_FAST)
    
    scored_papers = []
    for i, p in enumerate(candidates):
        print(f"正在评分 ({i+1}/{len(candidates)}): {p.title[:30]}...")

        base_priority = "High" if any(k.lower() in p.title.lower() for k in CORE_KEYWORDS) else "Normal"
        
        prompt = f"""
        Role: CV Research Assistant.
        Task: Rate relevance (1-10) for a researcher focusing on: Image Restoration, MAR, Super-Resolution.
        Input:
        Title: {p.title}
        Abstract: {p.summary}
        
        Output format strictly: Score | One-sentence reason
        Example: 8 | Proposes a novel MAR variant for deblurring.
        """
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()
            score_str = text.split('|')[0].strip()
            
            # 解析分数
            found_scores = re.findall(r"\d+", score_str)
            if found_scores:
                p.score = int(float(found_scores[0]))
            else:
                p.score = 5 
            
            p.reasoning = text.split('|')[1].strip() if '|' in text else text
            
            if base_priority == "High" and p.score < 7:
                p.score = 7 
            
            if p.score > 6:
                scored_papers.append(p)
                print(f"  -> 评分成功: {p.score}")

        except Exception as e:
            # 捕获错误但不中断循环
            print(f"  -> 评分失败: {e}")
            # 【关键修改】这里去掉了 continue，确保无论成功失败都会执行下面的 sleep
        
        # 【关键修改】强制等待 60 秒
        # 放在 try...except 外面，确保每次循环末尾都执行
        print("  -> 冷却 60 秒以保护 API 配额...")
        time.sleep(60) 

    scored_papers.sort(key=lambda x: x.score, reverse=True)
    return scored_papers

def deep_analyze_paper(paper):
    """使用模型进行深度审稿"""
    model = genai.GenerativeModel(MODEL_DEEP)
    
    prompt = f"""
    You are an expert reviewer for ECCV/CVPR.
    Analyze the following paper strictly in CHINESE (Markdown).
    
    Target Audience: A researcher working on **Image Restoration** and **Masked Autoregressive (MAR)** models.
    
    Paper:
    Title: {paper.title}
    Abstract: {paper.summary}
    
    Please provide:
    1. **核心创新点 (The "Hook")**: What is strictly new? (1-2 bullet points)
    2. **方法论拆解 (Methodology)**: How does it work? 
       - If it mentions MAR or Transformers, compare it with standard approaches.
    3. **潜在缺陷/局限 (Critical Review)**: As a reviewer, what would you challenge? (e.g., complexity, lack of specific baselines)
    4. **对我的启发**: How can this apply to Image Restoration tasks?
    
    Output strictly in Markdown. No preamble.
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"深度分析失败: {e}")
        return f"> **分析生成失败**: API 调用出错 ({str(e)[:100]}...)"

# =================主程序=================
def main():
    # 1. 获取 ID 列表
    hf_ids = get_huggingface_papers()
    
    # 2. 抓取全文数据
    all_papers = fetch_papers_data(hf_ids)
    print(f"共抓取原始论文: {len(all_papers)} 篇")
    
    if not all_papers:
        print("未抓取到论文，程序结束。")
        return

    # 3. 筛选与评分
    top_papers = filter_and_score(all_papers)
    print(f"最终入选精读: {len(top_papers)} 篇")
    
    # 4. 生成报告
    today = datetime.date.today().strftime("%Y-%m-%d")
    md_content = f"# 🚀 CV 论文日报 | {today}\n\n"
    md_content += f"> 🤖 今日动态：扫描 {len(all_papers)} 篇，精选 {min(5, len(top_papers))} 篇深度解读。\n\n"
    
    # 目录部分
    md_content += "## 📋 目录 (Quick View)\n"
    for p in top_papers[:10]:
        icon = "🔥" if "Hot" in p.source else "📄"
        md_content += f"- **{p.score}分** {icon} [{p.title}]({p.url}) - *{p.reasoning}*\n"
    md_content += "\n---\n"
    
    # 深度分析部分 (只取前 5 篇)
    md_content += "## 🧠 深度解读 (Deep Dive)\n"
    
    deep_dive_count = min(5, len(top_papers))
    
    for i, p in enumerate(top_papers[:deep_dive_count]):
        print(f"正在深度分析第 {i+1}/{deep_dive_count} 篇: {p.title}...")
        analysis = deep_analyze_paper(p)
        
        md_content += f"### {i+1}. {p.title}\n"
        md_content += f"**来源**: {p.source} | **评分**: {p.score}/10 | [Paper Link]({p.url})\n\n"
        md_content += f"{analysis}\n\n"
        md_content += "---\n"
        
        # 深度分析间隔
        if i < deep_dive_count - 1:
            print("等待 300 秒以符合 API 速率限制...")
            time.sleep(300) 

    # 5. 写入文件
    with open("README.md", "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"报告生成完毕！已保存至 README.md")

if __name__ == "__main__":
    main()
