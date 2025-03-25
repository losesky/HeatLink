#!/usr/bin/env python3
"""
使用Selenium检查澎湃新闻网站结构，以便更新抓取逻辑
"""

import time
import logging
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("thepaper_checker")

def setup_driver():
    """设置Selenium WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 无头模式
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")  # 设置窗口大小
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    logger.info("正在初始化Chrome WebDriver...")
    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    logger.info("Chrome WebDriver初始化完成")
    return driver

def check_thepaper_website():
    """检查澎湃新闻网站结构"""
    driver = None
    try:
        driver = setup_driver()
        
        # 打开澎湃新闻首页
        url = "https://www.thepaper.cn/"
        logger.info(f"正在打开 {url}")
        driver.get(url)
        
        # 等待页面加载
        logger.info("等待页面加载...")
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        time.sleep(5)  # 额外等待以确保动态内容加载
        
        # 保存页面源代码
        html_source = driver.page_source
        output_dir = "/tmp/thepaper_debug"
        os.makedirs(output_dir, exist_ok=True)
        
        with open(f"{output_dir}/thepaper_homepage.html", "w", encoding="utf-8") as f:
            f.write(html_source)
        logger.info(f"页面源代码已保存到 {output_dir}/thepaper_homepage.html")
        
        # 保存截图
        screenshot_path = f"{output_dir}/thepaper_screenshot.png"
        driver.save_screenshot(screenshot_path)
        logger.info(f"截图已保存到 {screenshot_path}")
        
        # 尝试各种可能的选择器
        possible_selectors = [
            "div.index_ppreport__slNZB a", 
            ".mdCard a",
            "ul a.index_inherit__A1ImK", 
            ".home_wrapper__H8fk4 a",
            ".content a",
            "div[class*=cardBox] a",
            "a[href*=newsDetail]",  # 查找链接到新闻详情的a标签
            ".news_box a",  # 新增可能的选择器
            ".index_news__GMcmR a",  # 新增可能的选择器
            "a.tit",  # 新增可能的选择器
            ".js-deepshare-hotnews a",  # 新增可能的选择器
            ".left_side a",  # 新增可能的选择器
            ".hot_news a",  # 新增可能的选择器
            ".newsbox a"  # 新增可能的选择器
        ]
        
        # 测试所有选择器并记录结果
        for selector in possible_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                logger.info(f"选择器 '{selector}': 找到 {len(elements)} 个元素")
                
                if elements and len(elements) >= 3:
                    logger.info(f"选择器 '{selector}' 可能有效，找到以下内容:")
                    
                    # 保存前5个元素的HTML和文本
                    for i, element in enumerate(elements[:5]):
                        try:
                            text = element.text.strip()
                            href = element.get_attribute("href")
                            html = element.get_attribute("outerHTML")
                            
                            logger.info(f"  元素 {i+1}:")
                            logger.info(f"    文本: {text}")
                            logger.info(f"    链接: {href}")
                            logger.info(f"    HTML: {html[:150]}...")
                        except Exception as e:
                            logger.warning(f"  获取元素 {i+1} 详情时出错: {e}")
            except Exception as e:
                logger.error(f"使用选择器 '{selector}' 时出错: {e}")
        
        # 分析网页结构，找出所有可能的新闻容器
        logger.info("分析网页结构，查找可能的新闻容器...")
        
        # 1. 查找所有可能的新闻容器元素
        possible_containers = [
            "div[class*=news]", 
            "div[class*=card]", 
            "div[class*=article]", 
            "div[class*=list]", 
            "div[class*=item]",
            "div[class*=hot]"
        ]
        
        for container_selector in possible_containers:
            try:
                containers = driver.find_elements(By.CSS_SELECTOR, container_selector)
                if containers:
                    logger.info(f"找到 {len(containers)} 个可能的容器元素使用选择器 '{container_selector}'")
                    
                    # 检查前3个容器是否包含链接和标题
                    for i, container in enumerate(containers[:3]):
                        try:
                            links = container.find_elements(By.TAG_NAME, "a")
                            if links:
                                logger.info(f"  容器 {i+1} 包含 {len(links)} 个链接")
                                logger.info(f"  前3个链接: {[link.get_attribute('href') for link in links[:3]]}")
                        except Exception as e:
                            logger.warning(f"  分析容器 {i+1} 时出错: {e}")
            except Exception as e:
                logger.error(f"使用容器选择器 '{container_selector}' 时出错: {e}")
        
        # 2. 查找所有div元素，统计类名
        logger.info("统计页面上所有div元素的类名...")
        all_divs = driver.find_elements(By.TAG_NAME, "div")
        class_counter = {}
        
        for div in all_divs:
            try:
                class_attr = div.get_attribute("class")
                if class_attr:
                    class_names = class_attr.split()
                    for class_name in class_names:
                        if class_name not in class_counter:
                            class_counter[class_name] = 0
                        class_counter[class_name] += 1
            except Exception:
                pass
        
        # 输出最常见的类名
        logger.info("页面上最常见的div类名 (前20个):")
        sorted_classes = sorted(class_counter.items(), key=lambda x: x[1], reverse=True)
        for class_name, count in sorted_classes[:20]:
            if "news" in class_name.lower() or "card" in class_name.lower() or "list" in class_name.lower() or "item" in class_name.lower():
                logger.info(f"* {class_name}: {count}个 (可能是新闻相关)")
            else:
                logger.info(f"  {class_name}: {count}个")
        
        logger.info("检查澎湃新闻网站结构完成！")
        
    except Exception as e:
        logger.error(f"检查过程中发生错误: {e}", exc_info=True)
    finally:
        if driver:
            logger.info("正在关闭WebDriver...")
            driver.quit()

if __name__ == "__main__":
    check_thepaper_website() 