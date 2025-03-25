#!/usr/bin/env python3
"""
使用Selenium打开财联社网站并检查home-telegraph-list元素
"""

import time
import logging
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
logger = logging.getLogger("selenium_checker")

def setup_driver():
    """设置Selenium WebDriver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # 无头模式
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")  # 设置窗口大小
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")
    
    logger.info("正在初始化Chrome WebDriver...")
    
    # 使用Service对象设置ChromeDriver路径
    chromedriver_path = "/usr/local/bin/chromedriver"
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    logger.info("Chrome WebDriver初始化完成")
    return driver

def check_cls_website():
    """检查财联社网站结构"""
    driver = None
    try:
        driver = setup_driver()
        
        # 打开财联社首页
        url = "https://www.cls.cn/"
        logger.info(f"正在打开 {url}")
        driver.get(url)
        
        # 等待页面加载
        logger.info("等待页面加载...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # 保存页面源代码
        html_source = driver.page_source
        with open("cls_homepage_selenium.html", "w", encoding="utf-8") as f:
            f.write(html_source)
        logger.info("页面源代码已保存到 cls_homepage_selenium.html")
        
        # 检查home-telegraph-list元素
        logger.info("正在查找 home-telegraph-list 元素...")
        telegraph_list = driver.find_elements(By.CLASS_NAME, "home-telegraph-list")
        if telegraph_list:
            logger.info(f"找到 {len(telegraph_list)} 个 home-telegraph-list 元素")
            
            # 获取第一个元素的HTML
            element_html = telegraph_list[0].get_attribute("outerHTML")
            with open("cls_telegraph_list.html", "w", encoding="utf-8") as f:
                f.write(element_html)
            logger.info("已保存 home-telegraph-list 元素的HTML到 cls_telegraph_list.html")
            
            # 查找电报项目 - 使用正确的类名 home-telegraph-item
            telegraph_items = telegraph_list[0].find_elements(By.CLASS_NAME, "home-telegraph-item")
            logger.info(f"在 home-telegraph-list 中找到 {len(telegraph_items)} 个 home-telegraph-item 元素")
            
            # 打印前3个电报项的内容
            for i, item in enumerate(telegraph_items[:3], 1):
                text_content = item.text
                logger.info(f"电报项 {i}:\n{text_content}\n{'-'*50}")
        else:
            logger.warning("未找到 home-telegraph-list 元素，正在查找其它可能的电报容器...")
            
            # 尝试其他可能的类名
            possible_containers = [
                "telegraph-list", "telegraph-container", "telegraph", 
                "roll-list", "cls-telegraph"
            ]
            
            for container_class in possible_containers:
                elements = driver.find_elements(By.CLASS_NAME, container_class)
                if elements:
                    logger.info(f"找到 {len(elements)} 个 {container_class} 元素")
                    
                    # 保存元素HTML
                    element_html = elements[0].get_attribute("outerHTML")
                    with open(f"cls_{container_class}.html", "w", encoding="utf-8") as f:
                        f.write(element_html)
                    logger.info(f"已保存 {container_class} 元素的HTML到 cls_{container_class}.html")
                    break
            
            # 尝试直接查找电报项
            direct_items = driver.find_elements(By.CLASS_NAME, "telegraph-item")
            if direct_items:
                logger.info(f"直接找到 {len(direct_items)} 个 telegraph-item 元素")
                
                # 打印前3个电报项的内容
                for i, item in enumerate(direct_items[:3], 1):
                    text_content = item.text
                    logger.info(f"电报项 {i}:\n{text_content}\n{'-'*50}")
            
            # 检查所有div元素的class属性
            logger.info("正在分析页面上所有div元素的class属性...")
            all_divs = driver.find_elements(By.TAG_NAME, "div")
            classes = {}
            for div in all_divs:
                try:
                    class_attr = div.get_attribute("class")
                    if class_attr:
                        for cls in class_attr.split():
                            if cls not in classes:
                                classes[cls] = 0
                            classes[cls] += 1
                except:
                    pass
            
            # 打印最常见的class
            logger.info("页面上最常见的div class (前20个):")
            sorted_classes = sorted(classes.items(), key=lambda x: x[1], reverse=True)
            for cls, count in sorted_classes[:20]:
                if "telegraph" in cls.lower() or "news" in cls.lower() or "list" in cls.lower():
                    logger.info(f"* {cls}: {count}个 (可能是电报相关)")
                else:
                    logger.info(f"{cls}: {count}个")
        
        logger.info("检查完成！")
        
    except Exception as e:
        logger.error(f"发生错误: {str(e)}", exc_info=True)
    finally:
        if driver:
            logger.info("正在关闭WebDriver...")
            driver.quit()

if __name__ == "__main__":
    check_cls_website() 