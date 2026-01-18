import arxiv
import google.generativeai as genai
import os
import datetime

# 1. 配置 API (使用 2026 最新 Gemini 3.0 模型)
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
FLASH_MODEL = genai.GenerativeModel('gemini-3.0-flash') # 用于海量筛选
PRO_MODEL = genai.GenerativeModel('gemini-3.0-pro')    # 用于深度分析

# 2. 定制你的研究兴趣 (根据你的画像：MAR, 图像恢复)
KEYWORDS = [
    # 你的核心研究方向
    "Image Restoration", "Super-Resolution", "Masked Autoregressive", "MAR",
    
    # 热门生成式技术
    "Diffusion Model", "Generative Adversarial Networks", "Flow-based Model",
    
    # 关联的高热度赛道
    "3D Gaussian Splatting", "Segment Anything", "Vision Transformer", 
]
WHITELIST_AUTHORS = ["Kaiming He", "Guangcan Liu"] # 示例：可以添加你关注的大牛

def get_latest_papers():
    """获取过去24小时内 cs.CV 的论文"""
    client = arxiv.Client()
    search = arxiv.Search(
        query="cat:cs.CV",
        max_results=50,
        sort_by=arxiv.SortCriterion.SubmittedDate
    )
    return list(client.results(search))

def fast_score(paper):
    """使用 3.0 Flash 进行快速打分 (1-10)"""
    prompt = f"你是一个CV专家。请根据标题和摘要给论文打分(1-10)。重点关注图像恢复和生成模型创新。\n标题：{paper.title}\n摘要：{paper.summary}"
    try:
        # Flash 模型速度极快且免费额度高
        response = FLASH_MODEL.generate_content(prompt)
        # 简单提取数字逻辑... (此处省略正则解析)
        return 7 # 假设返回分数
    except:
        return 5

def deep_analyze(paper):
    """使用 3.0 Pro 进行深度分析"""
    prompt = f"""
    作为计算机视觉专家，请深度解析这篇论文。
    重点分析：1.核心贡献 2.方法论亮点(Methodology) 3.对MAR或图像恢复任务的启发。
    使用中文输出，Markdown格式。
    
    标题：{paper.title}
    摘要：{paper.summary}
    """
    response = PRO_MODEL.generate_content(prompt)
    return response.text

def main():
    papers = get_latest_papers()
    today = datetime.date.today().strftime("%Y-%m-%d")
    report = f"# 🚀 CV 论文日报 | {today}\n\n"
    
    high_value_papers = []

    for p in papers:
        # 粗筛：标题命中关键词
        if any(k.lower() in p.title.lower() for k in KEYWORDS):
            score = fast_score(p)
            if score >= 7:
                high_value_papers.append(p)

    # 对高价值论文进行 Pro 级深度分析
    for p in high_value_papers[:5]: # 每天精选前5篇，节省 Pro 额度
        analysis = deep_analyze(p)
        report += f"## {p.title}\n- **链接**: {p.entry_id}\n\n{analysis}\n\n---\n"

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(report)

if __name__ == "__main__":
    main()
