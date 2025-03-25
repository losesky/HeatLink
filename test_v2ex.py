from worker.sources.sites.v2ex_selenium import V2EXSeleniumSource
import asyncio
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def test():
    source = V2EXSeleniumSource()
    try:
        print("开始获取V2EX内容...")
        result = await source.fetch()
        if result:
            print(f'成功获取了 {len(result)} 个项目')
            # 打印第一个项目的标题
            if len(result) > 0:
                print(f'第一个项目的标题: {result[0].title}')
        else:
            print('未获取到任何内容')
    except Exception as e:
        print(f'出错: {e}')

if __name__ == "__main__":
    asyncio.run(test()) 