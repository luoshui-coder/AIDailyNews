import os, json, datetime, glob
from workflow.gpt.summary import evaluate_article_with_gpt
import workflow.article.rss as rss
import workflow.article.blog as blog
import time
from loguru import logger

def execute(rss_resource="workflow/resources"):
    """
    主执行函数，处理RSS文章并生成日报
    
    Args:
        rss_resource: RSS配置文件所在目录路径
    
    流程:
    1. 检查缓存
    2. 获取RSS文章
    3. 保存文章(如果启用缓存)
    4. 筛选优质文章
    5. 生成markdown格式的日报
    """
    # 检查是否有有效的缓存文件
    cache_folder, cache_file = find_valid_file()
    # 解析RSS文章(如果有缓存则从缓存读取)
    origin_article_list = parse_daily_rss_article(rss_resource, cache_file)
    # 如果启用缓存，保存解析结果
    if cache_folder:
        save_article(origin_article_list, cache_folder)
    # 筛选评分高的文章
    articles = find_favorite_article(origin_article_list)
    # 生成markdown格式的日报
    blog.make_daily_markdown_with(articles, origin_article_list)

def parse_daily_rss_article(rss_resource, cache_file=None):
    """
    获取RSS文章信息
    
    Args:
        rss_resource: RSS配置文件目录
        cache_file: 缓存文件路径(如果有)
    
    Returns:
        list: RSS文章列表
    """
    # 如果有缓存文件，直接从缓存读取
    if cache_file:
        return decode_article(cache_file)
    
    # 加载RSS配置
    rss_items = rss.load_rss_configs(rss_resource)

    # 解析所有RSS源
    daily_rss = []
    for item in rss_items:
        rss_list = rss.parse_rss_config(item)
        for rss_item in rss_list:
            daily_rss.append(rss_item)
            logger.info(f"date: {rss_item.date}, link: {rss_item.link}")
    return daily_rss

def find_favorite_article(rss_articles):
    """
    筛选评分最高的文章
    
    筛选标准:
    - 评分 >= 7分的文章才会被考虑
    - 评分 = 10分的文章优先选择
    - 每个RSS源有独立的输出数量限制
    - 最终输出不超过设定的最大文章数
    - 去除重复或相似的文章
    """
    # 限制分析文章数量
    max_analyze_nums = 100
    rss_articles = rss_articles[:max_analyze_nums]
    max_article_nums = int(os.environ.get("MAX_ARTICLE_NUMS", "30"))
    
    # 按RSS源分组
    rss_resource = {}
    for article in rss_articles:
        if not article.summary:
            continue
        rss_category = article.info["title"]
        if rss_category in rss_resource.keys():
            rss_resource[rss_category].append(article)
        else:
            rss_resource[rss_category] = [article]

    # 处理每个RSS源的文章
    show_articles = []
    seen_titles = {}  # 用于记录已见过的标题
    
    for key, articles in rss_resource.items():
        time.sleep(2)
        evaluate_results = evaluate_article_with_gpt(articles)
        
        # 关联评估结果
        for evaluate in evaluate_results:
            for article in articles:
                if article.link == evaluate.get("link"):
                    article.evaluate = evaluate

        # 过滤低分文章
        articles = [item for item in articles if item.evaluate and item.evaluate.get("score", 0) >= 7]
        if not articles:
            continue

        # 按评分排序
        articles.sort(key=lambda x: x.evaluate["score"], reverse=True)
        
        # 去重处理
        filtered_articles = []
        for article in articles:
            title = article.evaluate["title"]
            # 移除emoji和空格后的标题用于比较
            clean_title = ''.join(c for c in title if not is_emoji(c)).strip()
            
            # 检查是否与已有标题相似
            is_duplicate = False
            for seen_title in seen_titles:
                if is_similar_title(clean_title, seen_title):
                    # 如果新文章评分更高，替换旧文章
                    if article.evaluate["score"] > seen_titles[seen_title].evaluate["score"]:
                        filtered_articles.remove(seen_titles[seen_title])
                        filtered_articles.append(article)
                        seen_titles[clean_title] = article
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                filtered_articles.append(article)
                seen_titles[clean_title] = article

        # 选择文章
        output_count = articles[0].config.get("output_count", 2)
        select_articles = filtered_articles[:output_count]
        show_articles.extend(select_articles)
        
    # 最终排序和数量限制
    show_articles.sort(key=lambda x: x.evaluate["score"], reverse=True)
    return show_articles[:max_article_nums]

def is_emoji(c):
    """判断字符是否为emoji"""
    return c in ['🤖', '💡', '🔬', '📱', '🚀', '⚡', '🧠', '🛠️', '📊', '🏥', 
                '🎓', '🏭', '🌾', '💰', '🤝', '📈', '🌐', '🔒', '📋', '🎯',
                '📚', '🎥', '📣', '💸', '🛡️', '🚨']

def is_similar_title(title1, title2):
    """
    判断两个标题是否相似
    使用简单的相似度算法，可以根据需要调整
    """
    # 将标题转换为小写进行比较
    title1 = title1.lower()
    title2 = title2.lower()
    
    # 如果标题完全相同
    if title1 == title2:
        return True
        
    # 如果一个标题包含另一个标题的大部分内容
    if title1 in title2 or title2 in title1:
        return True
        
    # 计算单词重叠度
    words1 = set(title1.split())
    words2 = set(title2.split())
    common_words = words1.intersection(words2)
    
    # 如果共同单词占比超过60%，认为是相似标题
    similarity = len(common_words) / max(len(words1), len(words2))
    return similarity > 0.4

def find_valid_file():
    """
    查找有效的RSS缓存文件
    
    Returns:
        tuple: (缓存目录, 缓存文件路径)
    """
    # 检查是否启用缓存
    if os.environ.get("RSS_CACHE_ENABLE") != "true":
        return None, None

    current_directory = os.path.dirname(os.path.abspath(__file__))
    cache_folder = f"{current_directory}/draft"
    today_str = datetime.date.today().strftime('%Y-%m-%d')
    # 查找今天的缓存文件
    cache_files = glob.glob(f"{cache_folder}/*{today_str}.json")
    cache_file = cache_files[-1] if cache_files else None
    return cache_folder, cache_file

def save_article(articles, draft_folder):
    """
    保存文章到缓存文件
    
    Args:
        articles: 文章列表
        draft_folder: 缓存目录
    """
    data = []
    path = f"{draft_folder}/article_cache_{datetime.date.today().strftime('%Y-%m-%d')}.json"
    # 将文章对象转换为字典
    for article in articles:
        data.append(article.__dict__)

    # 保存为JSON文件
    with open(path, "w") as fp:
        fp.write(json.dumps(data, indent=4))

def decode_article(path):
    """
    从缓存文件解析文章
    
    Args:
        path: 缓存文件路径
    
    Returns:
        list: 文章对象列表
    """
    rss_list = []
    with open(path, "r") as fp:
        object_list = json.loads(fp.read())
        # 将JSON数据转换回文章对象
        for item in object_list:
            rss_item = rss.Article()
            for key, value in item.items():
                setattr(rss_item, key, value)
            rss_list.append(rss_item)
    return rss_list
