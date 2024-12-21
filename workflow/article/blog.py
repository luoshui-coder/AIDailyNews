import os
from datetime import datetime
from dateutil import tz
from loguru import logger


class Blog:
    metadata: str
    guide: str
    categories: list

    def __init__(self, metadata, guide, categories):
        self.metadata = metadata
        self.guide = guide
        self.categories = categories

    def make_blog(self):
        return self.metadata + self.guide + "\n".join(self.categories)


def make_daily_markdown_with(articles, rss_list):
    """生成每日markdown文档
    
    Args:
        articles: 已评分的文章列表
        rss_list: 原始RSS列表
    """
    tags = []
    article_titles = []

    # 首先按评分对所有文章进行排序
    articles.sort(key=lambda x: x.evaluate["score"], reverse=True)
    
    # 获取分类列表
    category_list = []
    for rss in rss_list:
        if rss.config["category"] not in category_list:
            category_list.append(rss.config["category"])

    # 收集标题和标签
    for article in articles:
        tags.extend(article.evaluate.get("tags", []))
        article_titles.append(article.evaluate["title"])

    # 按分类生成内容，但保持评分排序
    category_contents = []
    for category in category_list:
        category_articles = [a for a in articles if a.config["category"] == category]
        if category_articles:
            category_contents.append(make_daily_category(category=category, articles=category_articles))

    # 生成文档
    md_path, meta_data = make_meta_data(description="\n".join(article_titles), tags=tags)
    daily_guide = make_daily_guide(article_titles)  # 标题列表已经按评分排序
    
    if len(category_contents) == 0:
        logger.error("category content is empty!")
        return
        
    blog = Blog(metadata=meta_data, guide=daily_guide, categories=category_contents)
    content = blog.make_blog()
    
    with open(md_path, "w") as fp:
        fp.write(content)


def make_meta_data(description, tags):

    time_zone = tz.gettz("Asia/Shanghai")
    today_with_timezone = datetime.today().astimezone(time_zone)
    today_str = today_with_timezone.strftime("%Y-%m-%d")

    current_directory = os.path.dirname(os.path.abspath(__file__))
    # 获取当前项目的根目录
    project_root = os.path.dirname(current_directory)
    blog_folder = f"{project_root}/../src/content/blog"

    md_title = f"Daily News #{today_str}"
    # Expected "tag" to match "[^\/#\?]+?"
    def rectify_tag_value(value: str):
        res = value.replace('/', '_')
        return f'- "{res}"\n'

    tags_str = "".join([rectify_tag_value(tag) for tag in set(tags)])
    data = f"""---
title: "{md_title}"
date: "{today_with_timezone.strftime("%Y-%m-%d %H:%M:%S")}"
description: "{description}"
tags: 
{tags_str}
---
"""

    path = f"{blog_folder}/dailyNews_{today_str}.md"
    return path, data


def make_daily_category(category, articles):
    """生成分类内容
    
    Args:
        category: 分类名称
        articles: 该分类下的文章列表(已按评分排序)
    """
    if not articles:
        return ""
        
    content = f"## {category}\n"
    
    # 文章已经按评分排序，直接生成内容
    for i, article in enumerate(articles):
        cover = f"![]({article.cover_url})" if article.cover_url else ""
        article_intro = f"""
### [{article.evaluate["title"]}]({article.link})

> *{article.date} · {article.info["title"]}*

{article.evaluate["summary"]}
{cover}"""
        
        # 为除最后一篇外的所有文章添加分隔符
        if i < len(articles) - 1:
            article_intro += "\n---\n"
            
        content += article_intro
        
    return content


def make_daily_guide(titles):
    """生成文章导航
    
    Args:
        titles: 已按评分排序的标题列表
    """
    guide = "".join([f"> - {item}\n" for item in titles])
    return f"\n{guide}\n"
